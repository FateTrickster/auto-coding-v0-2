"""Phase 1 — PilotSampler: stratified sampling from validated unit table.

Round 1 (default, no risk_config_path):
  Uses only real structural fields from unit_table_v0.1.csv.
  Pool 1: group_stratified (with speaker spread + order bucketing)
  Pool 2: structural difficulty (short_text, long_text, missing_context, multi_function)
  Pool 3: optional control_group oversampling
  Fill:   random_fill

Round 2+ (with risk_config_path):
  Pool 2 additionally supports explicit_units from previous round disagreements.
  confusion_pairs and boundary_patterns are recorded in the report but NOT used
  for text matching on un-coded samples.

Contains NO domain keywords, label semantics, or project-specific boundary expressions.
"""

from __future__ import annotations

import csv
import random
import re
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import yaml

# ── Generic helpers ─────────────────────────────────────────────

MEANINGLESS_RISK_VALS = {"", "none", "null", "nan", "[]", "{}", "false", "0"}
TRUE_VALUES = {"true", "1", "yes", "y"}


def _is_meaningful_risk(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() not in MEANINGLESS_RISK_VALS


def _char_len(text: str) -> int:
    return len(text.strip())


def _parse_bool(val: str | None) -> bool:
    if val is None:
        return False
    return val.strip().lower() in TRUE_VALUES


def _norm_group(val) -> str:
    return str(val or "").strip()


# ── Config loading ──────────────────────────────────────────────

def _load_risk_config(path: Path | None) -> dict:
    """Load optional risk config for Round 2+. Returns None markers for Round 1."""
    if path is None:
        return {
            "_is_round01": True,
            "explicit_units": [],
            "confusion_pairs": [],
            "boundary_patterns": [],
            "control_sampling": {"group_ids": []},
        }

    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"Risk config not found: {path}")

    with open(path, "r", encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        raise ValueError(f"Risk config must be a YAML mapping, got {type(raw).__name__}")

    explicit = raw.get("explicit_units", []) or []
    confusion = raw.get("confusion_pairs", []) or []
    boundary = raw.get("boundary_patterns", []) or []

    # Validate explicit_units
    for eu in explicit:
        if not eu.get("unit_id", "").strip():
            raise ValueError("explicit_units entries must have non-empty unit_id")
        if "evidence_ids" not in eu:
            eu["evidence_ids"] = []
        if "status" not in eu:
            eu["status"] = "candidate"

    for bp in boundary:
        if not bp.get("pattern", "").strip():
            raise ValueError("boundary_patterns entries must have non-empty pattern")
        if "evidence_ids" not in bp:
            bp["evidence_ids"] = []
        if "status" not in bp:
            bp["status"] = "candidate"

    return {
        "_is_round01": False,
        "_path": str(path),
        "source_round_id": raw.get("source_round_id", ""),
        "target_round_id": raw.get("target_round_id", ""),
        "explicit_units": explicit,
        "confusion_pairs": confusion,
        "boundary_patterns": boundary,
        "control_sampling": raw.get("control_sampling", {}) or {},
    }


# ── Unit table loading ──────────────────────────────────────────

def _load_and_validate(unit_table_path: Path) -> list[dict]:
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


# ── Pool 1: group_stratified ────────────────────────────────────

def _sample_group_stratified(
    valid_rows: list[dict], pool1_target: int, rng: random.Random
) -> tuple[list[dict], set[str], int]:
    """Pool 1: group-stratified random. Within each group, spread across speakers
    and time-order buckets when relevant fields exist."""

    by_group: dict[str, list[dict]] = defaultdict(list)
    for row in valid_rows:
        gid = _norm_group(row.get("group_id"))
        by_group[gid].append(row)

    nonempty_groups = [g for g, rows in by_group.items() if rows]
    n_groups = len(nonempty_groups)
    total_valid = len(valid_rows)

    # ── Quotas ─────────────────────────────────────────────
    group_quotas: dict[str, int] = {}
    remaining_quota = pool1_target

    if pool1_target >= n_groups > 0:
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
    for g in nonempty_groups:
        quota = min(group_quotas.get(g, 0), len(by_group[g]))
        if quota < group_quotas.get(g, 0):
            unused_quota += group_quotas[g] - quota
        group_quotas[g] = quota

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

    # ── Within-group sampling with speaker spread + order bucketing ─
    selected: list[dict] = []
    speaker_spread_count = 0

    for g in nonempty_groups:
        quota = group_quotas.get(g, 0)
        group_rows = by_group[g]
        if quota >= len(group_rows):
            sampled = list(group_rows)
        else:
            sampled = _sample_within_group(group_rows, quota, rng)

        for row in sampled:
            row["_sample_reason"] = "group_stratified"
            selected.append(row)

    selected_ids = {(r.get("unit_id") or "").strip() for r in selected}
    return selected, selected_ids, speaker_spread_count


def _sample_within_group(
    group_rows: list[dict], quota: int, rng: random.Random
) -> list[dict]:
    """Sample within a group, spreading across speakers and temporal order.

    Strategy:
    1. Build per-speaker pools
    2. Bucket by position (turn_id / source_row_id) if field exists
    3. Round-robin across speakers, then within-speaker random
    """

    # ── Per-speaker grouping ──────────────────────────────
    by_speaker: dict[str, list[dict]] = defaultdict(list)
    for row in group_rows:
        sp = _norm_group(row.get("speaker_id") or "speaker_unknown")
        by_speaker[sp].append(row)

    # ── Sort within speaker by position if order fields exist ─
    has_turn = any("turn_id" in r for r in group_rows)
    has_src_row = any("source_row_id" in r for r in group_rows)

    for sp, rows in by_speaker.items():
        if has_turn:
            rows.sort(key=lambda r: _parse_turn_order(r.get("turn_id", "")))
        elif has_src_row:
            rows.sort(key=lambda r: _parse_turn_order(r.get("source_row_id", "")))

    # ── Round-robin across speakers, then fill ────────────
    selected: list[dict] = []
    selected_ids: set[str] = set()
    speakers = list(by_speaker.keys())
    rng.shuffle(speakers)

    # Phase A: round-robin to ensure speaker spread
    idxs = {sp: 0 for sp in speakers}
    while len(selected) < quota:
        added_this_round = False
        for sp in speakers:
            if len(selected) >= quota:
                break
            pool = by_speaker[sp]
            i = idxs[sp]
            while i < len(pool):
                uid = (pool[i].get("unit_id") or "").strip()
                if uid not in selected_ids:
                    selected.append(pool[i])
                    selected_ids.add(uid)
                    idxs[sp] = i + 1
                    added_this_round = True
                    break
                i += 1
                idxs[sp] = i
        if not added_this_round:
            break

    return selected[:quota]


def _parse_turn_order(val: str) -> int:
    """Extract numeric turn order from turn_id / source_row_id string."""
    if not val:
        return 0
    nums = re.findall(r"\d+", str(val))
    return int(nums[-1]) if nums else 0


# ── Pool 2: structural difficulty ───────────────────────────────

def _is_structural_short(row: dict) -> bool:
    if _parse_bool(row.get("short_text_flag")):
        return True
    return _char_len(row.get("unit_text", "")) <= 5


def _is_structural_long(row: dict) -> bool:
    if _parse_bool(row.get("long_text_flag")):
        return True
    return _char_len(row.get("unit_text", "")) >= 120


def _is_structural_missing_context(row: dict) -> bool:
    if _parse_bool(row.get("missing_context_flag")):
        return True
    ctx_before = (row.get("context_before") or "").strip()
    ctx_after = (row.get("context_after") or "").strip()
    return not ctx_before and not ctx_after


def _is_structural_multi_function(row: dict) -> bool:
    flag = row.get("possible_multi_function_flag") or row.get("possible_multi_function")
    return _parse_bool(flag)


def _sample_structural_difficulty(
    remaining_rows: list[dict], pool2_target: int, rng: random.Random
) -> tuple[list[dict], set[str], dict[str, int]]:
    """Pool 2: structural difficulty samples.

    Priority: short_text → long_text → missing_context → multi_function.
    Within each priority, seed-controlled shuffle.
    """

    categories = [
        ("structural_short_text", _is_structural_short),
        ("structural_long_text", _is_structural_long),
        ("structural_missing_context", _is_structural_missing_context),
        ("structural_multi_function", _is_structural_multi_function),
    ]

    selected: list[dict] = []
    selected_ids: set[str] = set()
    counts: dict[str, int] = {}

    for reason, pred in categories:
        candidates = [r for r in remaining_rows
                      if (r.get("unit_id") or "").strip() not in selected_ids and pred(r)]
        rng.shuffle(candidates)
        for row in candidates:
            if len(selected) >= pool2_target:
                break
            uid = (row.get("unit_id") or "").strip()
            if uid in selected_ids:
                continue
            row["_sample_reason"] = reason
            selected.append(row)
            selected_ids.add(uid)
        counts[reason] = sum(1 for r in selected if r.get("_sample_reason") == reason)

    return selected, selected_ids, counts


# ── Pool 2 extension: explicit_units (Round 2+) ─────────────────

def _sample_explicit_units(
    valid_rows: list[dict],
    explicit_units: list[dict],
    already_selected: set[str],
    rng: random.Random,
) -> tuple[list[dict], set[str]]:
    """Select specific unit_ids from risk config (previous round disagreements)."""
    if not explicit_units:
        return [], set()

    target_ids = {eu["unit_id"].strip() for eu in explicit_units if eu.get("unit_id", "").strip()}
    # Build lookup
    row_map = {(r.get("unit_id") or "").strip(): r for r in valid_rows}

    selected: list[dict] = []
    selected_ids: set[str] = set()
    for uid in target_ids:
        if uid in already_selected:
            continue
        if uid in selected_ids:
            continue
        row = row_map.get(uid)
        if row is None:
            continue
        row["_sample_reason"] = "explicit_unit"
        selected.append(row)
        selected_ids.add(uid)

    return selected, selected_ids


# ── Pool 3: control group ───────────────────────────────────────

def _sample_control_group(
    remaining_rows: list[dict],
    pool3_target: int,
    control_group: str | None,
    config: dict,
    rng: random.Random,
) -> tuple[list[dict], set[str], str | None]:
    resolved = control_group
    if not resolved:
        cs = config.get("control_sampling", {}) or {}
        group_ids = cs.get("group_ids", []) or []
        if group_ids:
            resolved = str(group_ids[0]).strip()

    if not resolved:
        return [], set(), None

    resolved_norm = resolved.strip()
    candidates = [r for r in remaining_rows
                  if _norm_group(r.get("group_id")).casefold() == resolved_norm.casefold()]
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
    """Stratified sampling from unit_table_v0.1.csv.

    Round 1 (default): representative sampling + structural difficulty coverage.
    Round 2+ (with risk_config_path): also carries forward explicit_units from
    previous round disagreements.

    Args:
        unit_table_path: Path to unit_table_v0.1.csv.
        out_dir: Output directory (typically 04_pilot/).
        target_size: Desired number of pilot units.
        seed: Random seed for reproducibility.
        risk_config_path: Optional. Risk profile from previous round (Round 2+ only).
        control_group: Optional group_id for control-group oversampling.

    Returns:
        Dict with sampling stats and output paths.
    """
    unit_table_path = Path(unit_table_path)
    out_dir = Path(out_dir)

    if target_size <= 0:
        raise ValueError(f"target_size must be > 0, got {target_size}")

    # ── Load config ─────────────────────────────────────────
    config = _load_risk_config(Path(risk_config_path) if risk_config_path else None)
    is_round01 = config.get("_is_round01", True)
    explicit_units = config.get("explicit_units", [])

    # ── Load & validate ─────────────────────────────────────
    valid_rows = _load_and_validate(unit_table_path)
    input_count = len(valid_rows)
    rng = random.Random(seed)

    # ── Full-set ────────────────────────────────────────────
    if input_count <= target_size:
        for row in valid_rows:
            row["_sample_reason"] = "full_population"
        return _build_output(
            valid_rows, out_dir, target_size, input_count, seed,
            config, None, {}, is_round01, rng,
        )

    # ── Pool targets ────────────────────────────────────────
    pool1_target = round(target_size * 0.70)
    pool2_target = round(target_size * 0.20)
    pool3_target = target_size - pool1_target - pool2_target

    # ── Pool 1 ──────────────────────────────────────────────
    p1_selected, p1_ids, speaker_spread = _sample_group_stratified(valid_rows, pool1_target, rng)

    # ── Pool 2 ──────────────────────────────────────────────
    remaining = [r for r in valid_rows
                 if (r.get("unit_id") or "").strip() not in p1_ids]

    p2_selected: list[dict] = []
    p2_ids: set[str] = set()
    p2_counts: dict[str, int] = {}

    # Round 2+: explicit_units first
    if not is_round01 and explicit_units:
        eu_selected, eu_ids = _sample_explicit_units(
            valid_rows, explicit_units, p1_ids, rng,
        )
        p2_selected.extend(eu_selected)
        p2_ids.update(eu_ids)
        p2_counts["explicit_unit"] = len(eu_selected)

    # Structural difficulty (both Round 1 and Round 2+)
    remaining = [r for r in valid_rows
                 if (r.get("unit_id") or "").strip() not in p1_ids
                 and (r.get("unit_id") or "").strip() not in p2_ids]
    struct_quota = pool2_target - len(p2_selected)
    if struct_quota > 0:
        sd_selected, sd_ids, sd_counts = _sample_structural_difficulty(
            remaining, struct_quota, rng,
        )
        p2_selected.extend(sd_selected)
        p2_ids.update(sd_ids)
        for k, v in sd_counts.items():
            p2_counts[k] = p2_counts.get(k, 0) + v

    # ── Pool 3 ──────────────────────────────────────────────
    remaining = [r for r in valid_rows
                 if (r.get("unit_id") or "").strip() not in p1_ids
                 and (r.get("unit_id") or "").strip() not in p2_ids]
    p3_selected, p3_ids, resolved_control = _sample_control_group(
        remaining, pool3_target, control_group, config, rng,
    )

    # ── Final fill ──────────────────────────────────────────
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

    # ── Order-preserving output ─────────────────────────────
    ordered_reasons = [
        "group_stratified",
        "explicit_unit",
        "structural_short_text",
        "structural_long_text",
        "structural_missing_context",
        "structural_multi_function",
        "control_group",
        "random_fill",
    ]
    final_selected: list[dict] = []
    seen_final: set[str] = set()
    for reason in ordered_reasons:
        for row in all_selected:
            uid = (row.get("unit_id") or "").strip()
            if row.get("_sample_reason") == reason and uid not in seen_final:
                final_selected.append(row)
                seen_final.add(uid)
    for row in all_selected:
        uid = (row.get("unit_id") or "").strip()
        if uid not in seen_final:
            final_selected.append(row)
            seen_final.add(uid)

    return _build_output(
        final_selected, out_dir, target_size, input_count, seed,
        config, resolved_control, p2_counts, is_round01, rng,
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
    is_round01: bool,
    rng: random.Random,
) -> dict[str, Any]:
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
                "group_id": _norm_group(row.get("group_id")),
                "speaker_id": _norm_group(row.get("speaker_id")),
                "unit_text": (row.get("unit_text") or "").strip(),
                "risk_flags": (row.get("risk_flags") or "").strip(),
                "sample_reason": row.get("_sample_reason", ""),
            }
            writer.writerow(out_row)

    # ── Stats ───────────────────────────────────────────────
    sampled_count = len(selected)
    groups = set(_norm_group(r.get("group_id")) for r in selected)
    speakers = set(_norm_group(r.get("speaker_id")) for r in selected)
    reason_counts = Counter(r.get("_sample_reason", "") for r in selected)

    control_count = reason_counts.get("control_group", 0)
    short_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) <= 10)
    long_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) >= 100)

    # Round 2+ info
    explicit_count = reason_counts.get("explicit_unit", 0)
    confusion_pairs = config.get("confusion_pairs", [])

    # ── Report ──────────────────────────────────────────────
    report_path = out_dir / "pilot_sample_build_report.md"
    lines = [
        "# Pilot Sample Build Report",
        "",
        "## 1. 基本统计",
        f"- 输入有效记录数: {input_count}",
        f"- 目标样本数: {target_size}",
        f"- 实际抽样数: {sampled_count}",
        f"- 随机种子: {seed}",
        f"- 全量选取: {'是' if input_count <= target_size else '否'}",
        f"- Round 模式: {'Round 1（代表性抽样 + 结构困难覆盖）' if is_round01 else 'Round 2+（含风险画像）'}",
        "",
    ]

    if not is_round01:
        src = config.get("source_round_id", "?")
        tgt = config.get("target_round_id", "?")
        lines.append(f"## 2. 风险画像信息")
        lines.append(f"- 来源轮次: {src}")
        lines.append(f"- 目标轮次: {tgt}")
        lines.append(f"- 配置文件: {config.get('_path', '(未记录)')}")
        lines.append(f"- explicit_units 带入: {explicit_count}")
        if confusion_pairs:
            lines.append(f"- confusion_pairs（报告信息，不用于抽样匹配）: {len(confusion_pairs)} 对")
            for cp in confusion_pairs:
                codes = cp.get("codes", [])
                cnt = cp.get("disagreement_count", "?")
                lines.append(f"  - {codes}: {cnt} 次分歧")
        lines.append("")

    lines += [
        f"## {3 if not is_round01 else 2}. 对照组",
        f"- 对照组: {resolved_control or '(未指定)'}",
    ]
    if resolved_control is None:
        lines.append("- Pool 3 已跳过，其配额由 random_fill 补齐。")
    elif control_count == 0:
        lines.append(f"- ⚠️ 对照组 `{resolved_control}` 在数据中无匹配记录。")
    lines.append("")

    section = 4 if not is_round01 else 3
    lines += [
        f"## {section}. Pool 构成",
        f"- group_stratified: {reason_counts.get('group_stratified', 0)}",
    ]
    if explicit_count > 0:
        lines.append(f"- explicit_unit: {explicit_count}")
    lines += [
        f"- structural_short_text: {reason_counts.get('structural_short_text', 0)}",
        f"- structural_long_text: {reason_counts.get('structural_long_text', 0)}",
        f"- structural_missing_context: {reason_counts.get('structural_missing_context', 0)}",
        f"- structural_multi_function: {reason_counts.get('structural_multi_function', 0)}",
        f"- control_group: {control_count}",
        f"- random_fill: {reason_counts.get('random_fill', 0)}",
    ]
    if reason_counts.get("full_population", 0) > 0:
        lines.append(f"- full_population: {reason_counts['full_population']}")

    lines += [
        "",
        f"## {section + 1}. 覆盖统计",
        f"- group 覆盖: {len(groups)}",
        f"- speaker 覆盖: {len(speakers)}",
        "",
        "### 各 group 样本数量",
    ]

    def _group_sort_key(g: str) -> tuple:
        nums = re.findall(r"\d+", g)
        return (int(nums[0]), g) if nums else (9999, g)

    group_counts = Counter(_norm_group(r.get("group_id")) for r in selected)
    for g in sorted(group_counts, key=_group_sort_key):
        lines.append(f"- {g}: {group_counts[g]}")

    lines += [
        "",
        f"## {section + 2}. 文本长度统计",
        f"- 短文本（≤10 字）: {short_count}",
        f"- 长文本（≥100 字）: {long_count}",
    ]

    report_path.write_text("\n".join(lines), encoding="utf-8")

    return {
        "input_count": input_count,
        "target_size": target_size,
        "sampled_count": sampled_count,
        "groups_covered": len(groups),
        "speakers_covered": len(speakers),
        "high_risk_count": 0,  # no Round 1 hardcoded boundary
        "control_group_count": control_count,
        "risk_config_used": not is_round01,
        "control_group": resolved_control,
        "output_path": str(csv_path),
        "report_path": str(report_path),
    }
