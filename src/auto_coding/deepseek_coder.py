"""v1.1 — DeepSeekCoderAgent: strict LLM output boundaries.

LLM outputs ONLY: primary_code, confidence, evidence_span, reason, uncertain.
Program generates ALL metadata: unit_id, coder_id, parse_ok, timestamp, etc.
"""

from __future__ import annotations

import csv, json, time
from datetime import datetime, timezone
from pathlib import Path

# ── LLM output schema (what DeepSeek should return) ──────
LLM_CODER_SCHEMA = {"primary_code", "confidence", "evidence_span", "reason", "uncertain"}

# ── Program-generated metadata fields ────────────────────
PROGRAM_CODER_FIELDS = [
    "unit_id", "secondary_code", "needs_discussion",
    "codebook_version", "coder_id", "parse_ok", "error",
    "model", "run_id", "round_id", "timestamp",
    "raw_response_path", "cache_hit", "retry_count",
]


def _load_prompt(project_dir: Path, codebook_version: str) -> str:
    prompt_path = project_dir / "02_prompts" / f"coder_prompt_{codebook_version}.md"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    import yaml
    cb_path = project_dir / "01_codebook" / f"codebook_{codebook_version}.yaml"
    if not cb_path.exists() and codebook_version == "v1.0":
        cb_path = project_dir / "01_codebook" / "final_codebook_v1.0.yaml"
    cb = yaml.safe_load(cb_path.read_text(encoding="utf-8"))
    codes = cb.get("codes", [])
    lines = ["你是独立编码员。", "", "# 代码列表"]
    for c in codes:
        cid = c.get("label") or c.get("code_id", "?")
        cn = c.get("name_zh") or c.get("code_name", "?")
        d = c.get("revised_operational_definition") or c.get("definition", "")
        lines.append(f"## {cid} {cn}: {d[:200]}")
    lines += [
        "", "# 输出要求",
        "只输出以下 JSON 字段，不要输出其他字段：",
        '{"primary_code":"IS1|IS2|IS3|IS4","confidence":0.0,"evidence_span":"原文摘录","reason":"判断理由","uncertain":false}',
        "禁止输出 unit_id、coder_id 等元数据字段。",
    ]
    return "\n".join(lines)


CODER_PROFILES = {
    "conservative": "\n你是一个保守型编码员。严格依据定义编码。低置信时标记 uncertain=true。",
    "boundary_sensitive": "\n你是一个边界敏感型编码员。关注边界案例和上下文。遇到多义文本更容易标记 uncertain。",
    "default": "",
}


def _validate_llm_output(raw: dict) -> dict:
    """Strip non-schema fields, normalize, return clean LLM output."""
    clean = {}
    for k in LLM_CODER_SCHEMA:
        clean[k] = raw.get(k)
    # Normalize confidence
    try: clean["confidence"] = float(clean.get("confidence", 0.7))
    except: clean["confidence"] = 0.7
    # Normalize uncertain
    if not isinstance(clean.get("uncertain"), bool):
        clean["uncertain"] = False
    # Track ignored fields
    ignored = [k for k in raw if k not in LLM_CODER_SCHEMA]
    return clean, ignored


