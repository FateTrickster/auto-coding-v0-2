"""Phase 4 — AdjudicationAgent: rule-based adjudication.

Only adjudicates items flagged as needs_adjudication=TRUE in disagreement_table.csv.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _csv(p: Path) -> list[dict]:
    if not p.exists(): return []
    with open(p, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _sf(v) -> float:
    try: return float(v)
    except: return 0.0


def adjudicate(project_dir: str | Path, round_id: str = "round_01",
               codebook_version: str = "v0.2_candidate") -> dict:
    project_dir = Path(project_dir)
    rd = project_dir / "04_pilot" / round_id

    dis = _csv(rd / "disagreement_table.csv")
    a_map = {r["unit_id"]: r for r in _jl(rd / "coder_A_results.jsonl")}
    b_map = {r["unit_id"]: r for r in _jl(rd / "coder_B_results.jsonl")}

    # Only adjudicate items with needs_adjudication=TRUE
    to_adjudicate = [d for d in dis if d.get("needs_adjudication", "").upper() == "TRUE"]

    results = []
    unresolved_rows = []
    di = 1

    for d in to_adjudicate:
        uid = d["unit_id"]
        ra = a_map.get(uid, {})
        rb = b_map.get(uid, {})
        la = d.get("coder_A_label", "")
        lb = d.get("coder_B_label", "")
        ca = _sf(d.get("coder_A_confidence", 0))
        cb = _sf(d.get("coder_B_confidence", 0))

        final = None
        unresolved = False
        reason = ""
        cb_change = ""
        pattern = ""

        if not ra.get("parse_ok"):
            final = lb if lb else None
            reason = f"A parse failed; using B={lb}."
        elif not rb.get("parse_ok"):
            final = la if la else None
            reason = f"B parse failed; using A={la}."
        elif ra.get("uncertain") and not rb.get("uncertain"):
            final = lb; reason = f"A uncertain; using B={lb}."
        elif rb.get("uncertain") and not ra.get("uncertain"):
            final = la; reason = f"B uncertain; using A={la}."
        elif la != lb:
            if ca - cb >= 0.2:
                final = la; reason = f"A confidence ({ca}) >> B ({cb})."
            elif cb - ca >= 0.2:
                final = lb; reason = f"B confidence ({cb}) >> A ({ca})."
            else:
                unresolved = True
                reason = f"Both confident but disagree ({la} vs {lb})."
                cb_change = f"Review {la}-{lb} boundary."
                pattern = f"{la}-{lb}"
        elif la == lb:
            final = la; reason = f"Both agree on {la}."

        if final is None and not unresolved:
            unresolved = True; reason = "Cannot determine final label."

        r = {
            "decision_id": f"D{di:04d}", "unit_id": uid,
            "unit_text": d.get("unit_text", ""),
            "coder_A_label": la, "coder_B_label": lb,
            "final_primary_code": final, "final_secondary_code": None,
            "adjudication_method": "rule_based_adjudication",
            "disagreement_type": d.get("disagreement_type", ""),
            "decision_reason": reason,
            "codebook_change_needed": bool(cb_change),
            "suggested_codebook_change": cb_change,
            "affected_pattern": pattern,
            "requires_recoding": False, "unresolved": unresolved,
        }
        results.append(r)
        if unresolved:
            unresolved_rows.append({"unit_id": uid, "unit_text": d.get("unit_text", ""),
                                    "coder_A_label": la, "coder_B_label": lb,
                                    "decision_id": r["decision_id"], "reason": reason})
        di += 1

    _save_jl(rd / "adjudication_results.jsonl", results)

    uf = ["unit_id", "unit_text", "coder_A_label", "coder_B_label", "decision_id", "reason"]
    with open(rd / "unresolved_items.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=uf)
        w.writeheader(); w.writerows(unresolved_rows)

    return {"total": len(results), "resolved": sum(1 for r in results if not r["unresolved"]),
            "unresolved": sum(1 for r in results if r["unresolved"])}


def _save_jl(p: Path, items: list[dict]) -> None:
    with open(p, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
