"""Phase 7 freeze gate tests."""
import json, tempfile, yaml
from pathlib import Path
from auto_coding.codebook_schema import make_valid_code
from auto_coding.codebook_freezer import freeze


class TestFreezeGate:
    def _setup(self, d, freeze_allowed=False, next_action="stop_max_rounds", latest_cv="v0.3_candidate"):
        (d / "99_logs").mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
        st = {"freeze_allowed": freeze_allowed, "last_decision": "stop_max_rounds",
              "last_next_action": next_action, "latest_generated_codebook_version": latest_cv,
              "freeze_block_reason": "stop_max" if not freeze_allowed else ""}
        (d / "99_logs" / "self_loop_state.json").write_text(json.dumps(st))
        cb = {"version": latest_cv, "codes": [make_valid_code(c) for c in ["IS1","IS2","IS3","IS4"]]}
        with open(d / "01_codebook" / f"codebook_{latest_cv}.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)

    def test_blocks_stop_max_rounds(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), freeze_allowed=False)
            r = freeze(str(d))
            assert r["freeze_allowed"] is False

    def test_allows_freeze_when_allowed(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), freeze_allowed=True, next_action="freeze_codebook_v1.0")
            r = freeze(str(d))
            assert r["freeze_allowed"] is True

    def test_force_freeze_overrides_block(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), freeze_allowed=False)
            r = freeze(str(d), force=True)
            assert r["freeze_allowed"] is True

    def test_force_freeze_generates_report(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), freeze_allowed=False)
            freeze(str(d), force=True)
            assert (Path(d) / "01_codebook" / "codebook_freeze_report.md").exists()
            assert (Path(d) / "01_codebook" / "final_codebook_v1.0.yaml").exists()
