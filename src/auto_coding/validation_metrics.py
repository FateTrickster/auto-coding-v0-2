"""v1.1 — ValidationMetrics: mock vs human vs DeepSeek comparison."""

from __future__ import annotations

import csv, json, math
from collections import Counter
from pathlib import Path

VALID_LABELS = ["IS1", "IS2", "IS3", "IS4"]


def compute(project_dir: str | Path) -> dict:
    """Compute mock vs human validation metrics. DeepSeek optional."""
    root = Path(project_dir)
    out = root / "08_validation"

    tp = out / "human_audit_template.csv"
    if not tp.exists():
        return {"status": "no_template"}

    with open(tp, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    # Filter to labeled only
    labeled = [r for r in rows if r.get("audit_status", "").strip() == "labeled"
               and r.get("human_label", "").strip() in VALID_LABELS]

    if len(labeled) < 2:
        return {"status": "AWAITING_HUMAN_LABELS", "labeled_count": len(labeled)}

    mock_labels = [r.get("mock_final_code", "").strip() for r in labeled]
    human_labels = [r.get("human_label", "").strip() for r in labeled]
    has_deepseek = any(r.get("deepseek_label", "").strip() in VALID_LABELS for r in labeled)

    # Mock vs Human
    n = len(labeled)
    agrees = sum(1 for i in range(n) if mock_labels[i] == human_labels[i])
    pct = agrees / n
    kappa = _cohen_kappa(mock_labels, human_labels)
    cm = _confusion_matrix(mock_labels, human_labels)

    # Per-code P/R/F1 (mock as pred, human as truth)
    per_code = {}
    for lbl in VALID_LABELS:
        tp = cm.get((lbl, lbl), 0)
        pred_pos = sum(cm.get((other, lbl), 0) for other in VALID_LABELS)
        actual_pos = sum(cm.get((lbl, other), 0) for other in VALID_LABELS)
        p = tp / pred_pos if pred_pos > 0 else 0.0
        r = tp / actual_pos if actual_pos > 0 else 0.0
        f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0.0
        per_code[lbl] = {"precision": round(p, 4), "recall": round(r, 4),
                         "f1": round(f1, 4), "support": actual_pos}

    # Error cases
    error_rows = []
    for i in range(n):
        if mock_labels[i] != human_labels[i]:
            error_rows.append({
                "unit_id": labeled[i].get("unit_id", ""),
                "unit_text": labeled[i].get("unit_text", ""),
                "mock_label": mock_labels[i],
                "human_label": human_labels[i],
                "is_disagreement_sample": labeled[i].get("is_disagreement_sample", ""),
            })

    # Update three_way_comparison.csv
    three_way_path = out / "three_way_comparison.csv"
    if three_way_path.exists():
        _update_three_way(three_way_path, has_deepseek)

    # Save outputs
    result = {
        "status": "MOCK_VS_HUMAN_READY",
        "labeled_count": n,
        "mock_vs_human_agreement": round(pct, 4),
        "mock_vs_human_kappa": round(kappa, 4),
        "per_code_metrics": per_code,
        "error_count": len(error_rows),
        "has_deepseek": has_deepseek,
    }

    with open(out / "validation_metrics_report.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    _save_confusion_csv(out / "mock_vs_human_confusion_matrix.csv", cm)
    _save_error_csv(out / "mock_vs_human_error_cases.csv", error_rows)

    md = [
        "# Validation Metrics Report",
        f"Status: {result['status']}",
        f"Labeled samples: {n}",
        "",
        f"## Mock vs Human",
        f"- Agreement: {pct:.4f}",
        f"- Cohen's Kappa: {kappa:.4f}",
        f"- Error cases: {len(error_rows)}",
        "",
        "## Per-Code Metrics",
        "| Code | Precision | Recall | F1 | Support |",
        "|------|-----------|--------|-----|---------|",
    ]
    for lbl in VALID_LABELS:
        m = per_code[lbl]
        md.append(f"| {lbl} | {m['precision']} | {m['recall']} | {m['f1']} | {m['support']} |")
    if has_deepseek:
        md += ["", "## DeepSeek Status", "DeepSeek labels present. Three-way comparison available."]
    else:
        md += ["", "## DeepSeek Status", "Awaiting DeepSeek labels."]
    (out / "validation_metrics_report.md").write_text("\n".join(md), encoding="utf-8")

    return result


def _update_three_way(path: Path, has_deepseek: bool):
    """Update three_way_comparison.csv with match status columns."""
    with open(path, "r", encoding="utf-8", newline="") as f:
        rows = list(csv.DictReader(f))

    for r in rows:
        mock = r.get("mock_label", "").strip()
        human = r.get("human_label", "").strip()
        deepseek = r.get("deepseek_label", "").strip()

        r["mock_vs_human_match"] = "TRUE" if (mock and human and mock == human) else "FALSE"
        r["mock_vs_deepseek_match"] = "TRUE" if (mock and deepseek and mock == deepseek) else ("FALSE" if deepseek else "AWAITING")
        r["deepseek_vs_human_match"] = "TRUE" if (deepseek and human and deepseek == human) else ("FALSE" if deepseek else "AWAITING")

        if not human and not deepseek:
            r["all_three_match"] = "AWAITING"
        elif not deepseek:
            r["all_three_match"] = "AWAITING_DEEPSEEK"
        elif mock == human == deepseek:
            r["all_three_match"] = "all_agree"
        elif mock == human and mock != deepseek:
            r["all_three_match"] = "mock_human_agree"
        elif deepseek == human and mock != deepseek:
            r["all_three_match"] = "deepseek_human_agree"
        else:
            r["all_three_match"] = "all_disagree"

    fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _cohen_kappa(a: list[str], b: list[str]) -> float:
    from sklearn.metrics import cohen_kappa_score
    try:
        k = cohen_kappa_score(a, b)
        return 0.0 if math.isnan(k) else float(k)
    except Exception:
        return 0.0


def _confusion_matrix(a: list[str], b: list[str]) -> dict:
    cm: dict[tuple[str, str], int] = {}
    for la, lb in zip(a, b):
        cm[(la, lb)] = cm.get((la, lb), 0) + 1
    return cm


def _save_confusion_csv(p: Path, cm: dict):
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow([""] + VALID_LABELS)
        for rl in VALID_LABELS:
            w.writerow([rl] + [cm.get((rl, cl), 0) for cl in VALID_LABELS])


def _save_error_csv(p: Path, rows: list[dict]):
    if not rows:
        p.write_text("", encoding="utf-8")
        return
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
