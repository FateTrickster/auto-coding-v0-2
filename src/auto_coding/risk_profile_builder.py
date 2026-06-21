"""RiskProfileBuilder: generate round_N+1 risk config from round_N real outputs.

Consumes existing project artifacts:
  - disagreement_table.csv
  - disagreement_analysis.json
  - adjudication_results.jsonl
  - codebook_revision_proposal_{round_id}.json

Produces:
  - 04_pilot/risk_profiles/risk_config_{target_round_id}_candidate.yaml

ALL items have status: candidate and evidence_ids.
Does NOT extract natural-language keywords from unit_text.
confusion_pairs are report-only; NOT used for text matching on un-coded samples.
"""

from __future__ import annotations

import csv
import json
from collections import Counter
from pathlib import Path
from typing import Any

import yaml


def build_risk_config(
    project_dir: str | Path,
    source_round_id: str = "round_01",
    target_round_id: str = "round_02",
    min_confusion_count: int = 2,
) -> dict:
    """Build candidate risk config from round_N real outputs.

    Returns dict with status info and output path.
    """
    project_dir = Path(project_dir)
    rd = project_dir / "04_pilot" / source_round_id

    # ── Load sources ────────────────────────────────────────
    disagreement_rows = _load_disagreement_csv(rd / "disagreement_table.csv")
    disagreement_json = _load_json(rd / "disagreement_analysis.json")
    adjudication_rows = _load_jsonl(rd / "adjudication_results.jsonl")
    revision_proposal = _load_json(
        project_dir / "01_codebook" / f"codebook_revision_proposal_{source_round_id}.json"
    )

    # ── Build explicit_units ────────────────────────────────
    explicit_units = _build_explicit_units(disagreement_rows, adjudication_rows)

    # ── Build confusion_pairs (report-only) ─────────────────
    confusion_pairs = _build_confusion_pairs(disagreement_rows, min_confusion_count)

    # ── Build boundary_patterns (from revision proposal only) ─
    boundary_patterns = _build_boundary_patterns(revision_proposal, adjudication_rows)

    # ── Assemble config ─────────────────────────────────────
    config = {
        "source_round_id": source_round_id,
        "target_round_id": target_round_id,
        "status": "candidate",
        "generated_from": {
            "disagreement_table": f"04_pilot/{source_round_id}/disagreement_table.csv",
            "disagreement_analysis": f"04_pilot/{source_round_id}/disagreement_analysis.json",
            "adjudication_results": f"04_pilot/{source_round_id}/adjudication_results.jsonl",
            "revision_proposal": f"01_codebook/codebook_revision_proposal_{source_round_id}.json",
        },
        "explicit_units": explicit_units,
        "confusion_pairs": confusion_pairs,
        "boundary_patterns": boundary_patterns,
        "control_sampling": {"group_ids": []},
    }

    # ── Write ───────────────────────────────────────────────
    out_dir = project_dir / "04_pilot" / "risk_profiles"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"risk_config_{target_round_id}_candidate.yaml"

    with open(out_path, "w", encoding="utf-8") as f:
        yaml.dump(config, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    return {
        "source_round_id": source_round_id,
        "target_round_id": target_round_id,
        "explicit_units_count": len(explicit_units),
        "confusion_pairs_count": len(confusion_pairs),
        "boundary_patterns_count": len(boundary_patterns),
        "output_path": str(out_path),
    }


# ── Internal builders ───────────────────────────────────────────

def _load_disagreement_csv(path: Path) -> list[dict]:
    if not path.exists():
        return []
    with open(path, "r", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _load_json(path: Path) -> dict | None:
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _load_jsonl(path: Path) -> list[dict]:
    if not path.exists():
        return []
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def _build_explicit_units(
    disagreement_rows: list[dict],
    adjudication_rows: list[dict],
) -> list[dict]:
    """Build explicit_units list from label disagreements and unresolved adjudications."""
    units: list[dict] = []
    seen_ids: set[str] = set()

    # From disagreement table: rows where coder_A ≠ coder_B
    for row in disagreement_rows:
        uid = (row.get("unit_id") or "").strip()
        if not uid or uid in seen_ids:
            continue
        a_label = (row.get("coder_A_label") or "").strip()
        b_label = (row.get("coder_B_label") or "").strip()
        is_label_dis = str(row.get("is_label_disagreement", "")).lower() in ("true", "1", "yes")

        if is_label_dis or (a_label and b_label and a_label != b_label):
            seen_ids.add(uid)
            confused = sorted({a_label, b_label}) if a_label and b_label else []
            units.append({
                "unit_id": uid,
                "risk_type": "previous_label_disagreement",
                "confused_codes": confused,
                "source": "disagreement_table",
                "evidence_ids": [uid],
            })

    # From adjudication: unresolved items
    for row in adjudication_rows:
        uid = (row.get("unit_id") or "").strip()
        if not uid or uid in seen_ids:
            continue
        unresolved = str(row.get("unresolved", "")).lower() in ("true", "1", "yes")
        if unresolved:
            seen_ids.add(uid)
            a_label = (row.get("coder_A_label") or "").strip()
            b_label = (row.get("coder_B_label") or "").strip()
            confused = sorted({a_label, b_label}) if a_label and b_label else []
            decision_id = row.get("decision_id", "")
            units.append({
                "unit_id": uid,
                "risk_type": "unresolved_adjudication",
                "confused_codes": confused,
                "source": "adjudication_results",
                "evidence_ids": [decision_id] if decision_id else [uid],
            })

    return units


def _build_confusion_pairs(
    disagreement_rows: list[dict],
    min_count: int = 2,
) -> list[dict]:
    """Build confusion_pairs from label disagreement frequencies.

    These are REPORT-ONLY. They inform humans/codebook/refiner about which
    label pairs are problematic, but are NOT used to match un-coded samples.
    """
    pair_counter: Counter = Counter()
    pair_evidence: dict[tuple, list[str]] = {}

    for row in disagreement_rows:
        a_label = (row.get("coder_A_label") or "").strip()
        b_label = (row.get("coder_B_label") or "").strip()
        is_label_dis = str(row.get("is_label_disagreement", "")).lower() in ("true", "1", "yes")

        if not (is_label_dis or (a_label and b_label and a_label != b_label)):
            continue
        pair = tuple(sorted([a_label, b_label]))
        pair_counter[pair] += 1
        uid = (row.get("unit_id") or "").strip()
        if pair not in pair_evidence:
            pair_evidence[pair] = []
        if uid and uid not in pair_evidence[pair]:
            pair_evidence[pair].append(uid)

    pairs = []
    for (a, b), count in pair_counter.most_common():
        if count < min_count:
            continue
        pairs.append({
            "codes": [a, b],
            "disagreement_count": count,
            "source": "disagreement_table",
            "evidence_ids": pair_evidence.get((a, b), []),
            "status": "candidate",
        })

    return pairs


def _build_boundary_patterns(
    revision_proposal: dict | None,
    adjudication_rows: list[dict],
) -> list[dict]:
    """Build boundary_patterns ONLY from codebook_revision_proposal's affected_patterns.

    Does NOT extract natural-language keywords from unit_text.
    If affected_patterns are label-pair strings like "IS2-IS3",
    match_type is "label_pair" — NOT used for unit_text contains matching.
    """
    if revision_proposal is None:
        return []

    changes = revision_proposal.get("changes", [])
    if not changes:
        return []

    # Collect decision_ids for cross-referencing
    decision_ids = [r.get("decision_id", "") for r in adjudication_rows if r.get("decision_id")]

    patterns: list[dict] = []
    seen_patterns: set[str] = set()

    for change in changes:
        affected = change.get("affected_patterns") or change.get("affected_pattern") or []
        if isinstance(affected, str):
            affected = [affected]
        if not affected:
            continue

        target_codes = change.get("target_codes", [])
        change_id = change.get("change_id", "")
        evidence_decisions = change.get("evidence_decisions", [])

        for pat in affected:
            pat_str = str(pat).strip()
            if not pat_str or pat_str in seen_patterns:
                continue
            seen_patterns.add(pat_str)

            # Determine match_type: if the pattern looks like "IS2-IS3" label pair
            match_type = "label_pair"

            patterns.append({
                "pattern": pat_str,
                "match_type": match_type,
                "risk_type": "confirmed_boundary_pair",
                "confused_codes": target_codes if target_codes else [],
                "source": f"codebook_revision_proposal",
                "evidence_ids": (
                    evidence_decisions if evidence_decisions
                    else [change_id] if change_id
                    else decision_ids[:5]
                ),
            })

    return patterns
