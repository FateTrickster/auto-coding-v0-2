"""Phase 5 — RoundController: decide freeze/continue/stop for current round."""

from __future__ import annotations

import json
from pathlib import Path


def _load(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def decide(project_dir: str | Path, round_id: str = "round_01",
           kappa_threshold: float = 0.75, max_pilot_rounds: int = 5) -> dict:
    rd = Path(project_dir) / "04_pilot" / round_id

    m = _load(rd / "agreement_metrics.json")
    p = _load(Path(project_dir) / "01_codebook" / f"codebook_revision_proposal_{round_id}.json")
    pl = _load(rd / f"recoding_plan_{round_id}.json")
    diag = _load(rd / "disagreement_analysis.json")

    kappa = m.get("cohen_kappa", 0.0); pct = m.get("percent_agreement", 0.0)
    changes = p.get("changes", []); nc = len(changes)
    needs = pl.get("requires_recoding", False)
    un = diag.get("adjudication_count", 0)
    try: rn = int(round_id.replace("round_", "").replace("_", ""))
    except: rn = 1

    if rn >= max_pilot_rounds:
        decision, action, reason = "stop_max_rounds", "stop", f"Max rounds ({max_pilot_rounds})."
    elif un > 10:
        decision, action, reason = "manual_review_required", "manual_review", f"High unresolved ({un})."
    elif kappa >= kappa_threshold and not needs and nc == 0:
        decision, action, reason = "freeze_codebook", "freeze_codebook_v1.0", f"Kappa={kappa:.4f} >= {kappa_threshold}, no changes."
    elif kappa >= kappa_threshold and not needs and nc > 0:
        decision, action, reason = "next_pilot_round", "run_round_02", f"Kappa OK but {nc} non-recoding changes proposed."
    elif kappa >= kappa_threshold and needs:
        decision, action, reason = "next_pilot_round", "run_round_02", f"Kappa OK but recoding needed."
    elif kappa < kappa_threshold and nc > 0:
        decision, action, reason = "next_pilot_round", "run_round_02", f"Kappa={kappa:.4f} < {kappa_threshold}, {nc} changes."
    else:
        decision, action, reason = "manual_review_required", "manual_review", f"Kappa low, no changes."

    d = {"round_id": round_id, "kappa": kappa, "kappa_threshold": kappa_threshold,
         "percent_agreement": pct, "codebook_changes_count": nc,
         "requires_recoding": needs, "unresolved_count": un,
         "decision": decision, "reason": reason, "next_action": action}
    _save(rd / "round_decision.json", d)
    (rd / "round_audit_log.md").write_text(
        f"# Round Audit — {round_id}\n\n- Kappa: {kappa:.4f} (>{kappa_threshold})\n"
        f"- Agreement: {pct:.4f}\n- Changes: {nc}\n- **Decision**: {decision}\n"
        f"- **Next**: {action}\n- {reason}", encoding="utf-8")
    return d


def _save(p: Path, d: dict):
    with open(p, "w", encoding="utf-8") as f: json.dump(d, f, ensure_ascii=False, indent=2)
