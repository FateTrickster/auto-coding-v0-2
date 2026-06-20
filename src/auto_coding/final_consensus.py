"""Phase 7 — FinalConsensusAgent: build final consensus from formal coding."""

from __future__ import annotations

import csv, json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save_jl(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


def build_final_consensus(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir)
    fd = project_dir / "06_formal_coding"
    out = project_dir / "07_final"
    out.mkdir(parents=True, exist_ok=True)

    a = {r["unit_id"]: r for r in _jl(fd / "coder_A_formal.jsonl")}
    b = {r["unit_id"]: r for r in _jl(fd / "coder_B_formal.jsonl")}

    all_ids = sorted(set(a) | set(b))
    adj_results = []; decision_entries = []; consensus = []
    ag = adj_n = un = 0; di = 1

    for uid in all_ids:
        ra = a.get(uid, {}); rb = b.get(uid, {})
        la = ra.get("primary_code") if ra.get("parse_ok") else None
        lb = rb.get("primary_code") if rb.get("parse_ok") else None

        if la and lb and la == lb:
            consensus.append({"unit_id": uid, "final_primary_code": la, "final_secondary_code": None,
                              "consensus_source": "agreement", "decision_id": None, "unresolved": False})
            ag += 1
        elif la and lb and la != lb:
            # Simple adjudication
            unresolved = False; final = la if (ra.get("confidence",0) or 0) >= (rb.get("confidence",0) or 0) else lb
            reason = f"A={la} vs B={lb}; using {'A' if final==la else 'B'}."
            did = f"FD{di:04d}"
            adj_results.append({"decision_id": did, "unit_id": uid, "unit_text": "",
                                "coder_A_label": la or "", "coder_B_label": lb or "",
                                "final_primary_code": final, "final_secondary_code": None,
                                "decision_reason": reason, "unresolved": unresolved})
            decision_entries.append(f"## Decision {did}\n\nunit_id: {uid}\nA: {la}\nB: {lb}\nFinal: {final}\nReason: {reason}\n---\n")
            consensus.append({"unit_id": uid, "final_primary_code": final, "final_secondary_code": None,
                              "consensus_source": "adjudication", "decision_id": did, "unresolved": False})
            adj_n += 1; di += 1
        else:
            consensus.append({"unit_id": uid, "final_primary_code": None, "final_secondary_code": None,
                              "consensus_source": "unresolved", "decision_id": None, "unresolved": True})
            un += 1

    _save_jl(out / "final_adjudication_results.jsonl", adj_results)
    _save_jl(out / "final_consensus_labels.jsonl", consensus)
    (out / "final_decision_log.md").write_text(
        "# Final Decision Log\n\n" + "\n".join(decision_entries), encoding="utf-8")
    return {"total": len(consensus), "agreement": ag, "adjudication": adj_n, "unresolved": un}
