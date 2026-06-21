import csv, tempfile
from pathlib import Path
from auto_coding.unit_table_validator import validate

def _write_csv(path, rows, fields=None):
    with open(path, 'w', encoding='utf-8', newline='') as f:
        w = csv.DictWriter(f, fieldnames=fields or list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)

class TestValidate:
    def test_basic_validation(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "units.csv"
            _write_csv(csv_path, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"hello world","context_before":"","context_after":""},
                {"unit_id":"u2","turn_id":"t2","group_id":"g1","speaker_id":"s2",
                 "unit_text":"hi","context_before":"","context_after":"prev"},
            ])
            result = validate(csv_path, Path(d)/"out")
            assert result["total_units"] == 2
            assert Path(result["csv_path"]).exists()
            assert Path(result["report_path"]).exists()

    def test_duplicate_id_detected(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "units.csv"
            _write_csv(csv_path, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"a","context_before":"","context_after":""},
                {"unit_id":"u1","turn_id":"t2","group_id":"g1","speaker_id":"s2",
                 "unit_text":"b","context_before":"","context_after":""},
            ])
            result = validate(csv_path, Path(d)/"out")
            assert result["issues_count"] >= 1

    def test_short_text_flag(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "units.csv"
            _write_csv(csv_path, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"ok","context_before":"","context_after":""},
            ])
            result = validate(csv_path, Path(d)/"out")
            with open(result["csv_path"], encoding='utf-8', newline='') as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["short_text_flag"] == "TRUE"

    def test_long_text_flag(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "units.csv"
            _write_csv(csv_path, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"x" * 150,"context_before":"","context_after":""},
            ])
            result = validate(csv_path, Path(d)/"out")
            with open(result["csv_path"], encoding='utf-8', newline='') as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["long_text_flag"] == "TRUE"

    def test_missing_context_flag(self):
        with tempfile.TemporaryDirectory() as d:
            csv_path = Path(d) / "units.csv"
            _write_csv(csv_path, [
                {"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "unit_text":"test","context_before":"","context_after":""},
            ])
            result = validate(csv_path, Path(d)/"out")
            with open(result["csv_path"], encoding='utf-8', newline='') as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["missing_context_flag"] == "TRUE"


class TestSchemaGate:
    def test_missing_one_field(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "group_id": "g1", "speaker_id": "s1", "unit_text": "t"}],
                       fields=["unit_id", "group_id", "speaker_id", "unit_text"])
            try:
                validate(p, Path(d) / "out")
                assert False, "Should raise"
            except ValueError as e:
                assert "turn_id" in str(e)

    def test_missing_multiple_fields(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "unit_text": "t"}],
                       fields=["unit_id", "unit_text"])
            try:
                validate(p, Path(d) / "out")
                assert False
            except ValueError as e:
                assert "group_id" in str(e) and "speaker_id" in str(e)

    def test_empty_csv(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            p.write_text("")
            try:
                validate(p, Path(d) / "out")
                assert False
            except ValueError:
                pass

    def test_no_output_on_schema_fail(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "text": "t"}],
                       fields=["unit_id", "text"])
            out = Path(d) / "out"
            try:
                validate(p, out)
            except ValueError:
                pass
            assert not (out / "unit_table_v0.1.csv").exists()


class TestMultiFunction:
    def test_chinese_question_mark(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "turn_id": "t1", "group_id": "g1",
                            "speaker_id": "s1", "unit_text": "这是第一步？然后继续。",
                            "context_before": "", "context_after": ""}])
            r = validate(p, Path(d) / "out")
            with open(r["csv_path"], encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["possible_multi_function_flag"] == "TRUE"

    def test_question_without_clauses(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "turn_id": "t1", "group_id": "g1",
                            "speaker_id": "s1", "unit_text": "这是第一步？",
                            "context_before": "", "context_after": ""}])
            r = validate(p, Path(d) / "out")
            with open(r["csv_path"], encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["possible_multi_function_flag"] == "FALSE"

    def test_clauses_without_question(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "units.csv"
            _write_csv(p, [{"unit_id": "u1", "turn_id": "t1", "group_id": "g1",
                            "speaker_id": "s1", "unit_text": "第一步。第二步。第三步。",
                            "context_before": "", "context_after": ""}])
            r = validate(p, Path(d) / "out")
            with open(r["csv_path"], encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            assert rows[0]["possible_multi_function_flag"] == "FALSE"
