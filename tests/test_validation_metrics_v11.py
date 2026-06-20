"""v1.1 tests for ValidationMetrics."""
import csv, tempfile
from pathlib import Path
from auto_coding.validation_metrics import compute


class TestCompute:
    def _setup(self, d: Path, human_labels: list[str]):
        (d / "08_validation").mkdir(parents=True)
        fields = ["unit_id", "unit_text", "mock_final_code", "human_label", "audit_status",
                  "is_disagreement_sample", "deepseek_label"]
        with open(d / "08_validation" / "human_audit_template.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader()
            for i, hl in enumerate(human_labels):
                w.writerow({"unit_id": f"u{i}", "unit_text": f"t{i}", "mock_final_code": "IS2",
                            "human_label": hl, "audit_status": "labeled", "is_disagreement_sample": "FALSE"})

    def test_awaiting_when_no_labels(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), ["", ""])
            r = compute(str(d))
            assert r["status"] == "AWAITING_HUMAN_LABELS"

    def test_mock_vs_human_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), ["IS2", "IS2", "IS3"])
            r = compute(str(d))
            assert r["mock_vs_human_agreement"] >= 0.5

    def test_kappa_computed(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), ["IS2", "IS2", "IS3", "IS3", "IS1", "IS1", "IS4", "IS4"])
            r = compute(str(d))
            assert r["mock_vs_human_kappa"] is not None

    def test_no_deepseek_ok(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), ["IS2", "IS2"])
            r = compute(str(d))
            assert r["has_deepseek"] is False

    def test_error_cases_generated(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), ["IS2", "IS3"])  # 2nd disagrees with mock(IS2)
            r = compute(str(d))
            assert (Path(d) / "08_validation" / "mock_vs_human_error_cases.csv").exists()
