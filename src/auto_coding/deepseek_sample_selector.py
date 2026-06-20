"""v1.1 — Risk-enriched sample selector for DeepSeek runs."""

from __future__ import annotations

import csv, json, random
from collections import Counter
from pathlib import Path


def select_risk_sample(project_dir: str | Path, sample_size: int = 100,
                       output_path: str | None = None, seed: int = 42) -> dict:
    root = Path(project_dir)
    rng = random.Random(seed)

    # Load final coding table for label reference
    fc = root / "07_final" / "final_coding_table.csv"
    unit_path = root / "00_inputs" / "unit_table.csv"

    units = {}
    if fc.exists():
        with open(fc, "r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                units[r["unit_id"]] = r
    elif unit_path.exists():
        with open(unit_path, "r", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                units[r["unit_id"]] = r

    # Load v1.0 disagreements for risk enrichment
    dis_units = set()
    try:
        for rn in ["round_01"]:
            df = root / "04_pilot" / rn / "disagreement_table.csv"
            if df.exists():
                with open(df, "r", encoding="utf-8", newline="") as f:
                    for r in csv.DictReader(f):
                        if r.get("needs_adjudication", "").upper() == "TRUE":
                            dis_units.add(r.get("unit_id", ""))
    except Exception:
        pass

    # Boundary risk keywords
    risk_kw = [
        "是不是", "那先", "我来", "我可以", "okok", "不是吧", "感觉会出问题",
        "怎么办", "不太对", "谢谢", "要不要", "我们先", "咱们先",
        "没看懂", "不懂", "数据反了", "标准差吗",
    ]

    # Categorize units
    high_risk = []; boundary = []; label_pools = {"IS1": [], "IS2": [], "IS3": [], "IS4": []}
    for uid, u in units.items():
        text = u.get("unit_text", "")
        code = u.get("final_primary_code", "IS2")
        if uid in dis_units:
            high_risk.append(u)
        elif any(kw in text for kw in risk_kw):
            boundary.append(u)
        elif code in label_pools:
            label_pools[code].append(u)

    # Allocate: 30% high-risk, 30% boundary, 40% per-label
    n_hr = min(sample_size * 30 // 100, len(high_risk))
    n_bd = min(sample_size * 30 // 100, len(boundary))
    n_lb = sample_size - n_hr - n_bd
    n_per_label = max(1, n_lb // 4)

    selected = []
    if high_risk: selected.extend(rng.sample(high_risk, n_hr))
    if boundary: selected.extend(rng.sample(boundary, n_bd))
    for lbl in ["IS1", "IS2", "IS3", "IS4"]:
        pool = [u for u in label_pools[lbl] if u not in selected]
        n = min(n_per_label, len(pool))
        if pool and n > 0: selected.extend(rng.sample(pool, n))

    rng.shuffle(selected)
    selected = selected[:sample_size]

    # Fallback: if not enough, fill from remaining units
    shortage = sample_size - len(selected)
    selected_ids = {u.get("unit_id","") for u in selected}
    if shortage > 0:
        all_units = list(units.values())
        remaining = [u for u in all_units if u.get("unit_id","") not in selected_ids]
        if remaining:
            fill = rng.sample(remaining, min(shortage, len(remaining)))
            selected.extend(fill)
    shortage = sample_size - len(selected)

    # Write output
    out_dir = root / "09_deepseek_runs" / "round_01_100"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_csv = out_dir / "input_units.csv"
    if output_path:
        out_csv = root / output_path

    fields = list(selected[0].keys()) if selected else ["unit_id", "unit_text"]
    with open(out_csv, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(selected)

    # Manifest
    label_dist = Counter(u.get("final_primary_code", "?") for u in selected)
    reason_counts = {"high_risk_v1_disagreement": n_hr, "boundary_keyword": n_bd, "per_label": n_lb}
    manifest = {
        "requested_sample_size": sample_size,
        "actual_sample_size": len(selected),
        "shortage_count": shortage,
        "shortage_reason": "Insufficient risk-pool units; fallback filled from general pool." if shortage == 0 else f"{shortage} units could not be filled.",
        "fallback_used": shortage == 0 and len(selected) >= sample_size,
        "source": "risk_enriched",
        "label_distribution_from_v1": dict(label_dist),
        "risk_reason_counts": reason_counts,
        "unit_ids": [u.get("unit_id", "") for u in selected],
    }
    with open(out_dir / "risk_sample_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    return manifest
