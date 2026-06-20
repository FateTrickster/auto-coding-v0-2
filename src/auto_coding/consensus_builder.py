"""Phase 4 — ConsensusBuilderAgent: build consensus labels from A/B + adjudication."""

from __future__ import annotations

import json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save_jl(p: Path, items: list[dict]) -> None:
    with open(p, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def build(project_dir: str | Path, round_id: str = "round_01") -> dict:
    rd = Path(project_dir) / "04_pilot" / round_id

    a_map = {r["unit_id"]: r for r in _jl(rd / "coder_A_results.jsonl")}
    b_map = {r["unit_id"]: r for r in _jl(rd / "coder_B_results.jsonl")}
    adj_map = {r["unit_id"]: r for r in _jl(rd / "adjudication_results.jsonl")}

    all_ids = sorted(set(a_map) | set(b_map))
    results = []
    ag = adj_n = un = 0

    for uid in all_ids:
        ra = a_map.get(uid, {})
        rb = b_map.get(uid, {})
        adj = adj_map.get(uid)
        la = ra.get("primary_code") if ra.get("parse_ok") else None
        lb = rb.get("primary_code") if rb.get("parse_ok") else None

        if la and lb and la == lb:
            results.append({"unit_id": uid, "final_primary_code": la,
                            "final_secondary_code": None, "consensus_source": "agreement",
                            "decision_id": None, "unresolved": False,
                            "codebook_version": "v0.2_candidate"})
            ag += 1
        elif adj and not adj.get("unresolved"):
            results.append({"unit_id": uid,
                            "final_primary_code": adj.get("final_primary_code"),
                            "final_secondary_code": adj.get("final_secondary_code"),
                            "consensus_source": "adjudication",
                            "decision_id": adj.get("decision_id"),
                            "unresolved": False,
                            "codebook_version": "v0.2_candidate"})
            adj_n += 1
        else:
            results.append({"unit_id": uid, "final_primary_code": None,
                            "final_secondary_code": None, "consensus_source": "unresolved",
                            "decision_id": adj.get("decision_id") if adj else None,
                            "unresolved": True, "codebook_version": "v0.2_candidate"})
            un += 1

    _save_jl(rd / "consensus_labels.jsonl", results)
    return {"total": len(results), "agreement": ag, "adjudication": adj_n, "unresolved": un}
