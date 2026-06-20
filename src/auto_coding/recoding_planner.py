"""Phase 5 — RecodingPlanner: generate recoding plan for next round."""

from __future__ import annotations

import json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load(p: Path) -> dict:
    if not p.exists(): return {}
    return json.loads(p.read_text(encoding="utf-8"))


def plan(project_dir: str | Path, round_id: str = "round_01") -> dict:
    project_dir = Path(project_dir)
    rd = project_dir / "04_pilot" / round_id
    cb_dir = project_dir / "01_codebook"

    proposal = _load(cb_dir / f"codebook_revision_proposal_{round_id}.json")
    adj = _jl(rd / "adjudication_results.jsonl")
    changes = proposal.get("changes", [])
    needs = any(c.get("requires_recoding", False) for c in changes)

    affected_dids = []; affected_uids = []
    for c in changes: affected_dids.extend(c.get("evidence_decisions", []))
    for r in adj:
        if r["decision_id"] in affected_dids: affected_uids.append(r["unit_id"])

    carry = [r["unit_id"] for r in adj if r.get("unresolved")]

    d = {"round_id": round_id,
         "source_codebook_version": proposal.get("source_codebook_version", ""),
         "target_codebook_version": proposal.get("target_codebook_version", ""),
         "requires_recoding": needs,
         "recoding_scope": "affected_and_new_sample" if needs else "none",
         "affected_decisions": affected_dids,
         "affected_patterns": list(set(p for c in changes for p in c.get("affected_patterns", []))),
         "affected_unit_ids": affected_uids,
         "carryover_disagreement_unit_ids": carry,
         "new_sample_strategy": {"enabled": needs, "ratio_new": 0.7, "ratio_affected": 0.3, "target_size": 300},
         "notes": "Recoding needed." if needs else "No recoding needed."}
    _save(rd / f"recoding_plan_{round_id}.json", d)
    (rd / f"recoding_plan_{round_id}.md").write_text(
        f"# Recoding Plan — {round_id}\n\n- Requires: {needs}\n- Scope: {d['recoding_scope']}\n"
        f"- Affected: {len(affected_uids)} units, {len(affected_dids)} decisions\n"
        f"- Carryover: {len(carry)} unresolved\n- {d['notes']}", encoding="utf-8")
    return d


def _save(p: Path, d: dict):
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
