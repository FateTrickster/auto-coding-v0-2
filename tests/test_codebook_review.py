"""Tests for codebook_review.py — frozen v0.1 Schema: 12 fields, list[str] content."""
import json, tempfile, yaml, pytest
from pathlib import Path
from auto_coding.codebook_review import review, REQUIRED_FIELDS, CRITICAL_FIELDS, EXPECTED_CODE_IDS


def _write(path, codes):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"version": "v0.1", "codes": codes}, f, allow_unicode=True)


def _vc(cid="IS1"):
    return {"code_id": cid, "code_name": "T", "definition": ["d"], "inclusion_rules": ["i"],
            "exclusion_rules": ["e"], "typical_markers": ["t"], "counter_markers": ["c"],
            "positive_examples": ["p"], "negative_examples": ["n"], "boundary_cases": ["b"],
            "low_information_rules": ["l"], "notes": ["o"]}


class TestValid:
    def test_all_4_pass(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            r = review(Path(d) / "cb.yaml", Path(d) / "out")
            assert r["can_proceed"] is True

    def test_all_good(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            review(Path(d) / "cb.yaml", Path(d) / "out")
            data = json.loads((Path(d) / "out" / "codebook_missing_fields.json").read_text(encoding="utf-8"))
            assert all(c["severity"] == "good" for c in data["codes"])

    def test_12_fields_zero(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            review(Path(d) / "cb.yaml", Path(d) / "out")
            data = json.loads((Path(d) / "out" / "codebook_missing_fields.json").read_text(encoding="utf-8"))
            for f in REQUIRED_FIELDS:
                s = data["field_statistics"][f]
                assert s["missing"] == 0 and s["invalid_type"] == 0 and s["empty"] == 0 and s["blank_items"] == 0

    def test_def_list_ok(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]
            codes[0]["definition"] = ["a", "b"]
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is True

    def test_notes_list_ok(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]
            codes[0]["notes"] = ["x", "y"]
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is True

    def test_generates_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            review(Path(d) / "cb.yaml", Path(d) / "out")
            assert (Path(d) / "out" / "codebook_review_report_v0.1.md").exists()
            assert (Path(d) / "out" / "codebook_missing_fields.json").exists()


class TestFieldErrors:
    def test_def_empty_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["definition"] = []
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_def_blank_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["definition"] = [""]
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_def_wrong_type_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["definition"] = "str"
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_def_int_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["definition"] = 123
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_code_name_empty_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["code_name"] = ""
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_non_string_item_fails(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["inclusion_rules"] = ["ok", 123]
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False


class TestStructureErrors:
    def test_empty_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("")
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_root_list(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("- x")
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_no_codes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("version: v0.1")
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_codes_not_list(self):
        with tempfile.TemporaryDirectory() as d:
            with open(Path(d) / "cb.yaml", "w") as f: yaml.dump({"codes": "x"}, f)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_missing_is4(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in ["IS1","IS2","IS3"]])
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_duplicate_is1(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc("IS1"), _vc("IS1"), _vc("IS2"), _vc("IS3")])
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_unknown_is5(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes.append(_vc("IS5"))
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_wrong_order(self):
        with tempfile.TemporaryDirectory() as d:
            _write(Path(d) / "cb.yaml", [_vc(c) for c in ["IS2","IS1","IS3","IS4"]])
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_unknown_field(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["extra"] = "x"
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False


class TestCriticalFields:
    def test_def_missing(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; del codes[0]["definition"]
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_incl_empty(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["inclusion_rules"] = []
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_excl_empty(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["exclusion_rules"] = []
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False

    def test_boundary_empty(self):
        with tempfile.TemporaryDirectory() as d:
            codes = [_vc(c) for c in EXPECTED_CODE_IDS]; codes[0]["boundary_cases"] = []
            _write(Path(d) / "cb.yaml", codes)
            assert review(Path(d) / "cb.yaml", Path(d) / "out")["can_proceed"] is False
