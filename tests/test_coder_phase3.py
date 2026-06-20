"""Tests for Phase 3 MockCoderAgent."""
import csv, json, tempfile
from pathlib import Path
from auto_coding.coder import MockCoderAgent, run_pilot_coding


def _write_pilot_csv(path: Path, rows: list[dict]) -> None:
    fields = ["unit_id", "unit_text", "context_before", "context_after",
              "group_id", "speaker_id"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


class TestMockCoderAgent:
    def test_coder_a_basic(self):
        agent = MockCoderAgent(coder_id="A", seed=42)
        units = [{"unit_id": "u1", "unit_text": "是不是数据反了"}]
        results = agent.code(units, "v0.2")
        assert len(results) == 1
        assert results[0]["coder_id"] == "A"
        assert results[0]["primary_code"] in ("IS1", "IS2", "IS3", "IS4")
        assert results[0]["parse_ok"] is True

    def test_coder_b_different_seed(self):
        units = [{"unit_id": "u1", "unit_text": "我来写"}]
        a = MockCoderAgent("A", 42).code(units, "v0.2")
        b = MockCoderAgent("B", 42).code(units, "v0.2")
        assert a[0]["coder_id"] == "A"
        assert b[0]["coder_id"] == "B"

    def test_empty_text(self):
        agent = MockCoderAgent("A")
        results = agent.code([{"unit_id": "u1", "unit_text": "   "}], "v0.2")
        assert results[0]["parse_ok"] is False

    def test_all_fields_present(self):
        agent = MockCoderAgent("A")
        results = agent.code([{"unit_id": "u1", "unit_text": "谢谢大家"}], "v0.2")
        r = results[0]
        for field in ["unit_id", "primary_code", "secondary_code", "confidence",
                      "uncertain", "needs_discussion", "evidence_span", "reason",
                      "codebook_version", "coder_id", "parse_ok"]:
            assert field in r, f"Missing field: {field}"


class TestRunPilotCoding:
    def test_full_run(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            (base / "04_pilot").mkdir(parents=True, exist_ok=True)
            rows = [{"unit_id": f"u{i}", "unit_text": t, "context_before": "",
                     "context_after": "", "group_id": "g01", "speaker_id": "s1"}
                    for i, t in enumerate(["是不是数据反了", "谢谢", "okok", "无语",
                                           "我们可以先写", "好的", "没看懂", "不是吧",
                                           "那先计算均值吗", "感觉会出问题"])]
            _write_pilot_csv(base / "04_pilot" / "pilot_sample_units.csv", rows)

            result = run_pilot_coding(str(base))
            assert result["coder_a_count"] == 10
            assert result["coder_b_count"] == 10

            round_dir = Path(result["round_dir"])
            assert (round_dir / "coder_A_results.jsonl").exists()
            assert (round_dir / "coder_B_results.jsonl").exists()
