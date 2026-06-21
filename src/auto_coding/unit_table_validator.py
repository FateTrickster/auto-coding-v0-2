"""Phase 1 — Validate unit_table.csv for coding readiness."""

from __future__ import annotations

import csv
from pathlib import Path

from .structural_rules import SHORT_TEXT_MAX_CHARS, LONG_TEXT_MIN_CHARS

REQUIRED_FIELDS = ["unit_id", "turn_id", "group_id", "speaker_id", "unit_text"]


def validate(unit_table_path: str | Path, out_dir: str | Path) -> dict:
    """Validate a unit table CSV and produce enhanced output + report.

    Returns dict with paths and stats.
    """
    unit_table_path = Path(unit_table_path)
    if not unit_table_path.exists():
        raise FileNotFoundError(f"Unit table not found: {unit_table_path}")

    # Schema gate: validate required fields BEFORE creating any output
    with open(unit_table_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        available_fields = reader.fieldnames or []
        rows = list(reader)

    missing = [f for f in REQUIRED_FIELDS if f not in (available_fields or [])]
    if missing:
        raise ValueError(
            f"Missing required field(s) in {unit_table_path}: {missing}. "
            f"Required: {REQUIRED_FIELDS}"
        )
    if not available_fields or all(not h.strip() for h in available_fields):
        raise ValueError(f"Empty or invalid header in {unit_table_path}")
    if not rows:
        raise ValueError(
            f"Unit table contains a valid header but no data rows: {unit_table_path}"
        )

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    fieldnames = list(available_fields)
    enhanced_fieldnames = fieldnames + [
        "short_text_flag", "long_text_flag", "missing_context_flag",
        "possible_multi_function_flag", "validation_note",
    ]

    seen_ids = set()
    dup_ids = set()
    empty_text = 0
    short_text = 0
    long_text = 0
    missing_context = 0
    multi_function = 0

    enhanced_rows = []
    issues = []

    for row in rows:
        uid = row.get("unit_id", "").strip()
        text = row.get("unit_text", "").strip()
        ctx_before = row.get("context_before", "").strip()
        ctx_after = row.get("context_after", "").strip()

        flags = []
        notes = []

        # unit_id checks
        if not uid:
            flags.append("empty_unit_id")
            notes.append("unit_id 为空")
        elif uid in seen_ids:
            dup_ids.add(uid)
            flags.append("duplicate_id")
            notes.append(f"unit_id 重复: {uid}")
        seen_ids.add(uid)

        # unit_text checks
        if not text:
            flags.append("empty_text")
            notes.append("unit_text 为空")
            empty_text += 1
        else:
            text_len = len(text)
            if text_len <= SHORT_TEXT_MAX_CHARS:
                flags.append("short_text")
                notes.append(f"极短文本 ({text_len}字)")
                short_text += 1
            if text_len >= LONG_TEXT_MIN_CHARS:
                flags.append("long_text")
                notes.append(f"长文本 ({text_len}字)")
                long_text += 1
            # Check for possible multi-function (has question mark and multiple clauses)
            has_question = "?" in text or "？" in text
            has_multiple_clauses = any(mark in text for mark in ("。", "；", ";"))
            if has_question and has_multiple_clauses:
                flags.append("multi_function")
                notes.append("疑似多功能文本")
                multi_function += 1

        # context checks
        if not ctx_before and not ctx_after:
            flags.append("missing_context")
            notes.append("上下文完全缺失")
            missing_context += 1

        enhanced_row = dict(row)
        enhanced_row["short_text_flag"] = "TRUE" if "short_text" in flags else "FALSE"
        enhanced_row["long_text_flag"] = "TRUE" if "long_text" in flags else "FALSE"
        enhanced_row["missing_context_flag"] = "TRUE" if "missing_context" in flags else "FALSE"
        enhanced_row["possible_multi_function_flag"] = "TRUE" if "multi_function" in flags else "FALSE"
        enhanced_row["validation_note"] = "; ".join(notes) if notes else ""
        enhanced_rows.append(enhanced_row)

    # Write enhanced CSV
    csv_path = out_dir / "unit_table_v0.1.csv"
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=enhanced_fieldnames)
        writer.writeheader()
        writer.writerows(enhanced_rows)

    # Build report
    report = _build_report(
        total=len(rows), empty_text=empty_text, short_text=short_text,
        long_text=long_text, missing_context=missing_context,
        multi_function=multi_function, dup_ids=dup_ids,
    )
    report_path = out_dir / "unit_table_validation_report.md"
    report_path.write_text(report, encoding="utf-8")

    return {
        "csv_path": str(csv_path),
        "report_path": str(report_path),
        "total_units": len(rows),
        "issues_count": empty_text + short_text + long_text + missing_context + multi_function + len(dup_ids),
    }


def _build_report(**kwargs) -> str:
    total = kwargs["total"]
    lines = [
        "# Unit Table Validation Report",
        "",
        "## 1. 总体情况",
        f"- 总编码单元数: {total}",
        "",
        "## 2. 数据质量统计",
        "",
        "| 问题 | 数量 | 占比 |",
        "|------|------|------|",
    ]

    for label, key in [
        ("空文本", "empty_text"), (f"极短文本 (≤{SHORT_TEXT_MAX_CHARS}字)", "short_text"),
        (f"长文本 (≥{LONG_TEXT_MIN_CHARS}字)", "long_text"), ("缺上下文", "missing_context"),
        ("疑似多功能文本", "multi_function"), ("重复 unit_id", "dup_ids"),
    ]:
        count = kwargs.get(key, 0)
        if isinstance(count, set):
            count = len(count)
        pct = f"{count / total * 100:.1f}%" if total else "0%"
        lines.append(f"| {label} | {count} | {pct} |")

    dup_ids = kwargs.get("dup_ids", set())
    if dup_ids:
        lines += [
            "",
            "## 3. 重复 unit_id",
            ", ".join(sorted(dup_ids)),
        ]

    lines += [
        "",
        "## 4. 是否适合进入编码",
    ]
    if kwargs["empty_text"] > total * 0.1:
        lines.append("⚠️ 空文本占比 >10%，建议先清洗数据。")
    elif kwargs["short_text"] > total * 0.5:
        lines.append("⚠️ 极短文本占比 >50%，编码可能需要大量上下文补充。")
    else:
        lines.append("✅ 基本适合进入编码。")

    return "\n".join(lines)
