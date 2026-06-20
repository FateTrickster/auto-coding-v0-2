"""Phase 5 tests for RoundController."""
import json, tempfile
from pathlib import Path
from auto_coding.round_controller import decide


class TestDecide:
    def _setup(self, d, kappa=0.96, pct=0.99, changes=0, needs=False, un=1, rn="round_01"):
        rd = d / "04_pilot" / rn; rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        (rd / "agreement_metrics.json").write_text(json.dumps({"cohen_kappa": kappa, "percent_agreement": pct}))
        (d / "01_codebook" / f"codebook_revision_proposal_{rn}.json").write_text(json.dumps({"changes": [{} for _ in range(changes)]}))
        (rd / f"recoding_plan_{rn}.json").write_text(json.dumps({"requires_recoding": needs}))
        (rd / "disagreement_analysis.json").write_text(json.dumps({"adjudication_count": un}))

    def test_freeze_when_kappa_ok_no_changes(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), kappa=0.96, changes=0, needs=False)
            r = decide(str(d))
            assert r["decision"] == "freeze_codebook"

    def test_next_round_when_kappa_ok_but_needs_recoding(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), kappa=0.96, changes=1, needs=True)
            r = decide(str(d))
            assert r["decision"] == "next_pilot_round"

    def test_next_round_when_kappa_low_with_changes(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), kappa=0.60, changes=1, needs=True)
            r = decide(str(d))
            assert r["decision"] == "next_pilot_round"

    def test_manual_review_when_high_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), kappa=0.96, un=15)
            r = decide(str(d))
            assert r["decision"] == "manual_review_required"

    def test_stop_max_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), kappa=0.96, rn="round_05")
            r = decide(str(d), round_id="round_05", max_pilot_rounds=5)
            assert r["decision"] == "stop_max_rounds"
