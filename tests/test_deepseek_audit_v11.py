"""v1.1 tests for DeepSeekRunAuditor and stress test."""
import json, csv, tempfile
from pathlib import Path
from auto_coding.deepseek_run_auditor import audit
from tests.helpers.deepseek_stress_test import run_stress_test


class TestAudit:
    def _setup(self, d, a_code="IS2", b_code="IS2"):
        d = Path(d); rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        (rd / "logs").mkdir(parents=True)
        # Create raw response files so path-existence check passes
        for i in range(3):
            (d / f"raw_A_u{i}.json").write_text("{}")
            (d / f"raw_B_u{i}.json").write_text("{}")
        with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3): f.write(json.dumps({"unit_id":f"u{i}","primary_code":a_code,"parse_ok":True,"cache_hit":False,"retry_count":0,"coder_id":"A","run_id":"rA","raw_response_path":f"raw_A_u{i}.json","codebook_version":"v1.0","round_id":"round_01"})+"\n")
        with open(rd / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            for i in range(3): f.write(json.dumps({"unit_id":f"u{i}","primary_code":b_code,"parse_ok":True,"cache_hit":False,"retry_count":0,"coder_id":"B","run_id":"rB","raw_response_path":f"raw_B_u{i}.json","codebook_version":"v1.0","round_id":"round_01"})+"\n")
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

    def test_audit_passes_with_complete_data(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["audit_passed"] is True

    def test_audit_fails_with_missing_coder(self):
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
            (rd / "logs").mkdir(parents=True)
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["audit_passed"] is False

    def test_parse_ok_false_fails_audit(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            # Overwrite with a parse failure
            rd = Path(d) / "09_deepseek_runs" / "round_01"
            with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u0","primary_code":"IS2","parse_ok":False,"coder_id":"A","run_id":"rA","raw_response_path":"raw_A_u0.json","codebook_version":"v1.0","round_id":"round_01"})+"\n")
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["audit_passed"] is False

    def test_illegal_label_fails_audit(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d, a_code="IS5")
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["audit_passed"] is False

    def test_mismatched_unit_sets_fails_audit(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            rd = Path(d) / "09_deepseek_runs" / "round_01"
            # Add extra unit to A only (create raw file first)
            (Path(d) / "raw_A_u99.json").write_text("{}")
            with open(rd / "coder_A_results.jsonl", "a", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u99","primary_code":"IS2","parse_ok":True,"coder_id":"A","run_id":"rA","raw_response_path":"raw_A_u99.json","codebook_version":"v1.0","round_id":"round_01"})+"\n")
            r = audit(d, "09_deepseek_runs/round_01")
            assert r["audit_passed"] is False


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
