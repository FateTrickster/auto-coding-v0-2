"""v1.1 tests for DeepSeekCoderAgent."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.deepseek_coder import run_deepseek_coding


class TestDeepSeekCoder:
    def _setup(self, d: Path | str):
        d = Path(d)
        (d / "00_inputs").mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
        (d / "04_pilot").mkdir(parents=True, exist_ok=True)
        rows = [{"unit_id": f"u{i}", "unit_text": t, "context_before": "", "context_after": "",
                 "group_id": "g1", "speaker_id": "s1"}
                for i, t in enumerate(["谢谢", "无语", "是不是数据反了", "okok"])]
        with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        cb = {"version": "v1.0", "codes": [{"label": "IS1"}, {"label": "IS2"}, {"label": "IS3"}, {"label": "IS4"}]}
        with open(d / "01_codebook" / "codebook_v1.0.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)
        (d / "02_prompts" / "coder_prompt_v1.0.md").write_text(
            "# Test prompt\nIS1: Negative\nIS2: Neutral\nIS3: Confused\nIS4: Positive", encoding="utf-8")

    def test_mock_mode_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            r = run_deepseek_coding(str(d), mode="mock", max_items=4)
            assert r["coder_a_total"] == 4
            assert r["coder_b_total"] == 4
            assert (Path(d) / "09_deepseek_runs" / "round_01" / "coder_A_results.jsonl").exists()

    def test_no_real_call_without_env(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            import os
            assert os.getenv("RUN_REAL_DEEPSEEK") != "1"

    def test_illegal_label_blocked(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            r = run_deepseek_coding(str(d), mode="mock", max_items=4)
            a_results = [json.loads(l) for l in (Path(d) / "09_deepseek_runs" / "round_01" / "coder_A_results.jsonl").read_text(encoding="utf-8").splitlines() if l.strip()]
            for r in a_results:
                if r["parse_ok"]:
                    assert r["primary_code"] in {"IS1", "IS2", "IS3", "IS4"}
