"""Phase 3 — ReliabilityAgent: compute pilot coding reliability metrics.

Computes percent agreement, Cohen's Kappa, weighted Kappa,
Krippendorff's alpha, per-code P/R/F1, confusion matrix.
Does NOT call LLM. Does NOT perform disagreement adjudication.
"""

from __future__ import annotations

import csv
import json
import math
from collections import Counter
from pathlib import Path

ALL_LABELS = ["IS1", "IS2", "IS3", "IS4"]


def compute_reliability(project_dir: str | Path, round_id: str = "round_01") -> dict:
    """Compute reliability metrics between Coder A and Coder B results."""
    project_dir = Path(project_dir)
    round_dir = project_dir / "04_pilot" / round_id

    # Load results
    results_a = _load_jsonl(round_dir / "coder_A_results.jsonl")
    results_b = _load_jsonl(round_dir / "coder_B_results.jsonl")

    # Build lookup by unit_id
    a_map = {r["unit_id"]: r for r in results_a}
    b_map = {r["unit_id"]: r for r in results_b}

    all_ids = set(a_map.keys()) | set(b_map.keys())
    missing_a = all_ids - set(a_map.keys())
    missing_b = all_ids - set(b_map.keys())
    missing_count = len(missing_a) + len(missing_b)

    # Collect paired labels
    labels_a: list[str] = []
    labels_b: list[str] = []
    invalid_count = 0
    uncertain_a = 0
    uncertain_b = 0
    n_total = len(all_ids)

    for uid in sorted(all_ids & set(a_map.keys()) & set(b_map.keys())):
        ra = a_map[uid]
        rb = b_map[uid]
        la = ra.get("primary_code")
        lb = rb.get("primary_code")

        if la not in ALL_LABELS or lb not in ALL_LABELS:
            invalid_count += 1
            continue

        labels_a.append(la)
        labels_b.append(lb)

        if ra.get("uncertain"):
            uncertain_a += 1
        if rb.get("uncertain"):
            uncertain_b += 1

    n_valid = len(labels_a)

    # Percent agreement
    agrees = sum(1 for i in range(n_valid) if labels_a[i] == labels_b[i])
    pct_agreement = agrees / n_valid if n_valid > 0 else 0.0

    # Cohen's Kappa
    kappa = _cohen_kappa(labels_a, labels_b)
    wkappa = _cohen_kappa(labels_a, labels_b, weighted=True)
    kalpha = _krippendorff_alpha(labels_a, labels_b)

    # Label distributions
    dist_a = dict(Counter(labels_a))
    dist_b = dict(Counter(labels_b))
    for lbl in ALL_LABELS:
        dist_a.setdefault(lbl, 0)
        dist_b.setdefault(lbl, 0)

    # Confusion matrix
    cm = _confusion_matrix(labels_a, labels_b)

    # Per-code precision/recall/F1
    per_code = {}
    for lbl in ALL_LABELS:
        tp = cm.get((lbl, lbl), 0)
        pred_pos = sum(cm.get((other, lbl), 0) for other in ALL_LABELS)
        actual_pos = sum(cm.get((lbl, other), 0) for other in ALL_LABELS)
        p = tp / pred_pos if pred_pos > 0 else 0.0
        r = tp / actual_pos if actual_pos > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        per_code[lbl] = {"precision": round(p, 4), "recall": round(r, 4),
                         "f1": round(f1, 4), "support": actual_pos}

    parse_ok_a = sum(1 for r in results_a if r.get("parse_ok"))
    parse_ok_b = sum(1 for r in results_b if r.get("parse_ok"))

    metrics = {
        "round_id": round_id,
        "n_total_units": n_total,
        "n_valid_pairs": n_valid,
        "n_invalid": invalid_count,
        "n_missing": missing_count,
        "percent_agreement": round(pct_agreement, 4),
        "cohen_kappa": round(kappa, 4),
        "weighted_kappa": round(wkappa, 4),
        "krippendorff_alpha": round(kalpha, 4),
        "label_distribution_A": dist_a,
        "label_distribution_B": dist_b,
        "uncertain_rate_A": round(uncertain_a / max(len(results_a), 1), 4),
        "uncertain_rate_B": round(uncertain_b / max(len(results_b), 1), 4),
        "parse_ok_rate_A": round(parse_ok_a / max(len(results_a), 1), 4),
        "parse_ok_rate_B": round(parse_ok_b / max(len(results_b), 1), 4),
    }

    # Save outputs
    _save_json(round_dir / "agreement_metrics.json", metrics)
    _save_json(round_dir / "code_level_metrics.json", per_code)
    _save_confusion_csv(round_dir / "confusion_matrix.csv", cm)
    _save_report(round_dir / "reliability_report.md", metrics, per_code, cm)

    return metrics


# ── Internal metrics ──────────────────────────────────────

