"""v1.1 — AuditSampleBuilder: stratified sampling for human audit + DeepSeek validation.

Samples ~100 units from the final coding table, stratified by:
  - Label distribution (IS1/IS2/IS3/IS4)
  - Risk flags (boundary cases, low-information, uncertain)
  - Disagreement samples (where formal A/B disagreed)
  - Random baseline (agreement samples for calibration)

Outputs:
  - human_audit_template.csv (for human coders to fill)
  - audit_sample_manifest.json (sample metadata)
  - mock_labels_for_sample.jsonl (mock coder labels for sampled units)

Does NOT call DeepSeek. Does NOT modify final outputs.
"""

from __future__ import annotations

import csv
import json
import random
from collections import Counter, defaultdict
from pathlib import Path


def build_audit_sample(
    project_dir: str | Path,
    target_size: int = 100,
    seed: int = 42,
) -> dict:
    """Build a stratified audit sample from the final coding table.

    Args:
        project_dir: Project root directory.
        target_size: Total sample size (default 100).
        seed: Random seed for reproducibility.

    Returns dict with paths and stats.
    """
    root = Path(project_dir)
    out_dir = root / "08_validation"
    out_dir.mkdir(parents=True, exist_ok=True)

    rng = random.Random(seed)

    # ── Load final data ───────────────────────────────────
    final_table_path = root / "07_final" / "final_coding_table.csv"
    consensus_path = root / "07_final" / "final_consensus_labels.jsonl"
    formal_a_path = root / "06_formal_coding" / "coder_A_formal.jsonl"
    formal_b_path = root / "06_formal_coding" / "coder_B_formal.jsonl"
    adj_path = root / "07_final" / "final_adjudication_results.jsonl"
    unit_path = root / "00_inputs" / "unit_table.csv"

    # Load all units
    units = list(_load_csv(final_table_path))
    consensus = {r["unit_id"]: r for r in _load_jsonl(consensus_path)}
    formal_a = {r["unit_id"]: r for r in _load_jsonl(formal_a_path)}
    formal_b = {r["unit_id"]: r for r in _load_jsonl(formal_b_path)}
    adj = {r["unit_id"]: r for r in _load_jsonl(adj_path)} if adj_path.exists() else {}
    raw_units = {r["unit_id"]: r for r in _load_csv(unit_path)} if unit_path.exists() else {}

    # ── Build sampling pools ──────────────────────────────
    # Pool 1: Disagreement samples (A != B)
    dis_pool = []
    # Pool 2: High-risk boundary samples
    risk_pool = []
    # Pool 3: Per-label random baseline
    label_pools: dict[str, list[dict]] = defaultdict(list)

    boundary_keywords = [
        "是不是", "那先", "我来", "我可以", "okok", "不是吧",
        "感觉会出问题", "怎么办", "不太对", "谢谢",
    ]

    for u in units:
        uid = u["unit_id"]
        code = u.get("final_primary_code", "")
        text = u.get("unit_text", "")

        # Check for disagreement
        fa = formal_a.get(uid, {})
        fb = formal_b.get(uid, {})
        if fa.get("primary_code") != fb.get("primary_code"):
            dis_pool.append(u)
            continue

        # Check for boundary risk
        if any(kw in text for kw in boundary_keywords):
            risk_pool.append(u)
            continue

        # Per-label baseline
        if code:
            label_pools[code].append(u)

    # ── Allocate samples ───────────────────────────────────
    # Target: 30 disagreement + 30 high-risk + 40 stratified per-label
    n_dis = min(30, len(dis_pool))
    n_risk = min(30, len(risk_pool))
    n_label = target_size - n_dis - n_risk
    if n_label < 10:
        n_label = target_size - n_dis - n_risk

    sampled = []
    if dis_pool:
        sampled.extend(rng.sample(dis_pool, n_dis))
    if risk_pool:
        sampled.extend(rng.sample(risk_pool, n_risk))

    # Per-label: target ~equal per label from remaining pools
    n_per_label = max(1, n_label // max(1, len(label_pools)))
    for lbl in sorted(label_pools):
        pool = [u for u in label_pools[lbl] if u not in sampled]
        n = min(n_per_label, len(pool))
        if pool and n > 0:
            sampled.extend(rng.sample(pool, n))

    rng.shuffle(sampled)
    sampled = sampled[:target_size]

    # ── Build audit template ───────────────────────────────
    template_rows = []
    mock_rows = []
    label_counts: dict[str, int] = Counter()
    dis_count = 0
    risk_count = 0

    for u in sampled:
        uid = u["unit_id"]
        code = u.get("final_primary_code", "")
        text = u.get("unit_text", "")
        raw = raw_units.get(uid, {})
        label_counts[code] += 1

        fa = formal_a.get(uid, {})
        fb = formal_b.get(uid, {})
        is_dis = fa.get("primary_code") != fb.get("primary_code")
        if is_dis:
            dis_count += 1
        is_risk = any(kw in text for kw in boundary_keywords)
        if is_risk:
            risk_count += 1

        template_rows.append({
            "audit_id": f"AUDIT_{uid}",
            "unit_id": uid,
            "unit_text": text,
            "context_before": raw.get("context_before", ""),
            "context_after": raw.get("context_after", ""),
            "group_id": raw.get("group_id", u.get("group_id", "")),
            "speaker_id": raw.get("speaker_id", u.get("speaker_id", "")),
            "mock_final_code": code,
            "is_disagreement_sample": "TRUE" if is_dis else "FALSE",
            "is_boundary_risk_sample": "TRUE" if is_risk else "FALSE",
            "human_label": "",
            "human_confidence": "",
            "human_rationale": "",
            "human_notes": "",
        })

        mock_rows.append({
            "unit_id": uid,
            "unit_text": text,
            "mock_label": code,
            "mock_coder_a": fa.get("primary_code", ""),
            "mock_coder_b": fb.get("primary_code", ""),
            "is_disagreement": is_dis,
            "adjudicated": uid in adj,
        })

    # ── Save outputs ───────────────────────────────────────
    template_fields = [
        "audit_id", "unit_id", "unit_text", "context_before", "context_after",
        "group_id", "speaker_id", "mock_final_code",
        "is_disagreement_sample", "is_boundary_risk_sample",
        "human_label", "human_confidence", "human_rationale", "human_notes",
    ]
    with open(out_dir / "human_audit_template.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=template_fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(template_rows)

    _save_jsonl(out_dir / "mock_labels_for_sample.jsonl", mock_rows)

    manifest = {
        "version": "v1.1",
        "target_size": target_size,
        "actual_size": len(sampled),
        "label_distribution": dict(label_counts),
        "disagreement_samples": dis_count,
        "risk_samples": risk_count,
        "seed": seed,
        "template_path": str(out_dir / "human_audit_template.csv"),
        "mock_labels_path": str(out_dir / "mock_labels_for_sample.jsonl"),
    }
    with open(out_dir / "audit_sample_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest


def _load_csv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with open(p, "r", encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f))


def _load_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _save_jsonl(p: Path, items: list[dict]) -> None:
    with open(p, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")
