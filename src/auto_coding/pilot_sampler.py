"""Phase 1 — PilotSampler: stratified sampling from validated unit table.

Round 1 (default, no risk_config_path):
  Uses only real structural fields from unit_table_v0.1.csv.
  Pool 1: group_stratified (speaker round-robin with within-speaker order preservation)
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

from .structural_rules import SHORT_TEXT_MAX_CHARS, LONG_TEXT_MIN_CHARS

# ── Generic helpers ─────────────────────────────────────────────

TRUE_VALUES = {"true", "1", "yes", "y"}


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

def _load_and_validate(unit_table_path: Path) -> tuple[list[dict], list[str]]:
    if not unit_table_path.exists():
        raise FileNotFoundError(f"Unit table not found: {unit_table_path}")

    with open(unit_table_path, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        all_rows = list(reader)
        original_fieldnames = list(reader.fieldnames or [])

    required = {"unit_id", "group_id", "speaker_id", "unit_text"}
    available = set(original_fieldnames)
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
    return valid_rows, original_fieldnames


# ── Pool 1: group_stratified ────────────────────────────────────

def _sample_group_stratified(
    valid_rows: list[dict], pool1_target: int, rng: random.Random
) -> tuple[list[dict], set[str]]:
    """Pool 1: group-stratified random with speaker round-robin and
    within-speaker order preservation."""

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
    return selected, selected_ids


def _sample_within_group(
    group_rows: list[dict], quota: int, rng: random.Random
) -> list[dict]:
    """Sample within a group, spreading across speakers and temporal order.

    Strategy:
    1. Build per-speaker pools
    2. Sort within-speaker by turn_id/source_row_id for order preservation
    3. Round-robin across speakers, selecting earliest unselected from each
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
    return _char_len(row.get("unit_text", "")) <= SHORT_TEXT_MAX_CHARS


def _is_structural_long(row: dict) -> bool:
    if _parse_bool(row.get("long_text_flag")):
        return True
    return _char_len(row.get("unit_text", "")) >= LONG_TEXT_MIN_CHARS


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


# ── Coverage analysis ──────────────────────────────────────────

def _analyze_sample_coverage(
    all_rows: list[dict],
    selected_rows: list[dict],
    target_size: int,
) -> dict:
    """Analyze coverage of selected sample against full population.

    Reuses existing structural detection functions for consistency.
    Returns structured stats dict. Does NOT read/write files.
    """
    pop_count = len(all_rows)
    samp_count = len(selected_rows)

    # ── Group coverage ───────────────────────────────────────
    pop_groups = set(_norm_group(r.get("group_id")) for r in all_rows)
    samp_groups = set(_norm_group(r.get("group_id")) for r in selected_rows)
    missing_groups = sorted(pop_groups - samp_groups)

    # ── Speaker coverage ─────────────────────────────────────
    pop_speakers = set(_norm_group(r.get("speaker_id")) for r in all_rows)
    samp_speakers = set(_norm_group(r.get("speaker_id")) for r in selected_rows)
    missing_speakers = sorted(pop_speakers - samp_speakers)

    # ── Structural type coverage (reuses existing predicates) ─
    type_predicates = [
        ("short_text", _is_structural_short),
        ("long_text", _is_structural_long),
        ("missing_context", _is_structural_missing_context),
        ("multi_function", _is_structural_multi_function),
    ]
    structural_types: dict[str, dict] = {}
    for name, pred in type_predicates:
        pop_n = sum(1 for r in all_rows if pred(r))
        samp_n = sum(1 for r in selected_rows if pred(r))
        structural_types[name] = {
            "population_count": pop_n,
            "sampled_count": samp_n,
            "covered": samp_n > 0 or pop_n == 0,
        }

    # ── Warnings & needs_resampling ──────────────────────────
    warnings: list[str] = []
    needs_resampling = False

    # Group gap
    if missing_groups and target_size >= len(pop_groups):
        warnings.append(f"未覆盖 group: {missing_groups}")
        needs_resampling = True

    # Structural gap
    for name, info in structural_types.items():
        if info["population_count"] > 0 and info["sampled_count"] == 0:
            warnings.append(f"结构类型 {name} 存在但样本未覆盖")
            needs_resampling = True

    # Count anomaly — internal invariant, triggers resampling
    theoretical_max = min(target_size, pop_count)
    if samp_count < theoretical_max:
        needs_resampling = True
        warnings.append(
            f"样本数量 ({samp_count}) 少于理论可抽数量 ({theoretical_max})"
        )

    # Non-critical: partial speaker coverage
    if missing_speakers:
        warnings.append(f"部分 speaker 未覆盖: {missing_speakers}")

    # Non-critical: target_size too small for full group coverage
    if target_size < len(pop_groups):
        warnings.append(
            f"target_size ({target_size}) < group 总数 ({len(pop_groups)})，"
            f"不可能覆盖全部 group"
        )

    # Non-critical: full_population scenario
    if pop_count <= target_size:
        warnings.append(
            f"全量选取（总量 {pop_count} ≤ target {target_size}），无法评估抽样覆盖"
        )

    return {
        "population_count": pop_count,
        "sampled_count": samp_count,
        "sample_ratio": samp_count / max(pop_count, 1),
        "groups": {
            "population_count": len(pop_groups),
            "sampled_count": len(samp_groups),
            "missing": missing_groups,
        },
        "speakers": {
            "population_count": len(pop_speakers),
            "sampled_count": len(samp_speakers),
            "missing": missing_speakers,
        },
        "structural_types": structural_types,
        "warnings": warnings,
        "needs_resampling": needs_resampling,
    }