def _cohen_kappa(a: list[str], b: list[str], weighted: bool = False) -> float:
    """Compute Cohen's Kappa (unweighted or linear weighted). Pure Python, no sklearn."""
    if not a or len(a) != len(b):
        return 0.0
    n = len(a)
    if n == 0:
        return 0.0
    # Single-label case: if all identical, perfect agreement
    if len(set(a)) == 1 and a == b:
        return 1.0
    # Build label set from both raters
    labels = sorted(set(a) | set(b))
    n_labels = len(labels)
    if n_labels <= 1:
        return 1.0 if a == b else 0.0
    label_to_idx = {l: i for i, l in enumerate(labels)}

    # Confusion matrix
    cm = [[0] * n_labels for _ in range(n_labels)]
    for ai, bi in zip(a, b):
        cm[label_to_idx[ai]][label_to_idx[bi]] += 1

    # Weight matrix for linear weighting
    if weighted:
        w = [[1.0 - abs(i - j) / (n_labels - 1) for j in range(n_labels)] for i in range(n_labels)]
    else:
        w = [[1.0 if i == j else 0.0 for j in range(n_labels)] for i in range(n_labels)]

    # Observed agreement
    po = sum(cm[i][j] * w[i][j] for i in range(n_labels) for j in range(n_labels)) / n

    # Expected agreement
    row_sum = [sum(cm[i]) for i in range(n_labels)]
    col_sum = [sum(cm[i][j] for i in range(n_labels)) for j in range(n_labels)]
    pe = sum(row_sum[i] * col_sum[j] * w[i][j] for i in range(n_labels) for j in range(n_labels)) / (n * n)

    if abs(1.0 - pe) < 1e-12:
        return 1.0
    k = (po - pe) / (1.0 - pe)
    return float(max(-1.0, min(1.0, k)))


def _krippendorff_alpha(a: list[str], b: list[str]) -> float:
    """Simple Krippendorff's alpha for nominal data (2 coders)."""
    n = len(a)
    if n < 2:
        return 0.0

    # Build agreement matrix
    labels = sorted(set(a + b))
    mat = {(l1, l2): 0 for l1 in labels for l2 in labels}
    for la, lb in zip(a, b):
        mat[(la, lb)] += 1

    # Observed disagreement
    d_o = 0
    for (l1, l2), count in mat.items():
        if l1 != l2:
            d_o += count
    d_o /= n

    # Expected disagreement
    total = n * 2
    margins = {}
    for l in labels:
        margins[l] = sum(mat.get((l, l2), 0) + mat.get((l2, l), 0)
                         for l2 in labels) / 2
    d_e = 0
    for l1 in labels:
        for l2 in labels:
            if l1 != l2:
                d_e += margins[l1] * margins[l2]
    d_e = d_e / (total * (total - 1) / 2) if total > 1 else 1.0

    alpha = 1 - d_o / d_e if d_e > 0 else 0.0
    return round(alpha, 4)


def _confusion_matrix(a: list[str], b: list[str]) -> dict:
    cm: dict[tuple[str, str], int] = {}
    for la, lb in zip(a, b):
        cm[(la, lb)] = cm.get((la, lb), 0) + 1
    return cm


# ── I/O ───────────────────────────────────────────────────

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


def _save_json(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _save_confusion_csv(path: Path, cm: dict) -> None:
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([""] + ALL_LABELS + ["Total"])
        for row_lbl in ALL_LABELS:
            row = [row_lbl]
            total = 0
            for col_lbl in ALL_LABELS:
                v = cm.get((row_lbl, col_lbl), 0)
                row.append(v)
                total += v
            row.append(total)
            w.writerow(row)


def _save_report(path: Path, metrics: dict, per_code: dict, cm: dict) -> None:
    lines = [
        f"# Reliability Report — {metrics['round_id']}",
        "",
        "## 1. Summary",
        f"- Total units: {metrics['n_total_units']}",
        f"- Valid pairs: {metrics['n_valid_pairs']}",
        f"- Invalid: {metrics['n_invalid']}",
        f"- Missing: {metrics['n_missing']}",
        "",
        "## 2. Agreement Metrics",
        f"- Percent Agreement: {metrics['percent_agreement']:.4f}",
        f"- Cohen's Kappa: {metrics['cohen_kappa']:.4f}",
        f"- Weighted Kappa: {metrics['weighted_kappa']:.4f}",
        f"- Krippendorff's Alpha: {metrics['krippendorff_alpha']:.4f}",
        "",
        "## 3. Label Distributions",
        "| Label | Coder A | Coder B |",
        "|-------|---------|---------|",
    ]
    for lbl in ALL_LABELS:
        lines.append(f"| {lbl} | {metrics['label_distribution_A'].get(lbl,0)} | "
                     f"{metrics['label_distribution_B'].get(lbl,0)} |")

    lines += [
        "",
        "## 4. Per-Code Metrics",
        "| Code | Precision | Recall | F1 | Support |",
        "|------|-----------|--------|-----|---------|",
    ]
    for lbl in ALL_LABELS:
        m = per_code.get(lbl, {})
        lines.append(f"| {lbl} | {m.get('precision','?')} | {m.get('recall','?')} | "
                     f"{m.get('f1','?')} | {m.get('support','?')} |")

    lines += [
        "",
        "## 5. Quality Metrics",
        f"- parse_ok_rate A: {metrics['parse_ok_rate_A']:.4f}",
        f"- parse_ok_rate B: {metrics['parse_ok_rate_B']:.4f}",
        f"- uncertain_rate A: {metrics['uncertain_rate_A']:.4f}",
        f"- uncertain_rate B: {metrics['uncertain_rate_B']:.4f}",
        "",
        "## 6. Decision",
    ]
    k = metrics["cohen_kappa"]
    if k >= 0.80:
        lines.append(f"Kappa={k:.4f} ≥ 0.80: 一致性良好。")
    elif k >= 0.70:
        lines.append(f"Kappa={k:.4f} ≥ 0.70: 一致性可接受。")
    else:
        lines.append(f"Kappa={k:.4f} < 0.70: 建议进入分歧分析阶段。")

    path.write_text("\n".join(lines), encoding="utf-8")
