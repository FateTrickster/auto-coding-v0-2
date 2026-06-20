"""v1.1 tests for HumanAuditValidator."""
import csv, tempfile
from pathlib import Path
from auto_coding.human_audit_validator import write_instructions, validate


class TestWriteInstructions:
    def test_generates(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); (b / "08_validation").mkdir(parents=True)
            p = write_instructions(str(b))
            assert Path(p).exists()
            assert "IS1" in Path(p).read_text(encoding="utf-8")


class TestValidate:
    def _write_template(self, d: Path, rows: list[dict]):
        (d / "08_validation").mkdir(parents=True, exist_ok=True)
        fields = ["unit_id", "unit_text", "mock_final_code", "human_label",
                  "human_confidence", "human_rationale", "human_notes", "audit_status"]
        with open(d / "08_validation" / "human_audit_template.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)

    def test_awaiting_status(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_template(Path(d), [{"unit_id": "u1", "human_label": "", "audit_status": ""}])
            r = validate(str(d))
            assert r["status"] == "AWAITING_HUMAN_LABELS"

    def test_detects_illegal_label(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_template(Path(d), [{"unit_id": "u1", "human_label": "IS5", "audit_status": "labeled"}])
            r = validate(str(d))
            assert r["illegal_label_count"] >= 1

    def test_ready_when_all_labeled(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_template(Path(d), [{"unit_id": "u1", "human_label": "IS2", "audit_status": "labeled"},
                                           {"unit_id": "u2", "human_label": "IS3", "audit_status": "labeled"}])
            r = validate(str(d))
            assert r["ready_for_metrics"] is True
            assert r["status"] == "HUMAN_LABELS_READY"

    def test_detects_duplicate_ids(self):
        with tempfile.TemporaryDirectory() as d:
            self._write_template(Path(d), [{"unit_id": "u1", "human_label": "IS2", "audit_status": "labeled"},
                                           {"unit_id": "u1", "human_label": "IS3", "audit_status": "labeled"}])
            r = validate(str(d))
            assert r["duplicate_ids"] >= 1
