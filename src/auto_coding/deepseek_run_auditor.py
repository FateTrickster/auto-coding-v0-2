"""v1.1 — DeepSeekRunAuditor: comprehensive run integrity audit."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def audit(project_dir: str | Path, run_dir: str = "09_deepseek_runs/round_01") -> dict:
    root = Path(project_dir)
    rd = root / run_dir
    log_dir = rd / "logs"
    result: dict = {"run_dir": str(run_dir), "_checks": []}

    a_fn = rd / "coder_A_results.jsonl"
    b_fn = rd / "coder_B_results.jsonl"
    adj_fn = rd / "adjudication_results.jsonl"

    # ── Load data ──────────────────────────────────────────
    a_items = _load_jsonl(a_fn)
    b_items = _load_jsonl(b_fn)
    adj_items = _load_jsonl(adj_fn)
    am = {r["unit_id"]: r for r in a_items}
    bm = {r["unit_id"]: r for r in b_items}

    n_a, n_b = len(a_items), len(b_items)
    result["coder_A_rows"] = n_a; result["coder_B_rows"] = n_b
    ok_a = sum(1 for r in a_items if r.get("parse_ok"))
    ok_b = sum(1 for r in b_items if r.get("parse_ok"))
    cache_a = sum(1 for r in a_items if r.get("cache_hit"))
    cache_b = sum(1 for r in b_items if r.get("cache_hit"))
    retries_a = sum(r.get("retry_count", 0) for r in a_items)
    retries_b = sum(r.get("retry_count", 0) for r in b_items)
    result["coder_A_parse_ok"] = ok_a; result["coder_B_parse_ok"] = ok_b
    result["coder_A_cache_hits"] = cache_a; result["coder_B_cache_hits"] = cache_b
    result["coder_A_retries"] = retries_a; result["coder_B_retries"] = retries_b

    # ── Independence ───────────────────────────────────────
    independence_ok = True
    ind_checks: dict[str, bool] = {}
    ind_checks["all_A_coder_id_A"] = all(r.get("coder_id") == "A" for r in a_items) if a_items else True
    ind_checks["all_B_coder_id_B"] = all(r.get("coder_id") == "B" for r in b_items) if b_items else True
    # run_ids
    run_ids_a = {r.get("run_id") for r in a_items if r.get("run_id")}
    run_ids_b = {r.get("run_id") for r in b_items if r.get("run_id")}
    ind_checks["AB_run_id_different"] = not bool(run_ids_a & run_ids_b) if (run_ids_a and run_ids_b) else True
    # raw_response_paths
    raw_a = {r.get("raw_response_path", "") for r in a_items}
    raw_b = {r.get("raw_response_path", "") for r in b_items}
    ind_checks["AB_raw_paths_different"] = not bool(raw_a & raw_b) if (raw_a and raw_b) else True
    # unit sets
    units_a = {r["unit_id"] for r in a_items}
    units_b = {r["unit_id"] for r in b_items}
    ind_checks["AB_same_unit_set"] = units_a == units_b
    ind_checks["A_no_duplicate_ids"] = n_a == len(units_a)
    ind_checks["B_no_duplicate_ids"] = n_b == len(units_b)
    independence_ok = all(ind_checks.values())
    result["independence_ok"] = independence_ok
    result["independence_checks"] = ind_checks

    # ── Agreement ──────────────────────────────────────────
    agrees = 0; dis_count = 0; valid_pairs = 0
    for uid in units_a & units_b:
        ra = am[uid]; rb = bm[uid]
        if ra.get("parse_ok") and rb.get("parse_ok"):
            valid_pairs += 1
            if ra["primary_code"] == rb["primary_code"]: agrees += 1
            else: dis_count += 1
    result["agreement_pairs"] = valid_pairs
    result["agreement_count"] = agrees
    result["natural_disagreement_count"] = dis_count
    result["agreement_pct"] = round(agrees / max(valid_pairs, 1), 4)

    # ── Disagreement ↔ Adjudication integrity ─────────────
    dis_unit_ids = {uid for uid in units_a & units_b
                    if am[uid].get("parse_ok") and bm[uid].get("parse_ok")
                    and am[uid]["primary_code"] != bm[uid]["primary_code"]}
    adj_ids = {r["unit_id"] for r in adj_items}
    result["all_disagreements_have_decision"] = dis_unit_ids <= adj_ids
    result["adjudication_contains_only_disagreements"] = adj_ids <= dis_unit_ids if dis_unit_ids else True

    all_resolved_have_final = all(
        r.get("final_primary_code") is not None
        for r in adj_items if not r.get("unresolved")
    )
    all_unresolved_have_reason = all(
        bool(r.get("decision_reason", "").strip())
        for r in adj_items if r.get("unresolved")
    )
    result["all_resolved_have_final_code"] = all_resolved_have_final
    result["all_unresolved_have_reason"] = all_unresolved_have_reason
    result["adjudication_total"] = len(adj_items)
    result["adjudication_resolved"] = sum(1 for r in adj_items if not r.get("unresolved"))
    result["adjudication_unresolved"] = sum(1 for r in adj_items if r.get("unresolved"))

    # ── Refiner evidence safety ───────────────────────────
    result["refiner_used_unresolved_evidence"] = False
    for pn in [f"codebook_revision_proposal_{run_dir.split('/')[-1]}.json",
               "codebook_revision_proposal_round_01.json"]:
        prop_fn = rd / pn
        if prop_fn.exists():
            prop = json.loads(prop_fn.read_text(encoding="utf-8"))
            changes = prop.get("changes", [])
            result["codebook_changes"] = len(changes)
            for ch in changes:
                ev_ids = ch.get("evidence_decisions", [])
                for did in ev_ids:
                    adj_match = [r for r in adj_items if r.get("decision_id") == did]
                    if adj_match and adj_match[0].get("unresolved"):
                        result["refiner_used_unresolved_evidence"] = True
            break
    else:
        result["codebook_changes"] = 0

    # ── API usage ──────────────────────────────────────────
    api_log = log_dir / "deepseek_api_calls.jsonl"
    if api_log.exists():
        calls = [json.loads(l) for l in api_log.read_text(encoding="utf-8").splitlines() if l.strip()]
        result["api_real_calls"] = len(calls)
        result["api_tokens"] = sum(c.get("tokens", 0) for c in calls)
        result["api_time_s"] = round(sum(c.get("elapsed_s", 0) for c in calls), 1)
        latencies = [c.get("elapsed_s", 0) for c in calls if c.get("elapsed_s")]
        result["average_latency_s"] = round(sum(latencies) / max(len(latencies), 1), 2)
        result["max_latency_s"] = round(max(latencies), 2) if latencies else 0
    else:
        result["api_real_calls"] = 0; result["api_tokens"] = 0; result["api_time_s"] = 0
        result["average_latency_s"] = 0; result["max_latency_s"] = 0

    # ── Audit verdict ─────────────────────────────────────
    critical = [
        n_a > 0, n_b > 0,  # must have results
        independence_ok,
        n_a == n_b,
        result.get("all_disagreements_have_decision", True),
        result.get("all_resolved_have_final_code", True),
        result.get("all_unresolved_have_reason", True),
        not result.get("refiner_used_unresolved_evidence", False),
    ]
    result["audit_passed"] = all(critical)
    ck = result["_checks"]
    for label, ok in [("independence", independence_ok), ("row_count_match", n_a == n_b),
        ("all_dis_have_decision", result["all_disagreements_have_decision"]),
        ("resolved_have_final", all_resolved_have_final),
        ("unresolved_have_reason", all_unresolved_have_reason),
        ("no_unresolved_evidence", not result["refiner_used_unresolved_evidence"])]:
        ck.append({"check": label, "passed": ok})
    result.pop("_checks", None)

    # ── Write reports ─────────────────────────────────────
    out_dir = rd
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "deepseek_run_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    report = [
        "# DeepSeek Run Audit Report",
        f"Run: {run_dir}",
        f"Audit: {'PASS' if result['audit_passed'] else 'FAIL'}",
        "",
        "## Independence",
        f"- OK: {independence_ok}",
    ]
    for k, v in ind_checks.items():
        report.append(f"- {k}: {'PASS' if v else 'FAIL'}")
    report += [
        "",
        "## Coders",
        f"- A: {n_a} rows, {ok_a} OK, {cache_a} cache hits, {retries_a} retries",
        f"- B: {n_b} rows, {ok_b} OK, {cache_b} cache hits, {retries_b} retries",
        "",
        "## Agreement",
        f"- Pairs: {valid_pairs}, Agree: {agrees}, Disagree: {dis_count}",
        f"- Agreement: {result['agreement_pct']}",
        "",
        "## Adjudication Integrity",
        f"- All disagreements have decision: {result['all_disagreements_have_decision']}",
        f"- Only disagreements adjudicated: {result.get('adjudication_contains_only_disagreements','?')}",
        f"- All resolved have final code: {all_resolved_have_final}",
        f"- All unresolved have reason: {all_unresolved_have_reason}",
        f"- Total: {len(adj_items)}, Resolved: {result['adjudication_resolved']}, Unresolved: {result['adjudication_unresolved']}",
        "",
        "## Refiner Evidence Safety",
        f"- Unresolved evidence used: {result['refiner_used_unresolved_evidence']}",
        f"- Codebook changes: {result['codebook_changes']}",
        "",
        "## API Usage",
        f"- Real calls: {result['api_real_calls']}",
        f"- Tokens: {result['api_tokens']}",
        f"- Time: {result['api_time_s']}s",
        f"- Avg latency: {result['average_latency_s']}s",
        f"- Max latency: {result['max_latency_s']}s",
    ]
    (out_dir / "deepseek_run_audit_report.md").write_text("\n".join(report), encoding="utf-8")

    return result


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]
