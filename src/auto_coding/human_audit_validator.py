"""v1.1 — HumanAuditValidator: validate human-filled audit templates."""

from __future__ import annotations

import csv, json
from collections import Counter
from pathlib import Path

VALID_LABELS = {"IS1", "IS2", "IS3", "IS4"}
VALID_STATUSES = {"labeled", "uncertain", "exclude", "AWAITING_HUMAN_LABELS", ""}


def write_instructions(project_dir: str | Path) -> str:
    """Generate human_audit_instructions.md."""
    out = Path(project_dir) / "08_validation"
    out.mkdir(parents=True, exist_ok=True)
    md = (
        "# Human Audit Instructions\n\n"
        "## 1. Purpose\n"
        "This audit validates mock/rule-based labels against human judgment. "
        "97 units were sampled from the 3,439-unit final coding table, stratified by label, "
        "disagreement status, and boundary risk.\n\n"
        "## 2. Column Descriptions\n"
        "- `audit_id`: unique audit identifier, do not modify\n"
        "- `unit_id`: original unit identifier, do not modify\n"
        "- `unit_text`: the student message text, do not modify\n"
        "- `context_before`: previous message, do not modify\n"
        "- `context_after`: next message, do not modify\n"
        "- `mock_final_code`: the mock coder's label (IS1/IS2/IS3/IS4), do not modify\n"
        "- `human_label`: **your label** — must be IS1, IS2, IS3, or IS4\n"
        "- `human_confidence`: 0.0-1.0 (optional)\n"
        "- `human_rationale`: your reasoning (optional but recommended)\n"
        "- `human_notes`: any observations, doubts, or exclusion reasons\n"
        "- `audit_status`: `labeled` (complete), `uncertain` (unsure), `exclude` (cannot code)\n\n"
        "## 3. Rules\n"
        "1. `human_label` must be one of: IS1, IS2, IS3, IS4\n"
        "2. If `audit_status` = `labeled`, `human_label` must not be empty\n"
        "3. If `audit_status` = `exclude`, `human_notes` must explain why\n"
        "4. If unsure, set `audit_status` = `uncertain` and fill your best-guess `human_label`\n"
        "5. Do NOT modify `unit_id`, `unit_text`, `context_before`, `context_after`, or `mock_final_code`\n"
        "6. After filling, run: `python -m auto_coding.cli validate-human-audit`\n"
        "7. Final codebook reference: `01_codebook/final_codebook_v1.0.yaml`\n"
    )
    (out / "human_audit_instructions.md").write_text(md, encoding="utf-8")
    return str(out / "human_audit_instructions.md")


def validate(project_dir: str | Path) -> dict:
    """Validate human_audit_template.csv."""
    root = Path(project_dir)
    out = root / "08_validation"
    tp = out / "human_audit_template.csv"

    if not tp.exists():
        return {"status": "NO_TEMPLATE", "ready_for_metrics": False,
                "reason": "human_audit_template.csv not found"}

    with open(tp, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    checks = []
    issues = []
    seen_ids = set()
    dup_ids = set()
    labeled_count = 0
    uncertain_count = 0
    exclude_count = 0
    missing_label = 0
    illegal_label = 0

    for r in rows:
        uid = r.get("unit_id", "").strip()
        if not uid:
            checks.append({"check": "unit_id_empty", "passed": False})
            continue
        if uid in seen_ids:
            dup_ids.add(uid)
        seen_ids.add(uid)

        label = r.get("human_label", "").strip()
        status = r.get("audit_status", "").strip() or ""

        # Track status
        if not label and not status:
            missing_label += 1
        elif status == "labeled":
            if not label:
                issues.append(f"{uid}: audit_status=labeled but human_label empty")
            elif label not in VALID_LABELS:
                illegal_label += 1
                issues.append(f"{uid}: illegal human_label={label}")
            else:
                labeled_count += 1
        elif status == "uncertain":
            uncertain_count += 1
            if label and label not in VALID_LABELS:
                illegal_label += 1
        elif status == "exclude":
            exclude_count += 1
            notes = r.get("human_notes", "").strip()
            if not notes:
                issues.append(f"{uid}: audit_status=exclude but human_notes empty")
        elif status == "AWAITING_HUMAN_LABELS" or status == "":
            missing_label += 1

    checks.append({"check": "file_exists", "passed": True})
    checks.append({"check": "no_duplicate_ids", "passed": len(dup_ids) == 0,
                   "details": f"duplicates={len(dup_ids)}"})
    checks.append({"check": "valid_labels_only", "passed": illegal_label == 0,
                   "details": f"illegal={illegal_label}"})
    checks.append({"check": "exclude_has_notes", "passed": all("exclude" not in i for i in issues)})

    ready = missing_label == 0 and illegal_label == 0 and labeled_count > 0
    status = "HUMAN_LABELS_READY" if ready else "AWAITING_HUMAN_LABELS"

    result = {
        "status": status,
        "ready_for_metrics": ready,
        "total_rows": len(rows),
        "labeled_count": labeled_count,
        "uncertain_count": uncertain_count,
        "exclude_count": exclude_count,
        "missing_label_count": missing_label,
        "illegal_label_count": illegal_label,
        "duplicate_ids": len(dup_ids),
        "issues": issues[:20],
    }

    # Write reports
    with open(out / "human_audit_validation_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    md = [
        "# Human Audit Validation Report",
        f"Status: **{status}**",
        f"Ready for metrics: {ready}",
        "",
        f"- Total rows: {len(rows)}",
        f"- Labeled: {labeled_count}",
        f"- Uncertain: {uncertain_count}",
        f"- Excluded: {exclude_count}",
        f"- Missing: {missing_label}",
        f"- Illegal: {illegal_label}",
        f"- Duplicates: {len(dup_ids)}",
    ]
    if issues:
        md += ["", "## Issues"]
        for i in issues[:15]:
            md.append(f"- {i}")
    (out / "human_audit_validation_report.md").write_text("\n".join(md), encoding="utf-8")

    return result
