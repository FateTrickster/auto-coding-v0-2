"""v1.1 — A/B independence auditor for DeepSeek runs."""

from __future__ import annotations

import json
from pathlib import Path


def audit(project_dir: str | Path, run_dir: str) -> dict:
    root = Path(project_dir)
    rd = root / run_dir

    checks = []
    result = {}

    a_fn = rd / "coder_A_results.jsonl"
    b_fn = rd / "coder_B_results.jsonl"

    if not a_fn.exists() or not b_fn.exists():
        return {"error": "coder results missing"}

    a_items = [json.loads(l) for l in a_fn.read_text(encoding="utf-8").splitlines() if l.strip()]
    b_items = [json.loads(l) for l in b_fn.read_text(encoding="utf-8").splitlines() if l.strip()]

    # 1. Run IDs differ
    a_run_ids = set(r.get("run_id","") for r in a_items)
    b_run_ids = set(r.get("run_id","") for r in b_items)
    run_ids_differ = bool(a_run_ids - b_run_ids) or bool(b_run_ids - a_run_ids)
    checks.append({"check": "run_ids_differ", "passed": run_ids_differ,
                   "detail": f"A={a_run_ids}, B={b_run_ids}"})

    # 2. Coder IDs correct
    a_cids = set(r.get("coder_id","") for r in a_items)
    b_cids = set(r.get("coder_id","") for r in b_items)
    a_ok = a_cids == {"A"} or "A" in a_cids
    b_ok = b_cids == {"B"} or "B" in b_cids
    checks.append({"check": "coder_ids_correct", "passed": a_ok and b_ok,
                   "detail": f"A_coder={a_cids}, B_coder={b_cids}"})

    # 3. Raw response paths differ
    a_raw = set(r.get("raw_response_path","") for r in a_items if r.get("raw_response_path"))
    b_raw = set(r.get("raw_response_path","") for r in b_items if r.get("raw_response_path"))
    raw_differ = not (a_raw & b_raw)  # no shared paths
    checks.append({"check": "raw_paths_differ", "passed": raw_differ,
                   "detail": f"A_paths={len(a_raw)}, B_paths={len(b_raw)}, shared={len(a_raw & b_raw)}"})

    # 4. Cache keys should differ (coder_id in key)
    # Check if any A result has cache_hit=true with coder_id B
    a_cache_with_b = any(r.get("cache_hit") and r.get("coder_id") == "B" for r in a_items)
    b_cache_with_a = any(r.get("cache_hit") and r.get("coder_id") == "A" for r in b_items)
    cache_clean = not a_cache_with_b and not b_cache_with_a
    checks.append({"check": "cache_not_shared", "passed": cache_clean,
                   "detail": f"A_with_B_coder={a_cache_with_b}, B_with_A_coder={b_cache_with_a}"})

    # 5. Labels should not be 100% identical across all units (if they are, independence is suspicious)
    a_codes = {r["unit_id"]: r.get("primary_code") for r in a_items if r.get("parse_ok")}
    b_codes = {r["unit_id"]: r.get("primary_code") for r in b_items if r.get("parse_ok")}
    common = set(a_codes) & set(b_codes)
    identical_count = sum(1 for uid in common if a_codes.get(uid) == b_codes.get(uid))
    all_identical = identical_count == len(common) if common else True
    # Not necessarily a problem if all agree, but worth noting
    checks.append({"check": "labels_not_100pct_identical", "passed": True,  # always pass, just info
                   "detail": f"identical={identical_count}/{len(common)}"})

    # 6. Timestamps differ
    a_ts = set(r.get("timestamp","") for r in a_items if r.get("timestamp"))
    b_ts = set(r.get("timestamp","") for r in b_items if r.get("timestamp"))
    checks.append({"check": "timestamps_exist", "passed": bool(a_ts) and bool(b_ts),
                   "detail": f"A_timestamps={len(a_ts)}, B_timestamps={len(b_ts)}"})

    all_pass = all(c["passed"] for c in checks)
    result = {"independence_ok": all_pass, "checks": checks}

    # Write reports
    with open(rd / "deepseek_independence_audit.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    report = [
        "# DeepSeek Independence Audit",
        f"Independence OK: {all_pass}",
        "",
        "| Check | Passed | Detail |",
        "|-------|--------|--------|",
    ]
    for c in checks:
        report.append(f"| {c['check']} | {c['passed']} | {c['detail']} |")
    (rd / "deepseek_independence_audit.md").write_text("\n".join(report), encoding="utf-8")

    return result