# ── Main entry point ─────────────────────────────────────────────

def sample(
    unit_table_path: str | Path,
    out_dir: str | Path,
    target_size: int = 300,
    seed: int = 42,
    risk_config_path: str | Path | None = None,
    control_group: str | None = None,
    round_id: str = "round_01",
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
    is_round01 = (round_id == "round_01")
    risk_config_provided = risk_config_path is not None
    explicit_units = config.get("explicit_units", [])

    # ── Load & validate ─────────────────────────────────────
    valid_rows, original_fieldnames = _load_and_validate(unit_table_path)
    input_count = len(valid_rows)
    rng = random.Random(seed)

    # ── Full-set ────────────────────────────────────────────
    if input_count <= target_size:
        for row in valid_rows:
            row["_sample_reason"] = "full_population"
        coverage = _analyze_sample_coverage(valid_rows, valid_rows, target_size)
        return _build_output(
            valid_rows, out_dir, target_size, input_count, seed,
            config, None, is_round01, coverage, original_fieldnames, round_id, risk_config_provided,
        )

    # ── Pool targets ────────────────────────────────────────
    pool1_target = round(target_size * 0.70)
    pool2_target = round(target_size * 0.20)
    pool3_target = target_size - pool1_target - pool2_target

    # ── Pool 1 ──────────────────────────────────────────────
    p1_selected, p1_ids = _sample_group_stratified(valid_rows, pool1_target, rng)

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

    coverage = _analyze_sample_coverage(valid_rows, final_selected, target_size)
    return _build_output(
        final_selected, out_dir, target_size, input_count, seed,
        config, resolved_control, is_round01, coverage, original_fieldnames, round_id,
        risk_config_provided,
    )


# ── Output ──────────────────────────────────────────────────────

def _write_sample_csv(selected, out_dir, original_fieldnames):
    csv_path = out_dir / "pilot_sample_units.csv"
    csv_fields = [f for f in original_fieldnames if f != "sample_reason"]
    if "sample_reason" not in csv_fields:
        csv_fields.append("sample_reason")
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=csv_fields, extrasaction="ignore")
        w.writeheader()
        for row in selected:
            out_row = {
                k: ((row.get(k) or "").strip() if isinstance(row.get(k), str) else (row.get(k) or ""))
                for k in csv_fields if k != "sample_reason"
            }
            out_row["sample_reason"] = row.get("_sample_reason", "")
            w.writerow(out_row)
    return csv_path


