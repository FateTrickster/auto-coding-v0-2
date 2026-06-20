"""v1.1 tests for independence auditor and risk sample selector."""
import json, tempfile
from pathlib import Path
from auto_coding.deepseek_independence_auditor import audit
from auto_coding.deepseek_sample_selector import select_risk_sample


class TestIndependence:
    def _setup(self, d):
        d = Path(d); rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"unit_id":f"u{i}","primary_code":"IS2","parse_ok":True,
                    "coder_id":"A","run_id":"round_01_A","raw_response_path":f"raw_A_u{i}.json",
                    "cache_hit":False,"timestamp":"2024-01-01T00:00:0{i}"})+"\n")
        with open(rd / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3):
                f.write(json.dumps({"unit_id":f"u{i}","primary_code":"IS3","parse_ok":True,
                    "coder_id":"B","run_id":"round_01_B","raw_response_path":f"raw_B_u{i}.json",
                    "cache_hit":False,"timestamp":"2024-01-01T00:00:1{i}"})+"\n")

    def test_run_ids_differ(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["independence_ok"] is True

    def test_raw_paths_differ(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = audit(d, "09_deepseek_runs/round_01")
            checks = {c["check"]: c["passed"] for c in r["checks"]}
            assert checks.get("raw_paths_differ", False) is True


class TestRiskSample:
    def test_generates_sample(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d); (d / "07_final").mkdir(parents=True)
            (d / "00_inputs").mkdir(parents=True)
            import csv
            with open(d / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","final_primary_code","group_id","speaker_id"])
                w.writeheader()
                for i in range(50):
                    kw = ["是不是","谢谢","okok","无语","我们来","好的","没看懂","不是吧","那先算","感觉"] * 5
                    w.writerow({"unit_id":f"u{i}","unit_text":kw[i],"final_primary_code":"IS2","group_id":"g1","speaker_id":"s1"})
            m = select_risk_sample(str(d), sample_size=20)
            assert m["actual_sample_size"] >= 1
            assert "unit_ids" in m