def run_deepseek_coding(project_dir: str | Path, round_id: str = "round_01",
                        codebook_version: str = "v1.0", mode: str = "mock",
                        max_items: int = 30,
                        coder_a_profile: str = "default",
                        coder_b_profile: str = "default",
                        input_units_path: str | None = None,
                        concurrency: int = 4,
                        overwrite: bool = False) -> dict:
    root = Path(project_dir)
    rd = root / "09_deepseek_runs" / round_id
    if rd.exists() and not overwrite:
        existing = list(rd.glob("coder_*_results.jsonl"))
        if existing:
            raise FileExistsError(
                f"Round directory already has results: {rd}\n"
                f"Use overwrite=True to replace."
            )
    if overwrite and rd.exists():
        _clean_round_artifacts(rd)
    rd.mkdir(parents=True, exist_ok=True)
    _write_round_status(rd, "running")
    log_dir = rd / "logs"; log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat()

    if input_units_path:
        pilot_path = root / input_units_path
    else:
        pilot_path = root / "04_pilot" / "pilot_sample_units.csv"
        if not pilot_path.exists():
            raise FileNotFoundError(
                f"Pilot sample not found: {pilot_path}\n"
                f"Run `sample-pilot` first."
            )
    with open(pilot_path, "r", encoding="utf-8", newline="") as f:
        units = list(csv.DictReader(f))[:max_items]

    base_prompt = _load_prompt(root, codebook_version)
    prompt_a = base_prompt + CODER_PROFILES.get(coder_a_profile, "")
    prompt_b = base_prompt + CODER_PROFILES.get(coder_b_profile, "")
    valid = {"IS1", "IS2", "IS3", "IS4"}

    if mode == "mock":
        ra, rb = _run_mock_coding(units, codebook_version, round_id, rd, ts)
    else:
        ra, rb = _run_real_coding(
            units, prompt_a, prompt_b, valid, rd, log_dir, ts,
            codebook_version, round_id, concurrency,
        )

    _save_jl(rd / "coder_A_results.jsonl", ra)
    _save_jl(rd / "coder_B_results.jsonl", rb)

    ok_a = sum(1 for r in ra if r["parse_ok"]); ok_b = sum(1 for r in rb if r["parse_ok"])
    return {"coder_a_total": len(ra), "coder_a_ok": ok_a,
            "coder_b_total": len(rb), "coder_b_ok": ok_b}


def _run_mock_coding(units, codebook_version, round_id, rd, ts):
    """Mock coding using MockCoderAgent — for testing only, not production."""
    from .coder import MockCoderAgent
    ra = _mock_results(
        MockCoderAgent("A", 42).code(units, codebook_version), "A",
        codebook_version, round_id, rd, ts,
    )
    rb = _mock_results(
        MockCoderAgent("B", 43).code(units, codebook_version), "B",
        codebook_version, round_id, rd, ts,
    )
    return ra, rb


def _run_real_coding(units, prompt_a, prompt_b, valid, rd, log_dir, ts,
                      cv, round_id, concurrency):
    """Production DeepSeek coding. Each task creates its own client.
    API logs and retry counts are collected and aggregated by the main thread.
    """
    from .deepseek_client import DeepSeekClient
    from concurrent.futures import ThreadPoolExecutor, as_completed

    if concurrency < 1:
        raise ValueError(f"concurrency must be >= 1, got {concurrency}")

    uids = [u.get("unit_id", "").strip() for u in units]
    seen = set()
    for uid in uids:
        if uid in seen:
            raise ValueError(f"Duplicate unit_id in input: {uid}")
        seen.add(uid)

    tasks = [(u, "A", prompt_a) for u in units] + [(u, "B", prompt_b) for u in units]
    results_a: dict[str, dict] = {}
    results_b: dict[str, dict] = {}
    all_call_logs: list[dict] = []

    def _code_one(task):
        unit, coder_id, prompt = task
        uid = unit.get("unit_id", "")
        text = unit.get("unit_text", "").strip()
        ctx = unit.get("context_before", "")[:200]
        user = f"unit_id: {uid}\ncontext: {ctx}\nunit_text: {text}"
        client = DeepSeekClient(cache_dir=log_dir / f"cache_{coder_id}")
        cache_hit = False

        try:
            cache_key = client._cache_key(prompt, user, 800)
            if client.cache_dir and (client.cache_dir / f"{cache_key}.json").exists():
                cache_hit = True
            resp = client.chat_json(prompt, user, max_tokens=800)
            retry_count = client.last_retry_count
            llm, ignored = _validate_llm_output(resp)
            code = llm.get("primary_code", "")
            raw_path = log_dir / f"raw_{coder_id}_{uid}.json"
            raw_path.write_text(json.dumps(resp, ensure_ascii=False), encoding="utf-8")
            if code not in valid:
                return _build_result(uid, coder_id, None, False,
                    f"invalid_code:{code}", ts, cv, round_id, cache_hit, retry_count, str(raw_path)), client.call_log
            return _build_result(uid, coder_id, code, True, "",
                ts, cv, round_id, cache_hit, retry_count, str(raw_path),
                confidence=llm.get("confidence", 0.7),
                evidence_span=llm.get("evidence_span", text[:60]),
                reason=llm.get("reason", ""),
                uncertain=llm.get("uncertain", False),
                ignored_fields=ignored), client.call_log
        except Exception as e:
            retry_count = getattr(client, 'last_retry_count', 0)
            return _build_result(uid, coder_id, None, False,
                str(e), ts, cv, round_id, cache_hit, retry_count, ""), client.call_log

    with ThreadPoolExecutor(max_workers=concurrency) as executor:
        futures = {executor.submit(_code_one, t): t for t in tasks}
        for future in as_completed(futures):
            result, call_log = future.result()
            all_call_logs.extend(call_log)
            cid = result.get("coder_id", "")
            uid = result.get("unit_id", "")
            if cid == "A":
                results_a[uid] = result
            else:
                results_b[uid] = result

    if all_call_logs:
        _write_api_log(log_dir, all_call_logs)

    ra_list = [results_a[u.get("unit_id", "")] for u in units if u.get("unit_id", "") in results_a]
    rb_list = [results_b[u.get("unit_id", "")] for u in units if u.get("unit_id", "") in results_b]
    return ra_list, rb_list


