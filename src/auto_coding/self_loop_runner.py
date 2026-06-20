"""Phase 6 — SelfLoopRunner: orchestrates Phase 1-5 for pilot self-loop.

Can run a single round or auto-loop across rounds based on round_decision.
Does NOT freeze codebook. Does NOT run formal coding.
"""

from __future__ import annotations

import copy
import csv
import json
import random
from datetime import datetime
from pathlib import Path

ALL_PHASES = [
    "pilot-code", "compute-reliability", "analyze-disagreements",
    "adjudicate", "refine-codebook", "plan-recoding", "decide-round",
]


def _ts() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


class SelfLoopRunner:
    def __init__(self, project_dir: str | Path, mode: str = "mock",
                 kappa_threshold: float = 0.75, max_rounds: int = 5):
        self.project_dir = Path(project_dir)
        self.mode = mode
        self.kappa_threshold = kappa_threshold
        self.max_rounds = max_rounds
        self.state: dict = {}
        self.audit_lines: list[str] = []

    # ── Run single round ─────────────────────────────────

    def run_round(self, round_id: str = "round_01",
                  codebook_version: str = "v0.2_candidate") -> dict:
        """Run all Phase 3-5 steps for a single pilot round."""
        rd = self.project_dir / "04_pilot" / round_id
        rd.mkdir(parents=True, exist_ok=True)

        log = [f"# Round {round_id} — {_ts()}", "",
               f"Codebook: {codebook_version}", f"Mode: {self.mode}", ""]

        # Step 1: pilot-code
        from .coder import run_pilot_coding
        pilot_result = run_pilot_coding(
            str(self.project_dir), round_id=round_id,
            codebook_version=codebook_version, mode=self.mode,
        )
        log.append(f"pilot-code: A={pilot_result['coder_a_ok']}/{pilot_result['coder_a_count']} "
                   f"B={pilot_result['coder_b_ok']}/{pilot_result['coder_b_count']}")

        # Step 2: compute-reliability
        from .reliability import compute_reliability
        rel = compute_reliability(str(self.project_dir), round_id=round_id)
        kappa = rel["cohen_kappa"]
        pct = rel["percent_agreement"]
        log.append(f"reliability: Kappa={kappa:.4f}, Agreement={pct:.4f}")

        # Step 3: analyze-disagreements
        from .disagreement_analysis import analyze
        diag = analyze(str(self.project_dir), round_id=round_id)
        log.append(f"disagreements: label_dis={diag['label_disagreement_count']}, "
                   f"review={diag['review_candidate_count']}, adj_needed={diag['adjudication_count']}")

        # Step 4: adjudicate + decision_log + consensus
        from .adjudicator import adjudicate
        adj = adjudicate(str(self.project_dir), round_id=round_id,
                         codebook_version=codebook_version)
        from .decision_log import generate
        from .consensus_builder import build
        dlog = generate(str(self.project_dir), round_id=round_id)
        con = build(str(self.project_dir), round_id=round_id)
        log.append(f"adjudicate: {adj['total']} decisions "
                   f"(resolved={adj['resolved']}, unresolved={adj['unresolved']})")
        log.append(f"consensus: {con['total']} (agreement={con['agreement']}, "
                   f"adjudication={con['adjudication']}, unresolved={con['unresolved']})")

        # Step 5: refine-codebook
        target_cv = _next_codebook_version(codebook_version)
        from .codebook_refiner import refine
        ref = refine(str(self.project_dir), round_id=round_id,
                     source_version=codebook_version, target_version=target_cv,
                     mode=self.mode)
        log.append(f"refine-codebook: {ref['changes_count']} changes → {target_cv}")

        # Step 6: plan-recoding
        from .recoding_planner import plan
        pl = plan(str(self.project_dir), round_id=round_id)
        log.append(f"plan-recoding: requires_recoding={pl['requires_recoding']}, "
                   f"affected={len(pl['affected_unit_ids'])} units")

        # Step 7: decide-round
        from .round_controller import decide
        dec = decide(str(self.project_dir), round_id=round_id,
                     kappa_threshold=self.kappa_threshold,
                     max_pilot_rounds=self.max_rounds)
        log.append(f"decide-round: {dec['decision']} → {dec['next_action']}")
        log.append(f"  reason: {dec['reason']}")

        # Write round audit log
        (rd / "round_audit_log.md").write_text("\n".join(log), encoding="utf-8")

        return {
            "round_id": round_id, "kappa": kappa, "agreement": pct,
            "codebook_version": codebook_version,
            "target_codebook_version": target_cv,
            "changes": ref["changes_count"],
            "decision": dec["decision"],
            "next_action": dec["next_action"],
            "requires_recoding": pl["requires_recoding"],
            "carryover": pl["carryover_disagreement_unit_ids"],
            "affected_units": pl["affected_unit_ids"],
        }

    # ── Run auto-loop ────────────────────────────────────

    def run_loop(self, start_round_id: str = "round_01",
                 initial_codebook_version: str = "v0.2_candidate") -> dict:
        """Run self-loop: iterate rounds until stop condition."""
        self.audit_lines = [
            f"# Self-Loop Audit Log — {_ts()}", "",
            f"Project: {self.project_dir}", f"Max rounds: {self.max_rounds}",
            f"Kappa threshold: {self.kappa_threshold}", f"Mode: {self.mode}", "",
            "---", "",
        ]

        logs_dir = self.project_dir / "99_logs"
        logs_dir.mkdir(parents=True, exist_ok=True)

        round_id = start_round_id
        cv = initial_codebook_version
        rounds_completed = []
        stopped = False
        stop_reason = ""

        while len(rounds_completed) < self.max_rounds:
            result = self.run_round(round_id=round_id, codebook_version=cv)
            rounds_completed.append(round_id)

            self.audit_lines += [
                f"## {round_id}", "",
                f"- Kappa: {result['kappa']:.4f}",
                f"- Agreement: {result['agreement']:.4f}",
                f"- Codebook: {result['codebook_version']} → {result['target_codebook_version']}",
                f"- Changes: {result['changes']}",
                f"- Decision: {result['decision']}",
                f"- Next: {result['next_action']}",
                f"- Requires recoding: {result['requires_recoding']}",
                f"- Carryover: {len(result['carryover'])}",
                "",
            ]

            next_action = result["next_action"]
            if next_action in ("freeze_codebook_v1.0", "manual_review", "stop"):
                stopped = True
                stop_reason = f"Round {round_id}: decision={result['decision']}, next_action={next_action}"
                break

            if next_action == "run_round_02":
                round_id = _next_round_id(round_id)
                cv = result["target_codebook_version"]
                self._prepare_next_round_input(round_id, result)
                continue

            stopped = True
            stop_reason = f"Unknown next_action: {next_action}"
            break

        self.audit_lines += [
            "---", "",
            f"**Stopped**: {stopped}",
            f"**Reason**: {stop_reason}",
            f"**Rounds completed**: {rounds_completed}",
        ]
        (logs_dir / "self_loop_audit_log.md").write_text(
            "\n".join(self.audit_lines), encoding="utf-8")

        last_decision = result.get("decision", "")
        last_next_action = result.get("next_action", "")
        latest_cv = result.get("target_codebook_version", cv)
        freeze_allowed = last_next_action == "freeze_codebook_v1.0"
        block_reason = "" if freeze_allowed else (
            f"last_decision={last_decision}; explicit --force-freeze required"
        )

        state = {
            "project_dir": str(self.project_dir),
            "start_round_id": start_round_id,
            "current_round_id": round_id,
            "max_rounds": self.max_rounds,
            "rounds_completed": rounds_completed,
            "current_codebook_version": cv,
            "last_used_codebook_version": cv,
            "latest_generated_codebook_version": latest_cv,
            "freeze_candidate_version": latest_cv if freeze_allowed else None,
            "freeze_allowed": freeze_allowed,
            "freeze_block_reason": block_reason,
            "last_decision": last_decision,
            "last_next_action": last_next_action,
            "stopped": stopped,
            "stop_reason": stop_reason,
        }
        self.state = state
        with open(logs_dir / "self_loop_state.json", "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)

        return state

    # ── Helpers ──────────────────────────────────────────

    def _prepare_next_round_input(self, next_round_id: str, prev_result: dict):
        """Generate pilot_sample_units for the next round using carryover + affected."""
        rd = self.project_dir / "04_pilot" / next_round_id
        rd.mkdir(parents=True, exist_ok=True)

        # Load pilot sample from sampler output
        pilot_path = self.project_dir / "04_pilot" / "pilot_sample_units.csv"
        if not pilot_path.exists():
            return

        with open(pilot_path, "r", encoding="utf-8", newline="") as f:
            all_units = list(csv.DictReader(f))

        unit_map = {u["unit_id"]: u for u in all_units}

        # Carryover unresolved + affected units
        selected_ids = set(prev_result.get("carryover", []))
        selected_ids.update(prev_result.get("affected_units", []))

        selected = [unit_map[uid] for uid in selected_ids if uid in unit_map]

        # Fill with random samples from remaining
        remaining = [u for u in all_units if u["unit_id"] not in selected_ids]
        rng = random.Random(42)
        need = max(0, 30 - len(selected))
        fill = rng.sample(remaining, min(need, len(remaining)))
        selected.extend(fill)

        out_path = rd / f"pilot_sample_units_{next_round_id}.csv"
        if selected:
            fields = list(selected[0].keys())
            with open(out_path, "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
                w.writeheader(); w.writerows(selected)


def _next_round_id(current: str) -> str:
    try:
        num = int(current.replace("round_", "").replace("_", ""))
        return f"round_{num + 1:02d}"
    except ValueError:
        return f"{current}_next"


def _next_codebook_version(current: str) -> str:
    if "v0.2" in current:
        return "v0.3_candidate"
    if "v0.3" in current:
        return "v0.4_candidate"
    return f"{current}_next"
