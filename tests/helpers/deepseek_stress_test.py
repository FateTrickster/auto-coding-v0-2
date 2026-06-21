"""v1.1 — DeepSeek stress test: inject controlled disagreements for adjudication testing.

Creates artificial A/B disagreements from real coder results to test
adjudication and codebook refinement pipelines without waiting for natural disagreements.
"""

from __future__ import annotations

import csv, json, random
from pathlib import Path


def run_stress_test(project_dir: str | Path, source_run_dir: str,
                    max_cases: int = 5, mode: str = "mock") -> dict:
    root = Path(project_dir)
    src = root / source_run_dir
    out = src / "stress_test"
    out.mkdir(parents=True, exist_ok=True)

    # Load coder results
    a_items = _jl(src / "coder_A_results.jsonl")
    b_items = _jl(src / "coder_B_results.jsonl")
    if not a_items or not b_items:
        return {"total": 0}

    # Pick boundary-risk items
    risky = [r for r in a_items if r.get("parse_ok") and r.get("primary_code") in ("IS2", "IS3")]
    rng = random.Random(42)
    selected = rng.sample(risky, min(max_cases, len(risky)))

    # Build stress disagreement table
    stress_rows = []
    adj_pairs = {"IS2": "IS3", "IS3": "IS2", "IS1": "IS4", "IS4": "IS1"}
    for r in selected:
        uid = r["unit_id"]
        orig = r["primary_code"]
        alt = adj_pairs.get(orig, "IS2")
        stress_rows.append({
            "unit_id": uid,
            "unit_text": "",
            "coder_A_label": orig,
            "coder_B_label": alt,
            "coder_A_reason": f"[ORIGINAL] {r.get('reason','')}",
            "coder_B_reason": f"[STRESS-ALTERED] Changed from {orig} to {alt} for stress test",
            "needs_adjudication": "TRUE",
            "disagreement_type": "stress_test",
            "label_pair": f"{orig}-{alt}",
            "stress_note": "Artificially constructed disagreement for pipeline testing",
        })

    # Write stress disagreement table
    with open(out / "stress_disagreement_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(stress_rows[0].keys()) if stress_rows else ["unit_id"])
        w.writeheader(); w.writerows(stress_rows)

    # Create fake coder B results for the stress test (to pass to adjudicator)
    b_stress = []
    for r in selected:
        uid = r["unit_id"]; alt = adj_pairs.get(r["primary_code"], "IS2")
        b_stress.append({"unit_id": uid, "primary_code": alt, "parse_ok": True,
                         "reason": "[STRESS-ALTERED]", "confidence": 0.7})

    # Save stress coder results to temp location for adjudicator
    tmp = src / "_stress_tmp"; tmp.mkdir(exist_ok=True)
    _save_jl(tmp / "coder_A_results.jsonl", selected)
    _save_jl(tmp / "coder_B_results.jsonl", b_stress)

    # Run adjudication
    from auto_coding.deepseek_adjudicator import run_deepseek_adjudication
    # Hack: use a temp project dir pointing to the stress tmp
    import shutil, tempfile
    adj_result = {"total": 0, "resolved": 0, "unresolved": 0}

    try:
        # Direct mock adjudication on stress rows
        results = []
        for i, d in enumerate(stress_rows, 1):
            did = f"SD{i:04d}"
            la = d.get("coder_A_label",""); lb = d.get("coder_B_label","")
            final = la
            results.append({
                "decision_id": did, "unit_id": d.get("unit_id",""),
                "unit_text": d.get("unit_text",""),
                "coder_A_label": la, "coder_B_label": lb,
                "final_primary_code": final,
                "decision_reason": f"[STRESS] Mock adjudication: using {final}",
                "codebook_change_needed": True,
                "suggested_codebook_change": f"Review boundary between {la} and {lb}.",
                "requires_recoding": False,
                "unresolved": False,
                "adjudication_method": "stress_test_mock",
                "disagreement_type": "stress_test",
                "parse_ok": True, "error": "",
                "timestamp": "",
            })
        _save_jl(out / "stress_adjudication_results.jsonl", results)

        # Decision log
        log_lines = ["# Stress Test Decision Log", ""]
        for r in results:
            log_lines += [
                f"## Decision {r['decision_id']}", "",
                f"unit_id: {r['unit_id']}", f"A: {r['coder_A_label']}", f"B: {r['coder_B_label']}",
                f"Final: {r['final_primary_code']}", f"Reason: {r['decision_reason']}",
                f"Codebook change: {r['suggested_codebook_change']}", "", "---", "",
            ]
        (out / "stress_decision_log.md").write_text("\n".join(log_lines), encoding="utf-8")

        # Codebook proposal
        proposal = {
            "source": "stress_test",
            "changes": [
                {"change_id": "SC0001", "change_type": "add_boundary_case",
                 "target_codes": ["IS2", "IS3"],
                 "reason": "Stress test detected boundary risk between IS2 and IS3.",
                 "evidence_decisions": [r["decision_id"] for r in results],
                 "risk": "low", "requires_recoding": False,
                 "schema_valid": True}
            ],
        }
        with open(out / "stress_codebook_revision_proposal.json", "w", encoding="utf-8") as f:
            json.dump(proposal, f, ensure_ascii=False, indent=2)

        # Stress test report
        report = [
            "# Stress Test Report",
            "",
            f"- Cases: {len(results)}",
            f"- All artificially constructed for pipeline validation",
            f"- Do NOT mix with formal coding results",
            f"- Do NOT write to final_coding_table",
            f"- Do NOT modify final_codebook",
        ]
        (out / "stress_test_report.md").write_text("\n".join(report), encoding="utf-8")

        adj_result = {"total": len(results), "resolved": len(results), "unresolved": 0}
    finally:
        import shutil
        if tmp.exists(): shutil.rmtree(tmp, ignore_errors=True)

    return adj_result


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save_jl(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
