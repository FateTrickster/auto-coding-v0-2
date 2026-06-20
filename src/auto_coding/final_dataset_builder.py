"""Phase 7 — FinalDatasetBuilder: build final_coding_table.csv/.jsonl."""

from __future__ import annotations

import csv, json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def build(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir)
    out = project_dir / "07_final"; out.mkdir(parents=True, exist_ok=True)

    unit_path = project_dir / "00_inputs" / "unit_table.csv"
    with open(unit_path, "r", encoding="utf-8", newline="") as f:
        units = {r["unit_id"]: r for r in csv.DictReader(f)}

    consensus = {r["unit_id"]: r for r in _jl(out / "final_consensus_labels.jsonl")}
    adj = {r["unit_id"]: r for r in _jl(out / "final_adjudication_results.jsonl")}

    rows = []; excluded = 0
    for uid, u in units.items():
        cl = consensus.get(uid, {})
        al = adj.get(uid, {})
        rows.append({
            "unit_id": uid, "turn_id": u.get("turn_id", uid), "group_id": u.get("group_id", ""),
            "session_id": u.get("session_id", ""), "speaker_id": u.get("speaker_id", ""),
            "timestamp": u.get("timestamp", ""), "unit_text": u.get("unit_text", ""),
            "final_primary_code": cl.get("final_primary_code", ""),
            "final_secondary_code": cl.get("final_secondary_code", ""),
            "code_dimension": "情感投入",
            "adjudication_method": "formal_double_coding",
            "decision_id": cl.get("decision_id", ""),
            "final_note": "unresolved" if cl.get("unresolved") else "",
            "codebook_version": "v1.0",
        })

    fields = list(rows[0].keys()) if rows else []
    with open(out / "final_coding_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    with open(out / "final_coding_table.jsonl", "w", encoding="utf-8") as f:
        for r in rows: f.write(json.dumps(r, ensure_ascii=False) + "\n")

    unresolved_n = sum(1 for r in rows if r["final_note"] == "unresolved")
    (out / "final_dataset_report.md").write_text(
        f"# Final Dataset Report\n\n- Total rows: {len(rows)}\n"
        f"- Excluded: {excluded}\n- Unresolved: {unresolved_n}\n"
        f"- Codebook: v1.0\n", encoding="utf-8")
    return {"total": len(rows), "unresolved": unresolved_n}
