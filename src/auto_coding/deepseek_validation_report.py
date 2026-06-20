"""v1.1 — DeepSeek validation report: compare mock/human/DeepSeek labels.

Placeholder structure. Human labels must be filled in first.
DeepSeek real calls deferred to explicit trigger.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path


def generate_placeholder_report(project_dir: str | Path) -> dict:
    """Generate validation report placeholder with mock labels populated.

    Human and DeepSeek columns are empty, ready for filling.
    """
    root = Path(project_dir)
    out_dir = root / "08_validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    template_path = out_dir / "human_audit_template.csv"
    if not template_path.exists():
        return {"status": "no_template", "reason": "Run build-audit-sample first."}

    # Build three-way comparison structure
    with open(template_path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    comparison_rows = []
    for r in rows:
        comparison_rows.append({
            "unit_id": r.get("unit_id", ""),
            "unit_text": r.get("unit_text", ""),
            "mock_label": r.get("mock_final_code", ""),
            "human_label": r.get("human_label", ""),
            "deepseek_label": "",
            "deepseek_confidence": "",
            "deepseek_rationale": "",
            "mock_vs_human_match": "",
            "mock_vs_deepseek_match": "",
            "human_vs_deepseek_match": "",
            "all_three_match": "",
        })

    _save_comparison_csv(out_dir / "three_way_comparison.csv", comparison_rows)

    # Placeholder report
    has_human = any(r.get("human_label", "").strip() for r in rows)

    report_lines = [
        "# DeepSeek Validation Report — v1.1 (Placeholder)",
        "",
        f"## Status: {'AWAITING_HUMAN_LABELS' if not has_human else 'AWAITING_DEEPSEEK_RUN'}",
        "",
        f"- Sample size: {len(rows)}",
        f"- Human labels filled: {has_human}",
        f"- DeepSeek labels: false",
        "",
        "## Next Steps",
        "1. Fill human labels in `human_audit_template.csv`",
        "2. Run `build-audit-sample` to regenerate comparison",
        "3. Run DeepSeek on sampled units (not yet implemented)",
        "4. Fill DeepSeek columns",
        "5. Re-run validation report",
    ]
    (out_dir / "deepseek_validation_report.md").write_text(
        "\n".join(report_lines), encoding="utf-8")

    return {
        "status": "AWAITING_HUMAN_LABELS" if not has_human else "AWAITING_DEEPSEEK_RUN",
        "sample_size": len(rows),
    }


def _save_comparison_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)
