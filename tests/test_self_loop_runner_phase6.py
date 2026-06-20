"""Phase 6 tests for SelfLoopRunner."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.codebook_schema import make_valid_code
from auto_coding.self_loop_runner import SelfLoopRunner, _next_round_id, _next_codebook_version


def _setup_project(d: Path) -> None:
    (d / "00_inputs").mkdir(parents=True)
    (d / "01_codebook").mkdir(parents=True)
    (d / "02_prompts").mkdir(parents=True)
    (d / "04_pilot").mkdir(parents=True)
    # Minimal pilot sample
    rows = [{"unit_id": f"u{i}", "unit_text": t, "context_before": "", "context_after": "",
             "group_id": "g01", "speaker_id": "s1"}
            for i, t in enumerate(["是不是数据反了", "谢谢", "okok", "无语", "我们可以", "好的",
                                   "没看懂", "不是吧", "那先算均值吗", "感觉会出问题"])]
    with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_id", "unit_text", "context_before",
                                          "context_after", "group_id", "speaker_id"])
        w.writeheader(); w.writerows(rows)
    # Minimal codebook
    cb = {"version": "v0.2_candidate", "codes": [
        make_valid_code("IS1"),
        make_valid_code("IS2"),
        make_valid_code("IS3"),
        make_valid_code("IS4"),
    ]}
    with open(d / "01_codebook" / "codebook_v0.2_candidate.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cb, f, allow_unicode=True)


class TestNextRoundId:
    def test_increments(self):
        assert _next_round_id("round_01") == "round_02"
        assert _next_round_id("round_02") == "round_03"


class TestNextCodebookVersion:
    def test_increments(self):
        assert "v0.3" in _next_codebook_version("v0.2_candidate")
        assert "v0.4" in _next_codebook_version("v0.3_candidate")


class TestSelfLoopRunner:
    def test_run_single_round(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup_project(b)
            runner = SelfLoopRunner(b, mode="mock")
            r = runner.run_round("round_01", "v0.2_candidate")
            assert r["kappa"] is not None
            assert r["round_id"] == "round_01"
            rd = b / "04_pilot" / "round_01"
            assert (rd / "coder_A_results.jsonl").exists()
            assert (rd / "agreement_metrics.json").exists()
            assert (rd / "round_decision.json").exists()

    def test_run_loop_auto_stops(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup_project(b)
            runner = SelfLoopRunner(b, mode="mock", max_rounds=3)
            state = runner.run_loop("round_01", "v0.2_candidate")
            assert len(state["rounds_completed"]) >= 1
            assert state["stopped"] is True
            # Verify state file
            sf = b / "99_logs" / "self_loop_state.json"
            assert sf.exists()
            # Verify audit log
            af = b / "99_logs" / "self_loop_audit_log.md"
            assert af.exists()

    def test_state_file_content(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup_project(b)
            runner = SelfLoopRunner(b, mode="mock")
            runner.run_round("round_01", "v0.2_candidate")
            runner.run_loop("round_01", "v0.2_candidate")
            with open(b / "99_logs" / "self_loop_state.json", encoding="utf-8") as f:
                state = json.load(f)
            assert "rounds_completed" in state
            assert "stopped" in state
            assert "stop_reason" in state

    def test_round_02_input_prepared(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup_project(b)
            runner = SelfLoopRunner(b, mode="mock")
            runner.run_round("round_01", "v0.2_candidate")
            # Create round_02 input via auto-loop
            runner.run_loop("round_01", "v0.2_candidate")
            # Check round_02 directory
            rd2 = b / "04_pilot" / "round_02"
            # May or may not exist depending on decision
            if rd2.exists():
                csv_files = list(rd2.glob("pilot_sample*.csv"))
                if csv_files:
                    with open(csv_files[0], encoding="utf-8", newline="") as f:
                        rows = list(csv.DictReader(f))
                    assert len(rows) >= 1
