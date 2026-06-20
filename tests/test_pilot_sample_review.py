import csv, tempfile
from pathlib import Path
from auto_coding.pilot_sample_review import review

def _write_csv(path, rows):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

class TestReview:
    def test_basic_coverage(self):
        with tempfile.TemporaryDirectory() as d:
            pilot = Path(d) / "pilot.csv"
            units = Path(d) / "units.csv"
            _write_csv(pilot, [{"unit_id":"u1"}, {"unit_id":"u2"}])
            _write_csv(units, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"hello","context_before":"","context_after":""},
                {"unit_id":"u2","turn_id":"t2","group_id":"g1","speaker_id":"s1",
                 "unit_text":"world","context_before":"","context_after":""},
                {"unit_id":"u3","turn_id":"t3","group_id":"g2","speaker_id":"s2",
                 "unit_text":"test","context_before":"","context_after":""},
            ])
            result = review(pilot, units, Path(d)/"out")
            assert result["pilot_n"] == 2
            assert result["total_units"] == 3
            assert Path(result["csv_path"]).exists()
            assert Path(result["report_path"]).exists()

    def test_group_coverage_stats(self):
        with tempfile.TemporaryDirectory() as d:
            pilot = Path(d) / "pilot.csv"
            units = Path(d) / "units.csv"
            _write_csv(pilot, [{"unit_id":"u1"}])
            _write_csv(units, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"a","context_before":"","context_after":""},
                {"unit_id":"u2","turn_id":"t2","group_id":"g2","speaker_id":"s2",
                 "unit_text":"b","context_before":"","context_after":""},
            ])
            result = review(pilot, units, Path(d)/"out")
            assert result["needs_more_sampling"] is True

    def test_report_generated(self):
        with tempfile.TemporaryDirectory() as d:
            pilot = Path(d) / "pilot.csv"
            units = Path(d) / "units.csv"
            _write_csv(pilot, [{"unit_id":"u1"}])
            _write_csv(units, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"ok","context_before":"","context_after":""},
            ])
            result = review(pilot, units, Path(d)/"out")
            report = Path(result["report_path"]).read_text(encoding="utf-8")
            assert "样本总体情况" in report
            assert "Group 覆盖" in report
            assert "Speaker 覆盖" in report
