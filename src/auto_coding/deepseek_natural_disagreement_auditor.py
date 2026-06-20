"""v1.1 — Natural disagreement auditor for DeepSeek runs."""

from __future__ import annotations

import json
from collections import Counter
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def audit(project_dir: str | Path, run_dir: str) -> dict:
    root = Path(project_dir)
    rd = root / run_dir

    a_items = _jl(rd / "coder_A_results.jsonl")
    b_items = _jl(rd / "coder_B_results.jsonl")
    adj_items = _jl(rd / "adjudication_results.jsonl")

    # Count disagreements
    am = {r["unit_id"]: r for r in a_items if r.get("parse_ok")}
    bm = {r["unit_id"]: r for r in b_items if r.get("parse_ok")}
    dis_units = []
    for uid in sorted(set(am) & set(bm)):
        if am[uid].get("primary_code") != bm[uid].get("primary_code"):
            dis_units.append({
                "unit_id": uid,
                "coder_A_label": am[uid].get("primary_code"),
                "coder_B_label": bm[uid].get("primary_code"),
            })

    ndc = len(dis_units)
    resolved = [r for r in adj_items if not r.get("unresolved")]
    unresolved = [r for r in adj_items if r.get("unresolved")]
    unresolved_reasons = Counter(r.get("unresolved_reason", "no_reason") for r in unresolved)

    # Check refiner evidence
    prop_files = list(rd.glob("codebook_revision_proposal*.json"))
    refiner_used_unresolved = False
    for pf in prop_files:
        prop = json.loads(pf.read_text(encoding="utf-8"))
        for c in prop.get("changes", []):
            for did in c.get("evidence_decisions", []):
                for r in adj_items:
                    if r.get("decision_id") == did and r.get("unresolved"):
                        refiner_used_unresolved = True

    result = {
        "natural_disagreement_count": ndc,
        "resolved_adjudication_count": len(resolved),
        "unresolved_adjudication_count": len(unresolved),
        "unresolved_reason_distribution": dict(unresolved_reasons),
        "refiner_used_unresolved_evidence": refiner_used_unresolved,
        "all_disagreements_have_decision_id": all(
            any(r.get("unit_id") == d["unit_id"] for r in adj_items)
            for d in dis_units
        ),
        "all_resolved_have_final_code": all(
            r.get("final_primary_code") for r in resolved
        ),
        "all_unresolved_have_reason": all(
            r.get("unresolved_reason") for r in unresolved
        ),
        "disagreement_units": dis_units,
    }

    # Write reports
    with open(rd / "natural_disagreement_audit.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    report = [
        "# Natural Disagreement Audit",
        f"Natural disagreements: {ndc}",
        f"Resolved: {len(resolved)}",
        f"Unresolved: {len(unresolved)}",
        f"Refiner used unresolved: {refiner_used_unresolved}",
        "",
        "## Unresolved Reasons",
    ]
    for reason, count in unresolved_reasons.most_common():
        report.append(f"- {reason}: {count}")
    report += ["", "## Disagreement Units"]
    for d in dis_units:
        report.append(f"- {d['unit_id']}: A={d['coder_A_label']} vs B={d['coder_B_label']}")
    (rd / "natural_disagreement_audit.md").write_text("\n".join(report), encoding="utf-8")

    return result
