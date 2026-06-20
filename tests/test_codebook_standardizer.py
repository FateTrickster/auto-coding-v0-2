"""Tests for codebook_standardizer.py — strict state machine parser."""
import tempfile, yaml, pytest
from pathlib import Path
from auto_coding.codebook_standardizer import parse_markdown_codebook, standardize, ParseError

VALID_MD = """## IS1 TestCode

**定义**:
- This is a test definition.

**包含标准**:
- Inclusion rule 1.
- Inclusion rule 2.

**排除标准**:
- Exclusion rule 1.

**典型标记词**:
- Typical marker 1.

**反例标记词**:
- Counter marker 1.

**正例**:
- Positive example 1.

**反例**:
- Negative example 1.

**与其他标签的边界**:
- Boundary case 1.

**低信息文本处理**:
- Low info rule 1.

**备注**:
- Note 1.

---

# 附录：Test Appendix

## 规则 1：Test

- Appendix content.
"""


def _full_md(label_name="TestCode"):
    """Generate a complete 4-label Markdown."""
    parts = []
    for is_id, cn in [("IS1", "消极"), ("IS2", "中立"), ("IS3", "困惑"), ("IS4", "积极")]:
        parts.append(f"## {is_id} {cn}")
        for fn in ["定义", "包含标准", "排除标准", "典型标记词", "反例标记词", "正例", "反例", "与其他标签的边界", "低信息文本处理", "备注"]:
            parts.append(f"")
            parts.append(f"**{fn}**:")
            parts.append(f"- {is_id} {fn} item 1.")
            parts.append(f"- {is_id} {fn} item 2.")
        parts.append("")
        parts.append("---")
        parts.append("")
    parts.append("")
    parts.append("# 附录：Locked Rules")
    parts.append("")
    parts.append("## 规则 1：Test")
    parts.append("- Rule content.")
    return "\n".join(parts)


class TestParseValid:
    def test_parses_full_4_labels(self):
        md = _full_md()
        codes = parse_markdown_codebook(md)
        assert len(codes) == 4
        assert codes[0]["code_id"] == "IS1"
        assert codes[3]["code_id"] == "IS4"

    def test_all_10_fields_present(self):
        md = _full_md()
        codes = parse_markdown_codebook(md)
        for c in codes:
            assert len(c["definition"]) == 2
            assert len(c["inclusion_rules"]) == 2
            assert len(c["exclusion_rules"]) == 2
            assert len(c["typical_markers"]) == 2
            assert len(c["counter_markers"]) == 2
            assert len(c["positive_examples"]) == 2
            assert len(c["negative_examples"]) == 2
            assert len(c["boundary_cases"]) == 2
            assert len(c["low_information_rules"]) == 2
            assert len(c["notes"]) == 2

    def test_arrow_preserved(self):
        """Arrow → IS2 should survive parsing."""
        md = _full_md()
        # Inject arrow into IS1 definition first item
        md = md.replace("IS1 定义 item 1.", "Test rule → IS2 should be preserved.")
        codes = parse_markdown_codebook(md)
        assert "→ IS2" in codes[0]["definition"][0]

    def test_continuation_lines_merged(self):
        md = _full_md()
        # Inject a continuated item
        md = md.replace("IS1 定义 item 1.\n- IS1 定义 item 2.",
                        "IS1 first line\n  continued here.\n- IS1 定义 item 2.")
        codes = parse_markdown_codebook(md)
        assert "continued here" in codes[0]["definition"][0]

    def test_appendix_not_in_labels(self):
        md = _full_md()
        codes = parse_markdown_codebook(md)
        for c in codes:
            for items in c.values():
                for item in items:
                    assert "Rule content" not in item

    def test_standardize_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.md"
            src.write_text(_full_md(), encoding="utf-8")
            out = Path(d) / "out"
            r = standardize(src, out)
            assert r["code_count"] == 4
            assert Path(r["yaml_path"]).exists()


class TestParseErrors:
    def test_missing_label_raises(self):
        md = """## IS1 消极

**定义**:
- Test.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.
"""
        with pytest.raises(ParseError, match="Expected 4"):
            parse_markdown_codebook(md)

    def test_wrong_order_raises(self):
        md = """## IS2 中立

**定义**:
- Test.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.
"""
        with pytest.raises(ParseError, match="Expected label IS1"):
            parse_markdown_codebook(md)

    def test_missing_field_raises(self):
        md = """## IS1 消极

**定义**:
- Test.

**包含标准**:
- Rule 1.
"""
        with pytest.raises(ParseError):
            parse_markdown_codebook(md)

    def test_forbidden_field_raises(self):
        md = """## IS1 消极

**定义**:
- Test.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.
"""
        # Insert a forbidden field
        lines = md.split("\n")
        lines.insert(5, "**一级维度**: Test.")
        new_md = "\n".join(lines)
        with pytest.raises(ParseError):
            parse_markdown_codebook(new_md)

    def test_no_list_items_raises(self):
        md = _full_md()
        # Make IS1 包含标准 have zero items
        md = md.replace("- IS1 包含标准 item 1.\n- IS1 包含标准 item 2.", "")
        with pytest.raises(ParseError, match="Empty field"):
            parse_markdown_codebook(md)

    def test_chinese_colon_raises(self):
        md = """## IS1 Test

**定义**：
- Test.
"""
        # Chinese colon should fail field header match
        with pytest.raises(ParseError):
            parse_markdown_codebook(md)

    def test_no_bold_field_raises(self):
        md = """## IS1 Test

定义:
- Test.
"""
        with pytest.raises(ParseError):
            parse_markdown_codebook(md)

    def test_orphan_text_raises(self):
        md = """## IS1 Test

**定义**:
- Test.

This is orphan text.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.
"""
        with pytest.raises(ParseError, match="Unexpected content"):
            parse_markdown_codebook(md)

    def test_parse_fail_does_not_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            src = Path(d) / "in.md"
            out = Path(d) / "out"
            # First write a valid file
            src.write_text(_full_md(), encoding="utf-8")
            standardize(src, out)
            yaml_path = out / "codebook_v0.1.yaml"
            mtime_before = yaml_path.stat().st_mtime

            # Now write a bad file and try to standardize
            src.write_text("garbage", encoding="utf-8")
            with pytest.raises(ParseError):
                standardize(src, out)
            # File should not be overwritten
            assert yaml_path.stat().st_mtime == mtime_before

    def test_appendix_is_label_rejected(self):
        md = """## IS1 Test

**定义**:
- Test.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.

---

# 附录

## IS2 中立
"""
        with pytest.raises(ParseError, match="IS label found in appendix"):
            parse_markdown_codebook(md)

    def test_duplicate_label_raises(self):
        md = """## IS1 Test

**定义**:
- Test.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.

## IS1 Test2
"""
        with pytest.raises(ParseError):
            parse_markdown_codebook(md)

    def test_repeated_field_raises(self):
        md = """## IS1 Test

**定义**:
- Test.

**定义**:
- Test again.

**包含标准**:
- Rule 1.

**排除标准**:
- Rule 1.

**典型标记词**:
- Rule 1.

**反例标记词**:
- Rule 1.

**正例**:
- Rule 1.

**反例**:
- Rule 1.

**与其他标签的边界**:
- Rule 1.

**低信息文本处理**:
- Rule 1.

**备注**:
- Rule 1.
"""
        with pytest.raises(ParseError):
            parse_markdown_codebook(md)
