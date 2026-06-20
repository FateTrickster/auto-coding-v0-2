"""v1.1 — DeepSeek task queue with A/B concurrency, proper cache keys, and state tracking."""

from __future__ import annotations

import hashlib, json, time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from .deepseek_client import DeepSeekClient, RealDeepSeekDisabledError


def _cache_key(unit_id: str, coder_id: str, profile: str,
               codebook_hash: str, prompt_hash: str, model: str, temperature: float) -> str:
    raw = f"{unit_id}|{coder_id}|{profile}|{codebook_hash}|{prompt_hash}|{model}|{temperature}"
    return hashlib.sha256(raw.encode()).hexdigest()[:16]


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:12]


def run_concurrent_coding(
    units: list[dict],
    codebook_version: str,
    system_prompt_a: str,
    system_prompt_b: str,
    coder_a_profile: str,
    coder_b_profile: str,
    out_dir: Path,
    log_dir: Path,
    mode: str = "mock",
    concurrency: int = 5,
    batch_size: int = 50,
    flush_every: int = 10,
    rate_limit_rps: float = 0,
    max_items: int = 300,
) -> tuple[list[dict], list[dict]]:
    """Run A/B coding concurrently with proper cache keys."""
    units = units[:max_items]
    valid = {"IS1", "IS2", "IS3", "IS4"}

    # Hash codebook/prompt for cache
    cb_hash = _hash_text(codebook_version)
    prompt_a_hash = _hash_text(system_prompt_a)
    prompt_b_hash = _hash_text(system_prompt_b)
    model = "deepseek-chat"
    temperature = 0.1

    # Build task list: all (unit, coder_id, profile, prompt_hash) combinations
    tasks_a = [(u, "A", coder_a_profile, prompt_a_hash, system_prompt_a) for u in units]
    tasks_b = [(u, "B", coder_b_profile, prompt_b_hash, system_prompt_b) for u in units]
    all_tasks = tasks_a + tasks_b

    results_a: dict[str, dict] = {}
    results_b: dict[str, dict] = {}
    clients = {}

    def _get_client(profile: str) -> DeepSeekClient:
        if profile not in clients:
            clients[profile] = DeepSeekClient(cache_dir=log_dir / f"cache_{profile}")
        return clients[profile]

    def _process_task(task):
        unit, coder_id, profile, prompt_hash, prompt = task
        uid = unit.get("unit_id", "")
        text = unit.get("unit_text", "").strip()
        ctx = unit.get("context_before", "")[:200]
        user = f"unit_id: {uid}\ncontext: {ctx}\nunit_text: {text}"

        ck = _cache_key(uid, coder_id, profile, cb_hash, prompt_hash, model, temperature)

        if mode == "mock":
            # Fast mock: keyword-based
            code = "IS2"
            for kw, c in [("是不是", "IS3"), ("谢谢", "IS4"), ("不是吧", "IS1"), ("okok", "IS2")]:
                if kw in text:
                    code = c; break
            return uid, coder_id, {
                "unit_id": uid, "primary_code": code, "confidence": 0.8,
                "evidence_span": text[:60], "reason": f"[MOCK] coder {coder_id}",
                "uncertain": False, "parse_ok": True,
                "coder_id": coder_id, "profile": profile, "cache_key": ck, "cache_hit": False,
            }

        client = _get_client(profile)
        cache_hit = False
        if client.cache_dir and (client.cache_dir / f"{ck}.json").exists():
            cached = client._cache_get(ck)
            if cached:
                cache_hit = True
                cached["coder_id"] = coder_id
                cached["profile"] = profile
                cached["cache_key"] = ck
                cached["cache_hit"] = True
                return uid, coder_id, cached

        try:
            resp = client.chat_json(prompt, user, max_tokens=800)
            code = resp.get("primary_code", "")
            result = {
                "unit_id": uid, "primary_code": code if code in valid else None,
                "confidence": resp.get("confidence", 0.7),
                "evidence_span": resp.get("evidence_span", text[:60]),
                "reason": resp.get("reason", ""),
                "uncertain": resp.get("uncertain", False),
                "parse_ok": code in valid,
                "coder_id": coder_id, "profile": profile, "cache_key": ck, "cache_hit": False,
            }
            if client.cache_dir:
                client._cache_set(ck, result)
            return uid, coder_id, result
        except Exception as e:
            return uid, coder_id, {
                "unit_id": uid, "primary_code": None, "parse_ok": False,
                "error": str(e), "coder_id": coder_id, "profile": profile,
                "cache_key": ck, "cache_hit": False,
            }

    t0 = time.time()
    batch = all_tasks[:batch_size]
    processed = 0

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_process_task, t): t for t in batch}
        for future in as_completed(futures):
            uid, coder_id, result = future.result()
            if coder_id == "A":
                results_a[uid] = result
            else:
                results_b[uid] = result
            processed += 1

            if rate_limit_rps > 0:
                time.sleep(1.0 / rate_limit_rps)

            if processed % flush_every == 0:
                _flush_results(out_dir, results_a, results_b, log_dir, clients)

    # Process remaining batches
    for start in range(batch_size, len(all_tasks), batch_size):
        batch = all_tasks[start:start + batch_size]
        with ThreadPoolExecutor(max_workers=concurrency) as executor:
            futures = {executor.submit(_process_task, t): t for t in batch}
            for future in as_completed(futures):
                uid, coder_id, result = future.result()
                if coder_id == "A":
                    results_a[uid] = result
                else:
                    results_b[uid] = result
                processed += 1
                if processed % flush_every == 0:
                    _flush_results(out_dir, results_a, results_b, log_dir, clients)

    # Final flush
    _flush_results(out_dir, results_a, results_b, log_dir, clients)

    ra_list = sorted(results_a.values(), key=lambda r: r.get("unit_id", ""))
    rb_list = sorted(results_b.values(), key=lambda r: r.get("unit_id", ""))
    elapsed = time.time() - t0
    print(f"  Concurrent coding: {len(ra_list)}/{len(rb_list)} results in {elapsed:.0f}s")
    return ra_list, rb_list


def _flush_results(out_dir: Path, results_a: dict, results_b: dict,
                   log_dir: Path, clients: dict):
    """Flush current results to JSONL files."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for agent, results in [("A", results_a), ("B", results_b)]:
        items = sorted(results.values(), key=lambda r: r.get("unit_id", ""))
        with open(out_dir / f"coder_{agent}_results.jsonl", "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
    # Save logs
    for profile, client in clients.items():
        client.save_logs(log_dir)
