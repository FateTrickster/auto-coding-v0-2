"""Phase 1 — Review pilot sample coverage against full unit table."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path


def review(pilot_path: str | Path, unit_table_path: str | Path, out_dir: str | Path) -> dict:
    """Review pilot sample coverage.

    Returns dict with paths and coverage stats.
    """
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    # Load pilot sample (just unit_ids)
    with open(pilot_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        pilot_ids = {row["unit_id"].strip() for row in reader if row.get("unit_id", "").strip()}

    # Load unit table
    with open(unit_table_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_units = list(reader)

    total_units = len(all_units)
    pilot_units = [u for u in all_units if u.get("unit_id", "").strip() in pilot_ids]
    pilot_n = len(pilot_units)

    # Coverage stats
    all_groups = Counter(u.get("group_id", "?") for u in all_units)
    pilot_groups = Counter(u.get("group_id", "?") for u in pilot_units)
    all_speakers = Counter(u.get("speaker_id", "?") for u in all_units)
    pilot_speakers = Counter(u.get("speaker_id", "?") for u in pilot_units)

    # Text type coverage
    short_text_all = sum(1 for u in all_units if len(u.get("unit_text", "")) <= 3)
    long_text_all = sum(1 for u in all_units if len(u.get("unit_text", "")) >= 120)
    missing_ctx_all = sum(1 for u in all_units
                          if not u.get("context_before", "").strip() and not u.get("context_after", "").strip())

    short_text_pilot = sum(1 for u in pilot_units if len(u.get("unit_text", "")) <= 3)
    long_text_pilot = sum(1 for u in pilot_units if len(u.get("unit_text", "")) >= 120)
    missing_ctx_pilot = sum(1 for u in pilot_units
                            if not u.get("context_before", "").strip() and not u.get("context_after", "").strip())

    # Enhanced pilot CSV
    enhanced_rows = []
    for u in all_units:
        uid = u.get("unit_id", "").strip()
        row = dict(u)
        row["in_pilot_sample"] = "TRUE" if uid in pilot_ids else "FALSE"
        enhanced_rows.append(row)

    csv_path = out_dir / "pilot_sample_units_v0.1.csv"
    fieldnames = list(all_units[0].keys()) + ["in_pilot_sample"]
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(enhanced_rows)

    # Build report
    report = _build_report(
        pilot_n=pilot_n, total_units=total_units,
        all_groups=all_groups, pilot_groups=pilot_groups,
        all_speakers=all_speakers, pilot_speakers=pilot_speakers,
        short_text_all=short_text_all, short_text_pilot=short_text_pilot,
        long_text_all=long_text_all, long_text_pilot=long_text_pilot,
        missing_ctx_all=missing_ctx_all, missing_ctx_pilot=missing_ctx_pilot,
    )
    report_path = out_dir / "pilot_sample_review_report.md"
    report_path.write_text(report, encoding="utf-8")

    # Determine if more sampling is needed
    groups_missing = set(all_groups.keys()) - set(pilot_groups.keys())
    needs_more = len(groups_missing) > 0

    return {
        "csv_path": str(csv_path),
        "report_path": str(report_path),
        "pilot_n": pilot_n,
        "total_units": total_units,
        "pilot_pct": f"{pilot_n / total_units * 100:.1f}%" if total_units else "0%",
        "groups_covered": f"{len(pilot_groups)}/{len(all_groups)}",
        "needs_more_sampling": needs_more,
    }


def _build_report(**kw) -> str:
    lines = [
        "# Pilot Sample Review Report",
        "",
        "## 1. 样本总体情况",
        f"- 试编码样本数: {kw['pilot_n']}",
        f"- 总编码单元数: {kw['total_units']}",
        f"- 抽样比例: {kw['pilot_n'] / max(kw['total_units'], 1) * 100:.1f}%",
        "",
        "## 2. Group 覆盖",
        "",
        "| group | 全量 | 试编码 | 覆盖 |",
        "|-------|------|--------|------|",
    ]
    for g in sorted(kw["all_groups"]):
        a = kw["all_groups"].get(g, 0)
        p = kw["pilot_groups"].get(g, 0)
        lines.append(f"| {g} | {a} | {p} | {'✅' if p > 0 else '❌'} |")

    lines += [
        "",
        "## 3. Speaker 覆盖",
        "",
        "| speaker | 全量 | 试编码 | 覆盖 |",
        "|---------|------|--------|------|",
    ]
    for s in sorted(kw["all_speakers"]):
        a = kw["all_speakers"].get(s, 0)
        p = kw["pilot_speakers"].get(s, 0)
        lines.append(f"| {s} | {a} | {p} | {'✅' if p > 0 else '❌'} |")

    lines += [
        "",
        "## 4. 文本类型覆盖",
        "",
        "| 类型 | 全量 | 试编码 | 覆盖 |",
        "|------|------|--------|------|",
        f"| 极短文本 (≤3字) | {kw['short_text_all']} | {kw['short_text_pilot']} | {'✅' if kw['short_text_pilot'] > 0 else '❌'} |",
        f"| 长文本 (≥120字) | {kw['long_text_all']} | {kw['long_text_pilot']} | {'✅' if kw['long_text_pilot'] > 0 else '❌'} |",
        f"| 缺上下文 | {kw['missing_ctx_all']} | {kw['missing_ctx_pilot']} | {'✅' if kw['missing_ctx_pilot'] > 0 else '❌'} |",
        "",
        "## 5. 风险样本覆盖",
    ]

    risks = []
    if kw["short_text_all"] > 0 and kw["short_text_pilot"] == 0:
        risks.append("⚠️ 极短文本未覆盖")
    if kw["long_text_all"] > 0 and kw["long_text_pilot"] == 0:
        risks.append("⚠️ 长文本未覆盖")
    if kw["missing_ctx_all"] > 0 and kw["missing_ctx_pilot"] == 0:
        risks.append("⚠️ 缺上下文样本未覆盖")

    if risks:
        for r in risks:
            lines.append(f"- {r}")
    else:
        lines.append("- ✅ 主要风险类型已覆盖")

    groups_missing = set(kw["all_groups"]) - set(kw["pilot_groups"])
    lines += [
        "",
        "## 6. 是否建议进入培训阶段",
    ]

    if groups_missing:
        lines.append(f"⚠️ 以下 group 未被试编码覆盖: {', '.join(sorted(groups_missing))}")
        lines.append("建议补充这些 group 的样本后再进入培训。")
    elif kw["pilot_n"] < 5:
        lines.append("⚠️ 试编码样本过少 (<5)，建议增加样本。")
    else:
        lines.append("✅ 可以进入培训阶段。")

    if groups_missing or kw["pilot_n"] < 5:
        lines += [
            "",
            "## 7. 补样建议",
        ]
        if groups_missing:
            lines.append(f"- 从以下 group 各抽取 2-3 个样本: {', '.join(sorted(groups_missing))}")
        if kw["short_text_pilot"] == 0 and kw["short_text_all"] > 0:
            lines.append(f"- 增加 {min(3, kw['short_text_all'])} 个极短文本样本")
        if kw["missing_ctx_pilot"] == 0 and kw["missing_ctx_all"] > 0:
            lines.append(f"- 增加 {min(3, kw['missing_ctx_all'])} 个缺上下文样本")

    return "\n".join(lines)
