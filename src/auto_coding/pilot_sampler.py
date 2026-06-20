"""Phase 1 — PilotSampler: config-driven stratified sampling.

A *generic* sampling executor. Contains NO domain keywords, label semantics,
or project-specific boundary expressions. All project-level risk knowledge
comes from an optional YAML config file or pre-existing risk_flags in the
input unit table.

Three-pool design:
  Pool 1 (70%): group-stratified random
  Pool 2 (20%): codebook stress-test samples
    - existing risk_flags
    - configured boundary_patterns
    - generic structural difficulty markers
  Pool 3 (10%): control-group oversampling (optional)

Pure rule-based, no LLM calls. Deterministic given the same inputs, config, and seed.
"""

from __future__ import annotations

import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

# ── Generic helpers (no domain knowledge) ───────────────────────

MEANINGLESS_RISK_VALS = {"", "none", "null", "nan", "[]", "{}", "false", "0"}

TRUE_VALUES = {"true", "1", "yes", "y"}


def _is_meaningful_risk(val: str | None) -> bool:
    """Return True if the risk_flags value carries real risk information."""
    if val is None:
        return False
    return val.strip().lower() not in MEANINGLESS_RISK_VALS


def _char_len(text: str) -> int:
    """Character count after stripping."""
    return len(text.strip())


def _parse_bool(val: str | None) -> bool:
    """Parse a boolean-like string value."""
    if val is None:
        return False
    return val.strip().lower() in TRUE_VALUES


# ── Config loading ──────────────────────────────────────────────

def _load_risk_config(path: Path | None) -> dict:
    """Load and validate risk config YAML. Returns default config if path is None."""
    if path is None:
        return {
            "_is_default": True,
            "_path": None,
            "risk_sampling": {
                "enabled": True,
                "use_existing_risk_flags": True,
                "boundary_patterns": [],
            },
            "generic_difficulty": {
                "short_text_max_length": None,
                "include_missing_context": True,
                "include_possible_multi_function": True,
            },
            "control_sampling": {"group_ids": []},
        }

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Risk config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Risk config must be a YAML mapping, got {type(raw).__name__}")

    rs = raw.get("risk_sampling", {})
    gd = raw.get("generic_difficulty", {})
    cs = raw.get("control_sampling", {})

    # Validate boundary_patterns
    boundary_patterns = rs.get("boundary_patterns", [])
    if boundary_patterns is None:
        boundary_patterns = []
    for bp in boundary_patterns:
        if not bp.get("pattern", "").strip():
            raise ValueError("boundary_patterns entries must have a non-empty 'pattern'")

    # Validate short_text_max_length
    stml = gd.get("short_text_max_length")
    if stml is not None:
        if not isinstance(stml, int) or stml < 0:
            raise ValueError(
                f"short_text_max_length must be a non-negative int or null, got {stml!r}"
            )

    return {
        "_is_default": False,
        "_path": str(path),
        "risk_sampling": {
            "enabled": rs.get("enabled", True),
            "use_existing_risk_flags": rs.get("use_existing_risk_flags", True),
            "boundary_patterns": boundary_patterns,
        },
        "generic_difficulty": {
            "short_text_max_length": stml,
            "include_missing_context": gd.get("include_missing_context", True),
            "include_possible_multi_function": gd.get("include_possible_multi_function", True),
        },
        "control_sampling": {
            "group_ids": cs.get("group_ids", []) or [],
        },
    }


# ── Unit table loading & validation ────────────────────────────

