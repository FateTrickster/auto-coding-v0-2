"""Phase 1 — Review standardized codebook: 12-field schema, list[str] content, strict gating."""

from __future__ import annotations

import json
from pathlib import Path

import yaml

from .codebook_schema import (
    REQUIRED_FIELDS, STRING_FIELDS, LIST_FIELDS, EXPECTED_CODE_IDS,
)

# Review-specific critical fields for training gate
CRITICAL_FIELDS = {"definition", "inclusion_rules", "exclusion_rules", "boundary_cases"}


def review(codebook_yaml_path: str | Path, out_dir: str | Path) -> dict:
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    # ── Load ──────────────────────────────────────────────
    try:
        with open(codebook_yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except Exception as e:
        return _fail(f"YAML parse error: {e}", out_dir)

    structural = []
    if not isinstance(data, dict):
        structural.append("Root is not a mapping (dict)")
    codes_raw = data.get("codes") if isinstance(data, dict) else None
    if codes_raw is None:
        structural.append("Missing 'codes' key")
    elif not isinstance(codes_raw, list):
        structural.append(f"'codes' is not a list (got {type(codes_raw).__name__})")
    if structural:
        return _fail("; ".join(structural), out_dir)

    codes = codes_raw or []

    # ── Label structure check ─────────────────────────────
    label_errs = []
    for i, c in enumerate(codes):
        if not isinstance(c, dict):
            label_errs.append(f"codes[{i}] is not a dict")

    code_ids = [c.get("code_id") for c in codes if isinstance(c, dict)]
    dup = len(code_ids) != len(set(code_ids))
    missing_ids = set(EXPECTED_CODE_IDS) - set(code_ids)
    extra = set(code_ids) - set(EXPECTED_CODE_IDS)
    ordered = code_ids == EXPECTED_CODE_IDS

    if label_errs:
        return _fail("; ".join(label_errs), out_dir)

    # ── Per-code field validation ─────────────────────────
    all_results = []
    field_stats = {f: {"missing": 0, "invalid_type": 0, "empty": 0, "blank_items": 0}
                   for f in REQUIRED_FIELDS}
    problem = 0

    for code in codes:
        cid = code.get("code_id", "?")
        issues = []

        # Unknown fields
        unknown = {k for k in code.keys() if k not in REQUIRED_FIELDS}
        for uf in sorted(unknown):
            issues.append({"field": uf, "issue_type": "unknown_field",
                           "message": f"Unknown field: {uf}"})

        # String fields
        for sf in STRING_FIELDS:
            val = code.get(sf)
            if val is None:
                issues.append({"field": sf, "issue_type": "missing_field", "message": f"{sf} is missing"})
                field_stats[sf]["missing"] += 1
            elif not isinstance(val, str):
                issues.append({"field": sf, "issue_type": "invalid_type",
                               "message": f"{sf} is {type(val).__name__}, expected str"})
                field_stats[sf]["invalid_type"] += 1
            elif not val.strip():
                issues.append({"field": sf, "issue_type": "empty_field", "message": f"{sf} is empty"})
                field_stats[sf]["empty"] += 1

        # List fields
        for lf in LIST_FIELDS:
            val = code.get(lf)
            if val is None:
                issues.append({"field": lf, "issue_type": "missing_field", "message": f"{lf} is missing"})
                field_stats[lf]["missing"] += 1
            elif not isinstance(val, list):
                issues.append({"field": lf, "issue_type": "invalid_type",
                               "message": f"{lf} is {type(val).__name__}, expected list"})
                field_stats[lf]["invalid_type"] += 1
            elif len(val) == 0:
                issues.append({"field": lf, "issue_type": "empty_field", "message": f"{lf} is empty list"})
                field_stats[lf]["empty"] += 1
            else:
                for j, item in enumerate(val):
                    if not isinstance(item, str):
                        issues.append({"field": lf, "issue_type": "blank_item", "item_index": j,
                                       "message": f"{lf}[{j}] is not a string"})
                        field_stats[lf]["blank_items"] += 1
                    elif not item.strip():
                        issues.append({"field": lf, "issue_type": "blank_item", "item_index": j,
                                       "message": f"{lf}[{j}] is blank"})
                        field_stats[lf]["blank_items"] += 1

        # Severity
        has_crit = any(i["field"] in CRITICAL_FIELDS
                       and i["issue_type"] in ("missing_field", "invalid_type", "empty_field")
                       for i in issues)
        has_field_err = any(i["issue_type"] in ("missing_field", "invalid_type", "empty_field")
                            for i in issues)
        has_item_err = any(i["issue_type"] == "blank_item" for i in issues)
        severity = "critical" if has_crit else ("high" if has_field_err else
                                                ("medium" if has_item_err else "good"))
        if severity != "good":
            problem += 1
        all_results.append({"code_id": cid, "severity": severity, "issues": issues})

    # ── Gate ──────────────────────────────────────────────
    has_unknown = any(
        any(i["issue_type"] == "unknown_field" for i in cr["issues"])
        for cr in all_results)
    all_zero = all(v == 0 for f in field_stats.values() for v in f.values())
    schema_ok = (not dup and not missing_ids and not extra and ordered
                 and not structural and all_zero and not has_unknown)
    crit_ok = all(
        field_stats.get(f, {}).get("missing", 0) == 0
        and field_stats.get(f, {}).get("invalid_type", 0) == 0
        and field_stats.get(f, {}).get("empty", 0) == 0
        for f in CRITICAL_FIELDS)
    can_proceed = schema_ok and crit_ok

    # ── Outputs ───────────────────────────────────────────
    result = {
        "schema_version": "v0.1", "expected_code_ids": EXPECTED_CODE_IDS,
        "required_fields": REQUIRED_FIELDS,
        "summary": {"total_codes": len(codes), "valid_codes": len(codes) - problem,
                    "problem_codes": problem, "schema_valid": schema_ok,
                    "can_proceed_to_training": can_proceed},
        "field_statistics": field_stats, "codes": all_results,
    }

    # JSON
    jt = out_dir / "codebook_missing_fields.json.tmp"
    jp = out_dir / "codebook_missing_fields.json"
    with open(jt, "w", encoding="utf-8") as f: json.dump(result, f, ensure_ascii=False, indent=2)
    jt.replace(jp)

    # Markdown
    mt = out_dir / "codebook_review_report_v0.1.md.tmp"
    mp = out_dir / "codebook_review_report_v0.1.md"
    mt.write_text(_report(result), encoding="utf-8")
    mt.replace(mp)

    return {"missing_json_path": str(jp), "report_path": str(mp),
            "can_proceed": can_proceed, "total_codes": len(codes)}


def _fail(reason: str, out_dir: Path) -> dict:
    """Write failure without overwriting existing valid outputs."""
    fp = out_dir / "codebook_review_report_v0.1.md"
    fj = out_dir / "codebook_missing_fields.json"
    if not fp.exists(): fp.write_text(f"# FAILED\n\n{reason}\n", encoding="utf-8")
    if not fj.exists(): fj.write_text(json.dumps({"error": reason}, ensure_ascii=False, indent=2))
    return {"can_proceed": False, "total_codes": 0, "error": reason}


def _report(r: dict) -> str:
    s = r["summary"]; fs = r["field_statistics"]
    lines = [
        "# Codebook Review Report v0.1", "",
        "## 1. 总体情况",
        f"- 预期标签: {len(EXPECTED_CODE_IDS)} ({', '.join(EXPECTED_CODE_IDS)})",
        f"- 实际标签: {s['total_codes']}",
        f"- 有效标签: {s['valid_codes']}",
        f"- 问题标签: {s['problem_codes']}",
        f"- Schema 有效: {'是' if s['schema_valid'] else '**否**'}",
        f"- 可进入培训: {'是' if s['can_proceed_to_training'] else '**否**'}",
        "", "## 2. 标签结构检查",
        f"- ID 完整: {'是' if s['total_codes'] == 4 else '否'}",
        "- 无重复: 是", "- 顺序正确: 是", "- 无未知标签: 是",
        "", "## 3. 字段完整性统计", "",
        "| 字段 | 缺失 | 类型错误 | 空字段 | 空白项 |",
        "|------|------|---------|--------|--------|",
    ]
    for fn in REQUIRED_FIELDS:
        st = fs.get(fn, {})
        lines.append(f"| {fn} | {st.get('missing',0)} | {st.get('invalid_type',0)} | {st.get('empty',0)} | {st.get('blank_items',0)} |")
    lines += ["", "## 4. 各代码问题", ""]
    for cr in r["codes"]:
        lines.append(f"### {cr['code_id']} (severity: {cr['severity']})")
        if cr["issues"]:
            for i in cr["issues"]:
                lines.append(f"- [{i['issue_type']}] {i['message']}")
        else:
            lines.append("- 未发现字段问题。")
        lines.append("")
    lines += [
        "## 5. 边界字段完整性",
        "- boundary_cases / exclusion_rules / counter_markers: 已检查字段存在性",
        "- 此处仅检查字段完整性，不评价规则内容质量。",
        "", "## 6. 是否进入培训",
    ]
    if s["can_proceed_to_training"]:
        lines.append("**可以进入培训阶段。**")
    else:
        lines.append("**不能进入培训阶段。**")
        for cr in r["codes"]:
            for i in cr["issues"]:
                lines.append(f"- {cr['code_id']}.{i['field']}: {i['message']}")
    return "\n".join(lines)
