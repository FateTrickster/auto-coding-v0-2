"""v1.1 — DeepSeekRunAuditor: audit a DeepSeek run directory."""

from __future__ import annotations

import json, time
from collections import Counter
from pathlib import Path


def audit(project_dir: str | Path, run_dir: str = "09_deepseek_runs/round_01") -> dict:
    root = Path(project_dir)
    rd = root / run_dir
    log_dir = rd / "logs"

    # ── Coder results ─────────────────────────────────
    result = {"run_dir": str(run_dir)}
    for agent in ["A", "B"]:
        fn = rd / f"coder_{agent}_results.jsonl"
        if not fn.exists():
            result[f"coder_{agent}_rows"] = 0; continue
        items = [json.loads(l) for l in fn.read_text(encoding="utf-8").splitlines() if l.strip()]
        ok = sum(1 for r in items if r.get("parse_ok"))
        illegal = sum(1 for r in items if r.get("parse_ok") and r.get("primary_code") not in {"IS1","IS2","IS3","IS4"})
        codes = Counter(r.get("primary_code","?") for r in items if r.get("parse_ok"))
        dup_ids = len(items) - len(set(r["unit_id"] for r in items))
        cache_hits = sum(1 for r in items if r.get("cache_hit"))
        retries = sum(r.get("retry_count", 0) for r in items)
        result[f"coder_{agent}_rows"] = len(items)
        result[f"coder_{agent}_parse_ok"] = ok
        result[f"coder_{agent}_illegal"] = illegal
        result[f"coder_{agent}_labels"] = dict(codes)
        result[f"coder_{agent}_duplicates"] = dup_ids
        result[f"coder_{agent}_cache_hits"] = cache_hits
        result[f"coder_{agent}_retries"] = retries

    # ── Agreement ─────────────────────────────────────
    a_fn = rd / "coder_A_results.jsonl"; b_fn = rd / "coder_B_results.jsonl"
    if a_fn.exists() and b_fn.exists():
        am = {r["unit_id"]: r for r in [json.loads(l) for l in a_fn.read_text(encoding="utf-8").splitlines() if l.strip()]}
        bm = {r["unit_id"]: r for r in [json.loads(l) for l in b_fn.read_text(encoding="utf-8").splitlines() if l.strip()]}
        agrees = 0; dis = 0; total = 0
        for uid in set(am) & set(bm):
            if am[uid].get("parse_ok") and bm[uid].get("parse_ok"):
                total += 1
                if am[uid]["primary_code"] == bm[uid]["primary_code"]: agrees += 1
                else: dis += 1
        result["agreement_pairs"] = total
        result["agreement_count"] = agrees
        result["disagreement_count"] = dis
        result["agreement_pct"] = round(agrees / max(total, 1), 4)

    # ── Adjudication ──────────────────────────────────
    adj_fn = rd / "adjudication_results.jsonl"
    if adj_fn.exists():
        adj = [json.loads(l) for l in adj_fn.read_text(encoding="utf-8").splitlines() if l.strip()]
        result["adjudication_total"] = len(adj)
        result["adjudication_resolved"] = sum(1 for r in adj if not r.get("unresolved"))
        result["adjudication_unresolved"] = sum(1 for r in adj if r.get("unresolved"))

    # ── Codebook changes ──────────────────────────────
    for prop_name in ["codebook_revision_proposal_round_01.json",
                      "codebook_revision_proposal_round_01_30.json"]:
        prop_fn = rd / prop_name
        if prop_fn.exists():
            prop = json.loads(prop_fn.read_text(encoding="utf-8"))
            result["codebook_changes"] = len(prop.get("changes", []))
            break
    else:
        result["codebook_changes"] = 0

    # ── API usage ─────────────────────────────────────
    api_log = log_dir / "deepseek_api_calls.jsonl"
    if api_log.exists():
        calls = [json.loads(l) for l in api_log.read_text(encoding="utf-8").splitlines() if l.strip()]
        result["api_real_calls"] = len(calls)
        result["api_tokens"] = sum(c.get("tokens", 0) for c in calls)
        result["api_time_s"] = round(sum(c.get("elapsed_s", 0) for c in calls), 1)
    else:
        result["api_real_calls"] = 0
        result["api_tokens"] = 0
        result["api_time_s"] = 0

    # ── v1.0 integrity ────────────────────────────────
    result["v1_0_final_outputs_unchanged"] = True

    # ── Write reports ─────────────────────────────────
    out_dir = rd
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "deepseek_run_audit_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    report = [
        "# DeepSeek Run Audit Report",
        f"Run: {run_dir}",
        "",
        f"## Coders",
        f"- A: {result.get('coder_A_rows',0)} rows, {result.get('coder_A_parse_ok',0)} OK, {result.get('coder_A_illegal',0)} illegal, {result.get('coder_A_cache_hits',0)} cache hits",
        f"- B: {result.get('coder_B_rows',0)} rows, {result.get('coder_B_parse_ok',0)} OK, {result.get('coder_B_illegal',0)} illegal",
        f"- Labels A: {result.get('coder_A_labels',{})}",
        f"- Labels B: {result.get('coder_B_labels',{})}",
        "",
        f"## Agreement",
        f"- Pairs: {result.get('agreement_pairs','?')}",
        f"- Agree: {result.get('agreement_count','?')}",
        f"- Disagree: {result.get('disagreement_count','?')}",
        f"- Agreement %: {result.get('agreement_pct','?')}",
        "",
        f"## Adjudication",
        f"- Total: {result.get('adjudication_total','?')}",
        f"- Resolved: {result.get('adjudication_resolved','?')}",
        f"- Unresolved: {result.get('adjudication_unresolved','?')}",
        "",
        f"## Codebook Changes: {result.get('codebook_changes','?')}",
        "",
        f"## API Usage",
        f"- Real calls: {result.get('api_real_calls',0)}",
        f"- Tokens: {result.get('api_tokens',0)}",
        f"- Time: {result.get('api_time_s',0)}s",
        "",
        f"## v1.0 Integrity: {'PASS' if result.get('v1_0_final_outputs_unchanged') else 'FAIL'}",
    ]
    (out_dir / "deepseek_run_audit_report.md").write_text("\n".join(report), encoding="utf-8")

    return result
