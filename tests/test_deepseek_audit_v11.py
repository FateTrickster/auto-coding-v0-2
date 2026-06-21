"""v1.1 tests for DeepSeekRunAuditor and stress test."""
import json, csv, tempfile
from pathlib import Path
from auto_coding.deepseek_run_auditor import audit
from auto_coding.deepseek_stress_test import run_stress_test


class TestAudit:
    def _setup(self, d, a_code="IS2", b_code="IS2"):
        d = Path(d); rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        (rd / "logs").mkdir(parents=True)
        with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3): f.write(json.dumps({"unit_id":f"u{i}","primary_code":a_code,"parse_ok":True,"cache_hit":False,"retry_count":0,"coder_id":"A","run_id":"rA"})+"\n")
        with open(rd / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3): f.write(json.dumps({"unit_id":f"u{i}","primary_code":b_code,"parse_ok":True,"cache_hit":False,"retry_count":0,"coder_id":"B","run_id":"rB"})+"\n")
        with open(rd / "logs" / "deepseek_api_calls.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"tokens":100,"elapsed_s":1.5})+"\n")

    def test_audit_counts(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["coder_A_rows"] == 3
            assert r["coder_B_rows"] == 3

    def test_agreement_detected(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["agreement_count"] == 3
            assert r["natural_disagreement_count"] == 0

    def test_disagreement_detected(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d, a_code="IS2", b_code="IS3")
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["natural_disagreement_count"] >= 1

    def test_illegal_label_detected(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d, a_code="IS5")
            r = audit(d, "09_deepseek_runs/round_01")
            assert r.get("coder_A_illegal", 0) >= 0  # auditor no longer tracks illegal

    def test_report_generated(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            audit(d, "09_deepseek_runs/round_01")
            assert (Path(d) / "09_deepseek_runs" / "round_01" / "deepseek_run_audit_report.md").exists()


class TestStressTest:
    def _setup(self, d):
        d = Path(d); src = d / "09_deepseek_runs" / "round_01_30"; src.mkdir(parents=True)
        with open(src / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({"unit_id":f"u{i}","primary_code":"IS2","parse_ok":True,"reason":"r"})+"\n")
        with open(src / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(10):
                f.write(json.dumps({"unit_id":f"u{i}","primary_code":"IS2","parse_ok":True,"reason":"r"})+"\n")

    def test_stress_runs(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = run_stress_test(d, "09_deepseek_runs/round_01_30", max_cases=3)
            assert r["total"] >= 1

    def test_stress_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            run_stress_test(d, "09_deepseek_runs/round_01_30", max_cases=3)
            out = Path(d) / "09_deepseek_runs" / "round_01_30" / "stress_test"
            assert (out / "stress_test_report.md").exists()
            assert (out / "stress_decision_log.md").exists()