def _write_sample_report(selected, out_dir, input_count, target_size, seed,
                          config, resolved_control, is_round01, coverage, round_id,
                          risk_config_provided=False):
    report_path = out_dir / "pilot_sample_build_report.md"
    rc = Counter(r.get("_sample_reason", "") for r in selected)
    sc = len(selected)
    exc = rc.get("explicit_unit", 0)
    ctrl_count = rc.get("control_group", 0)
    short_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) <= SHORT_TEXT_MAX_CHARS)
    long_count = sum(1 for r in selected if _char_len(r.get("unit_text", "")) >= LONG_TEXT_MIN_CHARS)

    lines = [
        "# Pilot Sample Build Report", "",
        "## 1. 基本统计",
        f"- 输入有效记录数: {input_count}",
        f"- 目标样本数: {target_size}",
        f"- 实际抽样数: {sc}",
        f"- Round ID: {round_id}",
        f"- 随机种子: {seed}",
        f"- 全量选取: {'是' if input_count <= target_size else '否'}",
        f"- Round 模式: {'Round 1 (representative + structural difficulty)' if is_round01 else 'Round 2+'}",
        f"- Risk profile used: {'yes' if risk_config_provided else 'no'}",
        "",
    ]
    if not is_round01:
        src = config.get("source_round_id", "?")
        tgt = config.get("target_round_id", "?")
        lines.append("## 2. 风险画像信息")
        lines.append(f"- 来源轮次: {src}")
        lines.append(f"- 目标轮次: {tgt}")
        lines.append(f"- 配置文件: {config.get('_path', '(未记录)')}")
        lines.append(f"- explicit_units 带入: {exc}")
        cps = config.get("confusion_pairs", [])
        if cps:
            lines.append(f"- confusion_pairs（报告信息，不用于抽样匹配）: {len(cps)} 对")
            for cp in cps:
                lines.append(f"  - {cp.get('codes', [])}: {cp.get('disagreement_count', '?')} 次分歧")
        lines.append("")

    section_base = 3 if is_round01 else 4
    lines += [
        f"## {section_base - 1}. 对照组",
        f"- 对照组: {resolved_control or '(未指定)'}",
    ]
    if resolved_control is None:
        lines.append("- Pool 3 已跳过，其配额由 random_fill 补齐。")
    elif ctrl_count == 0:
        lines.append(f"- ⚠️ 对照组 `{resolved_control}` 在数据中无匹配记录。")
    lines.append("")

    lines += [
        f"## {section_base}. Pool 构成",
        f"- group_stratified: {rc.get('group_stratified', 0)}",
    ]
    if exc > 0:
        lines.append(f"- explicit_unit: {exc}")
    lines += [
        f"- structural_short_text: {rc.get('structural_short_text', 0)}",
        f"- structural_long_text: {rc.get('structural_long_text', 0)}",
        f"- structural_missing_context: {rc.get('structural_missing_context', 0)}",
        f"- structural_multi_function: {rc.get('structural_multi_function', 0)}",
        f"- control_group: {ctrl_count}",
        f"- random_fill: {rc.get('random_fill', 0)}",
    ]
    if rc.get("full_population", 0) > 0:
        lines.append(f"- full_population: {rc['full_population']}")

    cov_g = coverage.get("groups", {})
    cov_s = coverage.get("speakers", {})
    cov_st = coverage.get("structural_types", {})

    lines += [
        "", f"## {section_base + 1}. 样本覆盖审查", "",
        "### Group 覆盖",
        f"- 完整数据 group 数: {cov_g.get('population_count', '?')}",
        f"- 样本覆盖 group 数: {cov_g.get('sampled_count', '?')}",
        f"- 未覆盖 group: {cov_g.get('missing', [])}",
        "", "### Speaker 覆盖",
        f"- 完整数据 speaker 数: {cov_s.get('population_count', '?')}",
        f"- 样本覆盖 speaker 数: {cov_s.get('sampled_count', '?')}",
        f"- 未覆盖 speaker: {cov_s.get('missing', [])}",
        "", "### 结构类型覆盖",
        "| 类型 | 完整数据数量 | 样本数量 | 是否覆盖 |",
        "|---|---:|---:|---|",
    ]
    for tname, tinfo in cov_st.items():
        lines.append(
            f"| {tname} | {tinfo.get('population_count', 0)} | "
            f"{tinfo.get('sampled_count', 0)} | "
            f"{'✅' if tinfo.get('covered') else '❌'} |")
    lines += [
        "", "### 补样判断",
        f"- needs_resampling: {coverage.get('needs_resampling', False)}",
        f"- warnings: {coverage.get('warnings', [])}",
    ]

    lines += ["", "### 各 group 样本数量"]
    group_counts = Counter(_norm_group(r.get("group_id")) for r in selected)
    for g in sorted(group_counts, key=lambda g: (int(re.findall(r"\d+", g)[0]) if re.findall(r"\d+", g) else 9999, g)):
        lines.append(f"- {g}: {group_counts[g]}")

    lines += [
        "", f"## {section_base + 2}. 文本长度统计",
        f"- 短文本（≤{SHORT_TEXT_MAX_CHARS} 字）: {short_count}",
        f"- 长文本（≥{LONG_TEXT_MIN_CHARS} 字）: {long_count}",
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    return report_path


def _build_output(
    selected: list[dict],
    out_dir: Path,
    target_size: int,
    input_count: int,
    seed: int,
    config: dict,
    resolved_control: str | None,
    is_round01: bool,
    coverage: dict,
    original_fieldnames: list[str],
    round_id: str = "round_01",
    risk_config_provided: bool = False,
) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    csv_path = _write_sample_csv(selected, out_dir, original_fieldnames)
    report_path = _write_sample_report(
        selected, out_dir, input_count, target_size, seed, config,
        resolved_control, is_round01, coverage, round_id, risk_config_provided,
    )
    rc = Counter(r.get("_sample_reason", "") for r in selected)
    return {
        "input_count": input_count,
        "target_size": target_size,
        "sampled_count": len(selected),
        "groups_covered": len(set(_norm_group(r.get("group_id")) for r in selected)),
        "speakers_covered": len(set(_norm_group(r.get("speaker_id")) for r in selected)),
        "high_risk_count": 0,
        "control_group_count": rc.get("control_group", 0),
        "risk_config_used": risk_config_provided,
        "control_group": resolved_control,
        "output_path": str(csv_path),
        "report_path": str(report_path),
        "coverage": coverage,
        "needs_resampling": coverage.get("needs_resampling", False),
        "coverage_warnings": coverage.get("warnings", []),
        "round_id": round_id,
    }
