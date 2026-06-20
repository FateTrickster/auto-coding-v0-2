"""Phase 7 — CodebookFreezer: freeze codebook with gate control."""

from __future__ import annotations

import copy, json
from pathlib import Path
import yaml


def freeze(project_dir: str | Path, force: bool = False) -> dict:
    project_dir = Path(project_dir)
    cb_dir = project_dir / "01_codebook"
    pr_dir = project_dir / "02_prompts"

    state = {}
    sp = project_dir / "99_logs" / "self_loop_state.json"
    if sp.exists():
        state = json.loads(sp.read_text(encoding="utf-8"))

    last_decision = state.get("last_decision", "unknown")
    freeze_allowed = state.get("freeze_allowed", False)
    latest_cv = state.get("latest_generated_codebook_version", "v0.3_candidate")

    if not force and not freeze_allowed:
        reason = state.get("freeze_block_reason", f"last_decision={last_decision}")
        (cb_dir / "codebook_freeze_blocked_report.md").write_text(
            f"# Freeze Blocked\n\n- Decision: {last_decision}\n- Reason: {reason}\n"
            f"- Use --force-freeze only after manual review.\n", encoding="utf-8")
        return {"freeze_allowed": False, "reason": reason}

    src_path = cb_dir / f"codebook_{latest_cv}.yaml"
    if not src_path.exists():
        for cv in ["v0.5_candidate","v0.4_candidate","v0.3_candidate","v0.2_candidate"]:
            alt = cb_dir / f"codebook_{cv}.yaml"
            if alt.exists(): src_path = alt; latest_cv = cv; break

    if not src_path.exists():
        return {"freeze_allowed": False, "reason": "No candidate codebook found."}

    with open(src_path, encoding="utf-8") as f:
        codebook = yaml.safe_load(f)

    frozen = copy.deepcopy(codebook)
    frozen["version"] = "v1.0"
    frozen["frozen"] = True
    frozen["source_candidate_version"] = latest_cv
    frozen["freeze_round_id"] = state.get("current_round_id", "")
    frozen["forced"] = force and not freeze_allowed

    _yaml(cb_dir / "final_codebook_v1.0.yaml", frozen)
    from .prompt_renderer import render
    render(str(cb_dir / "final_codebook_v1.0.yaml"), pr_dir, expected_version="v1.0")

    (cb_dir / "codebook_freeze_report.md").write_text(
        f"# Freeze Report\n\n- Source: {latest_cv}\n- Frozen as: v1.0\n"
        f"- Forced: {force and not freeze_allowed}\n", encoding="utf-8")
    return {"freeze_allowed": True, "forced": force and not freeze_allowed,
            "source_version": latest_cv}


def _yaml(p: Path, d: dict):
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(d, f, allow_unicode=True, default_flow_style=False, sort_keys=False)