def _load_and_validate(unit_table_path: Path) -> list[dict]:
    """Load unit_table_v0.1.csv, validate, return valid rows (no empty unit_text)."""
    if not unit_table_path.exists():
        raise FileNotFoundError(f"Unit table not found: {unit_table_path}")

    with open(unit_table_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)

    required = {"unit_id", "group_id", "speaker_id", "unit_text"}
    available = set(reader.fieldnames or [])
    missing = required - available
    if missing:
        raise ValueError(f"Missing required fields in {unit_table_path}: {sorted(missing)}")

    seen_ids: set[str] = set()
    dup_ids: set[str] = set()
    valid_rows: list[dict] = []
    for row in all_rows:
        uid = (row.get("unit_id") or "").strip()
        if not uid:
            raise ValueError("Found empty unit_id in input")
        if uid in seen_ids:
            dup_ids.add(uid)
        else:
            seen_ids.add(uid)
            text = (row.get("unit_text") or "").strip()
            if text:
                valid_rows.append(row)
    if dup_ids:
        raise ValueError(f"Duplicate unit_id(s) found: {sorted(dup_ids)}")
    return valid_rows


# ── Pool helpers ────────────────────────────────────────────────

def _sample_group_stratified(
    valid_rows: list[dict], pool1_target: int, rng: random.Random
) -> tuple[list[dict], set[str]]:
    """Pool 1: group-stratified random sampling."""
    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in valid_rows:
        gid = (row.get("group_id") or "").strip()
        by_group[gid].append(row)

    nonempty_groups = [g for g, rows in by_group.items() if rows]
    n_groups = len(nonempty_groups)
    total_valid = len(valid_rows)

    group_quotas: dict[str, int] = {}
    remaining_quota = pool1_target

    if pool1_target >= n_groups:
        for g in nonempty_groups:
            group_quotas[g] = 1
        remaining_quota -= n_groups

    if remaining_quota > 0:
        for g in nonempty_groups:
            g_total = len(by_group[g])
            extra = round(remaining_quota * g_total / total_valid)
            group_quotas[g] = group_quotas.get(g, 0) + extra

    # Clamp and redistribute
    unused_quota = 0
    actual_pool1 = 0
    for g in nonempty_groups:
        quota = min(group_quotas.get(g, 0), len(by_group[g]))
        if quota < group_quotas.get(g, 0):
            unused_quota += group_quotas[g] - quota
        group_quotas[g] = quota
        actual_pool1 += quota

    while unused_quota > 0:
        candidates = [g for g in nonempty_groups if group_quotas.get(g, 0) < len(by_group[g])]
        if not candidates:
            break
        per_group = max(1, unused_quota // len(candidates))
        for g in candidates:
            add = min(per_group, len(by_group[g]) - group_quotas.get(g, 0), unused_quota)
            if add > 0:
                group_quotas[g] = group_quotas.get(g, 0) + add
                unused_quota -= add

    # Sample within each group
    selected: list[dict] = []
    for g in nonempty_groups:
        quota = group_quotas.get(g, 0)
        group_rows = by_group[g]
        if quota >= len(group_rows):
            sampled = list(group_rows)
        else:
            sampled = rng.sample(group_rows, quota)
        for row in sampled:
            row["_sample_reason"] = "group_stratified"
            selected.append(row)

    selected_ids = {(r.get("unit_id") or "").strip() for r in selected}
    return selected, selected_ids


def _is_generic_difficulty(row: dict, config: dict) -> bool:
    """Check if row qualifies as a generic structural difficulty sample.

    Uses only structural flags (short_text, missing_context, multi_function),
    NOT domain keywords.
    """
    gd = config.get("generic_difficulty", {})

    # A. Short text
    st_flag = _parse_bool(row.get("short_text_flag"))
    stml = gd.get("short_text_max_length")
    if st_flag or (stml is not None and _char_len(row.get("unit_text", "")) <= stml):
        return True

    # B. Missing context
    if gd.get("include_missing_context", True):
        mc_flag = _parse_bool(row.get("missing_context_flag"))
        if mc_flag:
            return True
        # Fallback: derive from context_before/context_after
        if "missing_context_flag" not in row:
            ctx_before = (row.get("context_before") or "").strip()
            ctx_after = (row.get("context_after") or "").strip()
            if not ctx_before and not ctx_after:
                return True

    # C. Possible multi-function
    if gd.get("include_possible_multi_function", True):
        pmf_flag = _parse_bool(
            row.get("possible_multi_function_flag")
            or row.get("possible_multi_function")
        )
        if pmf_flag:
            return True

    return False


def _hits_configured_boundary(text: str, config: dict) -> tuple[bool, str | None, str | None]:
    """Check if text matches any configured boundary pattern.

    Returns (matched, risk_type, source).
    """
    rs = config.get("risk_sampling", {})
    patterns = rs.get("boundary_patterns", [])
    if not patterns:
        return False, None, None

    t = text.strip()
    t_lower = t.lower()
    for bp in patterns:
        pat = (bp.get("pattern") or "").strip()
        if not pat:
            continue
        if pat in t or pat.lower() in t_lower:
            return True, bp.get("risk_type"), bp.get("source")
    return False, None, None


def _sample_pool2_stress_test(
    remaining_rows: list[dict], pool2_target: int, config: dict, rng: random.Random
) -> tuple[list[dict], set[str], dict[str, int]]:
    """Pool 2: codebook stress-test samples.

    Priority:
      1. existing risk_flags -> high_risk_existing
      2. configured boundary_patterns -> high_risk_boundary
      3. generic structural difficulty -> high_risk_difficulty
    """
    rs = config.get("risk_sampling", {})
    if not rs.get("enabled", True):
        return [], set(), {}

    use_existing = rs.get("use_existing_risk_flags", True)
    patterns = rs.get("boundary_patterns", [])

    # Build per-priority candidate lists
    p1 = []  # high_risk_existing
    p2 = []  # high_risk_boundary
    p3 = []  # high_risk_difficulty

    for row in remaining_rows:
        text = (row.get("unit_text") or "").strip()
        uid = (row.get("unit_id") or "").strip()

        if use_existing and _is_meaningful_risk(row.get("risk_flags")):
            p1.append(row)
        elif patterns:
            matched, risk_type, source = _hits_configured_boundary(text, config)
            if matched:
                row["_matched_risk_type"] = risk_type
                row["_matched_pattern_source"] = source
                p2.append(row)
                continue

        if _is_generic_difficulty(row, config):
            p3.append(row)

    # Shuffle within priority (seed-controlled)
    rng.shuffle(p1)
    rng.shuffle(p2)
    rng.shuffle(p3)

    selected: list[dict] = []
    selected_ids: set[str] = set()

    def _add(candidates: list[dict], reason: str):
        nonlocal selected, selected_ids
        for row in candidates:
            if len(selected) >= pool2_target:
                break
            uid = (row.get("unit_id") or "").strip()
            if uid in selected_ids:
                continue
            row["_sample_reason"] = reason
            selected.append(row)
            selected_ids.add(uid)

    _add(p1, "high_risk_existing")
    _add(p2, "high_risk_boundary")
    _add(p3, "high_risk_difficulty")

    counts = {
        "high_risk_existing": sum(1 for r in selected if r.get("_sample_reason") == "high_risk_existing"),
        "high_risk_boundary": sum(1 for r in selected if r.get("_sample_reason") == "high_risk_boundary"),
        "high_risk_difficulty": sum(1 for r in selected if r.get("_sample_reason") == "high_risk_difficulty"),
    }
    return selected, selected_ids, counts


def _sample_pool3_control(
    remaining_rows: list[dict],
    pool3_target: int,
    control_group: str | None,
    config: dict,
    rng: random.Random,
) -> tuple[list[dict], set[str], str | None]:
    """Pool 3: control-group oversampling (optional)."""
    # Resolve control group priority: function arg > YAML config
    resolved = control_group
    if not resolved:
        cs = config.get("control_sampling", {})
        group_ids = cs.get("group_ids", []) or []
        if group_ids:
            resolved = str(group_ids[0]).strip()

    if not resolved:
        return [], set(), None

    resolved_norm = resolved.strip()
    candidates = [
        r for r in remaining_rows
        if str(r.get("group_id", "")).strip().casefold() == resolved_norm.casefold()
    ]
    rng.shuffle(candidates)

    selected: list[dict] = []
    selected_ids: set[str] = set()
    for row in candidates:
        if len(selected) >= pool3_target:
            break
        uid = (row.get("unit_id") or "").strip()
        if uid in selected_ids:
            continue
        row["_sample_reason"] = "control_group"
        selected.append(row)
        selected_ids.add(uid)

    return selected, selected_ids, resolved


# ── Main entry point ─────────────────────────────────────────────

def sample(
    unit_table_path: str | Path,
    out_dir: str | Path,
    target_size: int = 300,
    seed: int = 42,
    risk_config_path: str | Path | None = None,
    control_group: str | None = None,
) -> dict[str, Any]:
    """Config-driven stratified sampling from unit_table_v0.1.csv.

    Args:
        unit_table_path: Path to unit_table_v0.1.csv (validated, enhanced).
        out_dir: Output directory (typically 04_pilot/).
        target_size: Desired number of pilot units.
        seed: Random seed for reproducibility.
        risk_config_path: Optional YAML config for boundary patterns and difficulty rules.
        control_group: Optional group_id for control-group oversampling.
                        Overrides YAML control_sampling.group_ids.

    Returns:
        Dict with sampling stats and output paths.
    """
    unit_table_path = Path(unit_table_path)
    out_dir = Path(out_dir)

    # ── Validation ──────────────────────────────────────────
    if target_size <= 0:
        raise ValueError(f"target_size must be > 0, got {target_size}")

    # ── Load config ─────────────────────────────────────────
    config = _load_risk_config(Path(risk_config_path) if risk_config_path else None)
    rs = config.get("risk_sampling", {})
    pool2_enabled = rs.get("enabled", True)

    # ── Load & validate unit table ──────────────────────────
    valid_rows = _load_and_validate(unit_table_path)
    input_count = len(valid_rows)

    # ── Full-set scenario ───────────────────────────────────
    rng = random.Random(seed)
    if input_count <= target_size:
        for row in valid_rows:
            row["_sample_reason"] = "full_population"
        return _build_output(
            valid_rows, out_dir, target_size, input_count, seed,
            config, None, {}, rng,
        )

    # ── Pool targets ────────────────────────────────────────
    pool1_target = round(target_size * 0.70)
    pool2_target = round(target_size * 0.20)
    pool3_target = target_size - pool1_target - pool2_target

    # ── Pool 1: group-stratified ────────────────────────────
    p1_selected, p1_ids = _sample_group_stratified(valid_rows, pool1_target, rng)

    # ── Pool 2: stress test ─────────────────────────────────
    remaining = [r for r in valid_rows
                 if (r.get("unit_id") or "").strip() not in p1_ids]
    p2_selected, p2_ids, p2_counts = _sample_pool2_stress_test(
        remaining, pool2_target, config, rng
    ) if pool2_enabled else ([], set(), {})

    # ── Pool 3: control group ───────────────────────────────
    remaining = [r for r in valid_rows
                 if (r.get("unit_id") or "").strip() not in p1_ids
                 and (r.get("unit_id") or "").strip() not in p2_ids]
    p3_selected, p3_ids, resolved_control = _sample_pool3_control(
        remaining, pool3_target, control_group, config, rng,
    )

    # ── Final random fill ───────────────────────────────────
    all_selected_ids = p1_ids | p2_ids | p3_ids
    all_selected = p1_selected + p2_selected + p3_selected
    current_count = len(all_selected)

    if current_count < target_size:
        remaining = [r for r in valid_rows
                     if (r.get("unit_id") or "").strip() not in all_selected_ids]
        needed = target_size - current_count
        if needed >= len(remaining):
            fill_rows = list(remaining)
        else:
            fill_rows = rng.sample(remaining, needed)
        for row in fill_rows:
            uid = (row.get("unit_id") or "").strip()
            if uid not in all_selected_ids:
                row["_sample_reason"] = "random_fill"
                all_selected.append(row)
                all_selected_ids.add(uid)

    # ── Preserve Pool order in output ───────────────────────
    ordered_reasons = [
        "group_stratified", "high_risk_existing", "high_risk_boundary",
        "high_risk_difficulty", "control_group", "random_fill",
    ]
    final_selected: list[dict] = []
    seen_final: set[str] = set()
    for reason in ordered_reasons:
        for row in all_selected:
            uid = (row.get("unit_id") or "").strip()
            if row.get("_sample_reason") == reason and uid not in seen_final:
                final_selected.append(row)
                seen_final.add(uid)
    # Any strays
    for row in all_selected:
        uid = (row.get("unit_id") or "").strip()
        if uid not in seen_final:
            final_selected.append(row)
            seen_final.add(uid)

    # ── Build output ────────────────────────────────────────
    return _build_output(
        final_selected, out_dir, target_size, input_count, seed,
        config, resolved_control, p2_counts, rng,
    )


# ── Output ──────────────────────────────────────────────────────

def _build_output(
    selected: list[dict],
    out_dir: Path,
    target_size: int,
    input_count: int,
    seed: int,
    config: dict,
    resolved_control: str | None,
    p2_counts: dict[str, int],
    rng: random.Random,
) -> dict[str, Any]:
    """Write CSV and report, return stats dict."""
    out_dir.mkdir(parents=True, exist_ok=True)

    # ── CSV ─────────────────────────────────────────────────
    csv_fields = ["unit_id", "group_id", "speaker_id", "unit_text", "risk_flags", "sample_reason"]
    csv_path = out_dir / "pilot_sample_units.csv"
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        writer.writeheader()
        for row in selected:
            out_row = {
                "unit_id": (row.get("unit_id") or "").strip(),
                "group_id": (row.get("group_id") or "").strip(),
                "speaker_id": (row.get("speaker_id") or "").strip(),
                "unit_text": (row.get("unit_text") or "").strip(),
                "risk_flags": (row.get("risk_flags") or "").strip(),
                "sample_reason": row.get("_sample_reason", ""),
            }
            writer.writerow(out_row)

    # ── Stats ───────────────────────────────────────────────
    sampled_count = len(selected)
    groups = set((r.get("group_id") or "").strip() for r in selected)
    speakers = set((r.get("speaker_id") or "").strip() for r in selected)

    reason_counts = Counter(r.get("_sample_reason", "") for r in selected)

    # High-risk count: all pool2 reasons + pool1/pool3/fill rows with risk_flags
    high_risk_count = (
        reason_counts.get("high_risk_existing", 0)
        + reason_counts.get("high_risk_boundary", 0)
        + reason_counts.get("high_risk_difficulty", 0)
    )
    # Also count any other rows that have risk_flags
    high_risk_count += sum(
        1 for r in selected
        if r.get("_sample_reason") not in (
            "high_risk_existing", "high_risk_boundary", "high_risk_difficulty"
        )
        and _is_meaningful_risk(r.get("risk_flags"))
    )

    control_count = reason_counts.get("control_group", 0)

    short_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) <= 10)
    long_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) >= 100)

    # ── Report ──────────────────────────────────────────────
    report_path = out_dir / "pilot_sample_build_report.md"
    rs = config.get("risk_sampling", {})
    gd = config.get("generic_difficulty", {})

    report_lines = [
        "# Pilot Sample Build Report",
        "",
        "## 1. 基本统计",
        f"- 输入有效记录数: {input_count}",
        f"- 目标样本数: {target_size}",
        f"- 实际抽样数: {sampled_count}",
        f"- 随机种子: {seed}",
        f"- 全量选取: {'是' if input_count <= target_size else '否'}",
        "",
        "## 2. 配置说明",
        f"- 风险配置文件: {_config_path_str(config)}",
        f"- 风险抽样启用: {rs.get('enabled', True)}",
        f"- 使用已有 risk_flags: {rs.get('use_existing_risk_flags', True)}",
        f"- boundary_patterns 数量: {len(rs.get('boundary_patterns', []))}",
        f"- short_text_max_length: {gd.get('short_text_max_length')}",
        f"- 检查 missing context: {gd.get('include_missing_context', True)}",
        f"- 检查 possible multi-function: {gd.get('include_possible_multi_function', True)}",
        f"- 对照组: {resolved_control or '(未指定)'}",
    ]

    if config.get("_is_default", False):
        report_lines += [
            "",
            "> ⚠️ 未提供项目级边界规则。",
            "> Pool 2 仅使用已有 risk_flags 和可用的通用结构困难标记。",
        ]
    if resolved_control is None:
        report_lines += [
            "",
            "> ⚠️ 未指定对照组，跳过 Pool 3，其配额由最终随机补齐。",
        ]
    if resolved_control and control_count == 0:
        report_lines += [
            "",
            f"> ⚠️ 对照组 `{resolved_control}` 在数据中无匹配记录，Pool 3 数量为 0。",
        ]

    report_lines += [
        "",
        "## 3. Pool 构成",
        f"- group_stratified: {reason_counts.get('group_stratified', 0)}",
        f"- high_risk_existing: {reason_counts.get('high_risk_existing', 0)}",
        f"- high_risk_boundary: {reason_counts.get('high_risk_boundary', 0)}",
        f"- high_risk_difficulty: {reason_counts.get('high_risk_difficulty', 0)}",
        f"- control_group: {control_count}",
        f"- random_fill: {reason_counts.get('random_fill', 0)}",
    ]
    if reason_counts.get("full_population", 0) > 0:
        report_lines.append(f"- full_population: {reason_counts['full_population']}")

    report_lines += [
        "",
        "## 4. 覆盖统计",
        f"- group 覆盖: {len(groups)}",
        f"- speaker 覆盖: {len(speakers)}",
        "",
        "### 各 group 样本数量",
    ]

    def _group_sort_key(g: str) -> tuple:
        nums = re.findall(r"\d+", g)
        return (int(nums[0]), g) if nums else (9999, g)

    group_counts = Counter((r.get("group_id") or "").strip() for r in selected)
    for g in sorted(group_counts, key=_group_sort_key):
        report_lines.append(f"- {g}: {group_counts[g]}")

    report_lines += [
        "",
        "## 5. 文本长度统计",
        f"- 短文本（≤10 字）: {short_count}",
        f"- 长文本（≥100 字）: {long_count}",
        "",
        "## 6. 风险和对照统计",
        f"- 有效 risk_flags 样本: {reason_counts.get('high_risk_existing', 0)}",
        f"- 命中 boundary_pattern: {reason_counts.get('high_risk_boundary', 0)}",
        f"- 结构困难样本: {reason_counts.get('high_risk_difficulty', 0)}",
        f"- 对照组样本: {control_count}",
    ]

    report_path.write_text("\n".join(report_lines), encoding="utf-8")

    return {
        "input_count": input_count,
        "target_size": target_size,
        "sampled_count": sampled_count,
        "groups_covered": len(groups),
        "speakers_covered": len(speakers),
        "high_risk_count": high_risk_count,
        "control_group_count": control_count,
        "risk_config_used": not config.get("_is_default", False),
        "control_group": resolved_control,
        "output_path": str(csv_path),
        "report_path": str(report_path),
    }


def _config_path_str(config: dict) -> str:
    """Return a human-readable config path string."""
    path = config.get("_path")
    if path:
        return str(path)
    if config.get("_is_default"):
        return "(内置默认)"
    return "(未提供)"
