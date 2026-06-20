"""Phase 4 — DisagreementAnalysisAgent: identify and classify A/B disagreements.

Three distinct concepts:
  label_disagreement_count — A.primary_code != B.primary_code (strict)
  review_candidate_count   — any item needing human/agent review
  adjudication_count        — items that actually enter adjudication
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path

FIELDS = [
    "unit_id", "unit_text", "context_before", "context_after",
    "coder_A_label", "coder_B_label", "coder_A_confidence", "coder_B_confidence",
    "coder_A_reason", "coder_B_reason", "label_pair", "disagreement_type",
    "is_label_disagreement", "is_review_candidate", "needs_adjudication",
    "review_reason", "analysis_note",
]


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _csv_map(p: Path, key: str = "unit_id") -> dict[str, dict]:
    if not p.exists(): return {}
    with open(p, "r", encoding="utf-8", newline="") as f:
        return {r[key]: r for r in csv.DictReader(f)}


def analyze(project_dir: str | Path, round_id: str = "round_01") -> dict:
    project_dir = Path(project_dir)
    rd = project_dir / "04_pilot" / round_id

    a_items = _jl(rd / "coder_A_results.jsonl")
    b_items = _jl(rd / "coder_B_results.jsonl")
    pilot = _csv_map(project_dir / "04_pilot" / "pilot_sample_units.csv")

    # Load reliability metrics for valid_pairs reference
    rel = {}
    rp = rd / "agreement_metrics.json"
    if rp.exists():
        rel = json.loads(rp.read_text(encoding="utf-8"))

    a_map = {r["unit_id"]: r for r in a_items}
    b_map = {r["unit_id"]: r for r in b_items}
    all_ids = sorted(set(a_map) | set(b_map))

    agreement_count = 0
    label_disagreement_count = 0
    review_candidate_count = 0
    adjudication_count = 0

    rows = []
    type_counts = Counter()

    for uid in all_ids:
        ra = a_map.get(uid)
        rb = b_map.get(uid)
        inp = pilot.get(uid, {}) if pilot else {}

        # Determine status
        is_label_dis = False
        is_review = False
        needs_adj = False
        dtype = ""
        review_reason = ""
        notes = []

        if not ra or not rb:
            is_review = True; needs_adj = True
            dtype = "missing_pair"; review_reason = "missing_pair"
            notes.append("Missing A" if not ra else "Missing B")
        elif not ra.get("parse_ok") or not rb.get("parse_ok"):
            is_review = True; needs_adj = True
            dtype = "parse_error"; review_reason = "parse_error"
            notes.append("Parse error")
        else:
            la = ra.get("primary_code"); lb = rb.get("primary_code")
            labels_match = (la == lb)
            if labels_match:
                agreement_count += 1  # Label agreement, even if uncertain/discussion

            if la != lb:
                is_label_dis = True; is_review = True; needs_adj = True
                dtype = "label_disagreement"; review_reason = "label_mismatch"
                notes.append(f"Label: {la} vs {lb}")
            elif ra.get("uncertain") or rb.get("uncertain"):
                is_review = True
                dtype = "uncertain_item"; review_reason = "uncertain"
                notes.append("Uncertain flag")
            elif ra.get("needs_discussion") or rb.get("needs_discussion"):
                is_review = True
                dtype = "needs_discussion_item"; review_reason = "needs_discussion"
                notes.append("Needs discussion")

        if is_label_dis:
            label_disagreement_count += 1
        if is_review:
            review_candidate_count += 1
        if needs_adj:
            adjudication_count += 1

        if dtype:
            type_counts[dtype] += 1

        if is_label_dis or is_review:
            rows.append({
                "unit_id": uid,
                "unit_text": inp.get("unit_text", ""),
                "context_before": inp.get("context_before", ""),
                "context_after": inp.get("context_after", ""),
                "coder_A_label": ra.get("primary_code", "") if ra else "",
                "coder_B_label": rb.get("primary_code", "") if rb else "",
                "coder_A_confidence": str(ra.get("confidence", "")) if ra else "",
                "coder_B_confidence": str(rb.get("confidence", "")) if rb else "",
                "coder_A_reason": ra.get("reason", "") if ra else "",
                "coder_B_reason": rb.get("reason", "") if rb else "",
                "label_pair": f"{ra.get('primary_code','?') if ra else '?'}-{rb.get('primary_code','?') if rb else '?'}",
                "disagreement_type": dtype,
                "is_label_disagreement": "TRUE" if is_label_dis else "FALSE",
                "is_review_candidate": "TRUE" if is_review else "FALSE",
                "needs_adjudication": "TRUE" if needs_adj else "FALSE",
                "review_reason": review_reason,
                "analysis_note": "; ".join(notes),
            })

    # Compute consistency
    valid_pairs = rel.get("n_valid_pairs", agreement_count + label_disagreement_count)
    computed_pct = agreement_count / max(valid_pairs, 1)
    reliability_pct = rel.get("percent_agreement", computed_pct)
    consistency_ok = abs(computed_pct - reliability_pct) < 0.01

    # Save CSV
    with open(rd / "disagreement_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=FIELDS, extrasaction="ignore")
        w.writeheader(); w.writerows(rows)

    # Analysis JSON
    analysis = {
        "round_id": round_id,
        "total_A": len(a_items), "total_B": len(b_items),
        "valid_pairs": valid_pairs,
        "agreement_count": agreement_count,
        "label_disagreement_count": label_disagreement_count,
        "review_candidate_count": review_candidate_count,
        "adjudication_count": adjudication_count,
        "percent_agreement_from_reliability": reliability_pct,
        "computed_percent_agreement": round(computed_pct, 4),
        "consistency_check_passed": consistency_ok,
        "type_counts": dict(type_counts),
        "label_pair_counts": dict(Counter(r["label_pair"] for r in rows)),
    }
    with open(rd / "disagreement_analysis.json", "w", encoding="utf-8") as f:
        json.dump(analysis, f, ensure_ascii=False, indent=2)

    # Summary MD
    md = [
        f"# Disagreement Summary — {round_id}", "",
        f"## Counts",
        f"- Valid pairs: {valid_pairs}",
        f"- **Agreement**: {agreement_count}",
        f"- **Label disagreements**: {label_disagreement_count}",
        f"- **Review candidates**: {review_candidate_count}",
        f"- **Adjudication needed**: {adjudication_count}",
        f"- Percent agreement (computed): {computed_pct:.4f}",
        f"- Consistency check: {'PASS' if consistency_ok else 'FAIL'}", "",
        "## Review Candidate Types", "",
        "| Type | Count |", "|------|-------|",
    ]
    for t, c in type_counts.most_common():
        md.append(f"| {t} | {c} |")
    (rd / "disagreement_summary.md").write_text("\n".join(md), encoding="utf-8")

    return analysis
