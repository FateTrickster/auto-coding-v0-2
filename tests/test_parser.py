"""Tests for robust JSON parsing."""

import pytest

from auto_coding.parser import robust_json_parse, validate_coding_output

VALID = ("IS1", "IS2", "IS3", "IS4")


class TestRobustJsonParse:
    def test_pure_json(self):
        text = '{"label": "IS2", "confidence": 0.9}'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS2"

    def test_markdown_json_block(self):
        text = 'Here is the result:\n\n```json\n{"label": "IS3", "confidence": 0.85}\n```\n\nDone.'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS3"

    def test_generic_code_block(self):
        text = '```\n{"label": "IS4"}\n```'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS4"

    def test_json_with_surrounding_text(self):
        text = 'Some explanation... {"label": "IS1", "confidence": 0.7} and more text.'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS1"

    def test_invalid_json(self):
        text = 'not json at all {broken'
        result, err = robust_json_parse(text)
        assert result is None
        assert err is not None

    def test_empty_text(self):
        result, err = robust_json_parse("")
        assert result is None
        assert err is not None

    def test_nested_json_objects(self):
        text = 'Outer {"label": "IS2", "inner": {"x": 1}} trailing'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS2"


class TestJsonRepair:
    def test_unescaped_quotes_in_code_block(self):
        """LLM wrote \"okok\" unescaped inside a JSON string."""
        text = '```json\n{"label": "IS2", "rationale": "确认\"okok\"无感叹号"}\n```'
        result, err = robust_json_parse(text)
        assert err is None, f"Should repair: {err}"
        assert result["label"] == "IS2"
        assert "okok" in result["rationale"]

    def test_unescaped_quotes_chinese_context(self):
        """Unescaped quotes with Chinese text around them."""
        text = '```json\n{"label": "IS3", "why_not_alternative": "如果是\"我来写吗\"则为IS2"}\n```'
        result, err = robust_json_parse(text)
        assert err is None, f"Should repair: {err}"
        assert result["label"] == "IS3"

    def test_trailing_comma(self):
        """Trailing comma before }."""
        text = '{"label": "IS2", "confidence": 0.9,}'
        result, err = robust_json_parse(text)
        assert err is None, f"Should repair trailing comma: {err}"
        assert result["label"] == "IS2"

    def test_normal_json_unaffected(self):
        """Normal JSON should still parse correctly."""
        text = '{"label": "IS2", "confidence": 0.9, "rationale": "测试"}'
        result, err = robust_json_parse(text)
        assert err is None
        assert result["label"] == "IS2"

    def test_unfixable_json_still_fails(self):
        """Completely broken JSON should still fail."""
        text = "not json at all {broken[[["
        result, err = robust_json_parse(text)
        assert result is None


class TestValidateCodingOutput:
    def test_valid_output(self):
        parsed = {"label": "IS2", "confidence": 0.9, "rationale": "test"}
        result, err = validate_coding_output(parsed, VALID)
        assert err is None
        assert result["label"] == "IS2"

    def test_invalid_label(self):
        parsed = {"label": "IS5"}
        result, err = validate_coding_output(parsed, VALID)
        assert result is None
        assert "Invalid label" in err

    def test_missing_label(self):
        parsed = {"confidence": 0.9}
        result, err = validate_coding_output(parsed, VALID)
        assert result is None

    def test_alternative_label_null(self):
        parsed = {"label": "IS2", "alternative_label": None}
        result, err = validate_coding_output(parsed, VALID)
        assert err is None
        assert result["alternative_label"] is None

    def test_alternative_label_valid(self):
        parsed = {"label": "IS2", "alternative_label": "IS3"}
        result, err = validate_coding_output(parsed, VALID)
        assert err is None
        assert result["alternative_label"] == "IS3"

    def test_defaults_filled(self):
        parsed = {"label": "IS2"}
        result, err = validate_coding_output(parsed, VALID)
        assert err is None
        assert result["rationale"] == ""
        assert result["uncertainty"] == "无"