def _write_api_log(log_dir, entries):
    log_dir.mkdir(parents=True, exist_ok=True)
    p = log_dir / "deepseek_api_calls.jsonl"
    with open(p, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def _write_round_status(rd, status, audit_passed=False, failure_stage="", failure_reasons=None):
    import json as _json
    s = {"round_id": rd.name, "status": status, "audit_passed": audit_passed,
         "failure_stage": failure_stage, "failure_reasons": failure_reasons or [],
         "codebook_candidate_accepted": status == "accepted"}
    with open(rd / "round_status.json", "w", encoding="utf-8") as f:
        _json.dump(s, f, ensure_ascii=False, indent=2)
    return s


def _clean_round_artifacts(rd):
    import shutil
    for name in ["coder_A_results.jsonl", "coder_B_results.jsonl",
                 "adjudication_results.jsonl", "disagreement_table.csv",
                 "low_confidence_agreement_items.csv", "low_confidence_agreement_items.jsonl",
                 "deepseek_run_audit_report.json", "deepseek_run_audit_report.md",
                 "round_status.json", "unresolved_items.csv"]:
        p = rd / name; p.unlink(missing_ok=True)
    for pat in ["codebook_revision_proposal_*.json", "raw_*.json"]:
        for p in rd.glob(pat): p.unlink()
    for d in ["logs", "cache_A", "cache_B"]:
        p = rd / d
        if p.exists():
            shutil.rmtree(p)


def _mock_results(mock_items, coder_id, codebook_version, round_id, rd, ts):
    """Adapt MockCoderAgent output to full schema."""
    results = []
    for m in mock_items:
        results.append(_build_result(
            m.get("unit_id",""), coder_id,
            m.get("primary_code") if m.get("parse_ok") else None,
            m.get("parse_ok", False),
            m.get("error", ""), ts, codebook_version, round_id, False, 0, "",
            confidence=m.get("confidence"), evidence_span=m.get("evidence_span",""),
            reason=m.get("reason",""), uncertain=m.get("uncertain", False)))
    return results


def _build_result(unit_id, coder_id, primary_code, parse_ok, error, ts,
                  codebook_version, round_id, cache_hit, retry_count,
                  raw_response_path, **kwargs):
    return {
        # LLM fields (minimal)
        "primary_code": primary_code,
        "confidence": kwargs.get("confidence"),
        "evidence_span": kwargs.get("evidence_span", ""),
        "reason": kwargs.get("reason", ""),
        "uncertain": kwargs.get("uncertain", False),
        # Program-generated fields
        "unit_id": unit_id,
        "secondary_code": None,
        "needs_discussion": not parse_ok or kwargs.get("uncertain", False),
        "codebook_version": codebook_version,
        "coder_id": coder_id,
        "parse_ok": parse_ok,
        "error": error,
        "model": "deepseek-chat",
        "run_id": f"{round_id}_{coder_id}",
        "round_id": round_id,
        "timestamp": ts,
        "raw_response_path": raw_response_path,
        "cache_hit": cache_hit,
        "retry_count": retry_count,
        "ignored_llm_fields": kwargs.get("ignored_fields", []),
    }


def _save_jl(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
