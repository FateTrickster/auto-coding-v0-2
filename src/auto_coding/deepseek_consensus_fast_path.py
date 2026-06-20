"""v1.1 — Agreement fast path: skip adjudication for high-confidence agreement pairs."""

from __future__ import annotations

import csv, json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def run_fast_path(project_dir: str | Path, round_id: str,
                  confidence_threshold: float = 0.70) -> dict:
    root = Path(project_dir)
    src = root / "09_deepseek_runs" / round_id

    a = _jl(src / "coder_A_results.jsonl")
    b = _jl(src / "coder_B_results.jsonl")
    am = {r["unit_id"]: r for r in a}; bm = {r["unit_id"]: r for r in b}

    consensus = []
    watchlist = []
    fast = 0; excluded = 0; reasons = {"low_confidence": 0, "uncertain": 0, "parse_fail": 0}

    for uid in sorted(set(am) & set(bm)):
        ra = am[uid]; rb = bm[uid]
        la = ra.get("primary_code"); lb = rb.get("primary_code")

        if not ra.get("parse_ok") or not rb.get("parse_ok"):
            consensus.append({"unit_id": uid, "final_primary_code": None,
                              "consensus_source": "parse_failed", "decision_id": None, "unresolved": True})
            excluded += 1; reasons["parse_fail"] += 1
            continue

        if la != lb:
            consensus.append({"unit_id": uid, "final_primary_code": None,
                              "consensus_source": "disagreement", "decision_id": None, "unresolved": False})
            continue

        # Labels agree
        ca = float(ra.get("confidence", 0.8) or 0.8)
        cb = float(rb.get("confidence", 0.8) or 0.8)
        ua = ra.get("uncertain", False); ub = rb.get("uncertain", False)

        if ca >= confidence_threshold and cb >= confidence_threshold and not ua and not ub:
            consensus.append({"unit_id": uid, "final_primary_code": la,
                              "consensus_source": "agreement_fast_path", "decision_id": None, "unresolved": False})
            fast += 1
        else:
            watchlist.append({"unit_id": uid, "unit_text": "",
                              "coder_A_label": la, "coder_B_label": lb,
                              "A_confidence": ca, "B_confidence": cb,
                              "A_uncertain": ua, "B_uncertain": ub,
                              "reason": "low_confidence" if ca < confidence_threshold or cb < confidence_threshold else "uncertain"})
            excluded += 1
            if ca < confidence_threshold or cb < confidence_threshold: reasons["low_confidence"] += 1
            if ua or ub: reasons["uncertain"] += 1

    # Save
    _save_jl(src / "consensus_labels.jsonl", consensus)
    _save_watchlist(src / "low_confidence_agreement_items.csv", watchlist)
    _save_jl(src / "low_confidence_agreement_items.jsonl", watchlist)

    report = {
        "total_pairs": len(consensus),
        "agreement_pairs": fast + excluded,
        "fast_path_pairs": fast,
        "fast_path_rate": round(fast / max(len(consensus), 1), 4),
        "excluded_from_fast_path_count": excluded,
        "excluded_reasons": reasons,
    }
    with open(src / "agreement_fast_path_report.json", "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    (src / "agreement_fast_path_report.md").write_text(
        f"# Agreement Fast Path\n\n- Pairs: {len(consensus)}\n- Fast path: {fast}\n"
        f"- Excluded: {excluded}\n- Rate: {report['fast_path_rate']}\n"
        f"- Reasons: {reasons}\n", encoding="utf-8")
    return report


def _save_jl(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _save_watchlist(p: Path, items: list[dict]):
    if not items: return
    with open(p, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(items[0].keys()))
        w.writeheader(); w.writerows(items)
