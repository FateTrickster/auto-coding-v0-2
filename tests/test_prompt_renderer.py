"""Tests for prompt_renderer.py — strict validation, atomic write, 10-field rendering."""
import tempfile, yaml, pytest
from pathlib import Path
from auto_coding.prompt_renderer import render, RenderError
from auto_coding.codebook_schema import EXPECTED_CODE_IDS, PROMPT_FIELDS


def _vc(cid="IS1"):
    return {"code_id": cid, "code_name": "N", "definition": ["d"], "inclusion_rules": ["i"],
            "exclusion_rules": ["e"], "typical_markers": ["t"], "counter_markers": ["c"],
            "positive_examples": ["p"], "negative_examples": ["n"], "boundary_cases": ["b"],
            "low_information_rules": ["l"], "notes": ["o"]}


def _write_cb(path, codes, version="v0.1"):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump({"version": version, "codes": codes}, f, allow_unicode=True)


REAL_YAML = "outputs/agentic_coding_project/01_codebook/codebook_v0.1.yaml"


class TestValidRender:
    def test_real_yaml_renders(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        assert r["code_count"] == 4
        assert Path(r["prompt_path"]).exists()

    def test_all_4_labels(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        p = Path(r["prompt_path"]).read_text(encoding="utf-8")
        for c in EXPECTED_CODE_IDS: assert f"## {c} " in p

    def test_all_10_fields(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        p = Path(r["prompt_path"]).read_text(encoding="utf-8")
        for _, zh in PROMPT_FIELDS: assert f"**{zh}**:" in p

    def test_no_priority_rules(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        assert "优先规则" not in Path(r["prompt_path"]).read_text(encoding="utf-8")

    def test_no_placeholders(self):
        p = Path(render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")["prompt_path"]).read_text(encoding="utf-8")
        assert "缺失" not in p and "未提供" not in p

    def test_arrows_preserved(self):
        p = Path(render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")["prompt_path"]).read_text(encoding="utf-8")
        assert "→" in p

    def test_version_consistent(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        p = Path(r["prompt_path"]).read_text(encoding="utf-8")
        assert "v0.1" in p and "coder_prompt_v0.1.md" in str(r["prompt_path"])

    def test_json_contract(self):
        p = Path(render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")["prompt_path"]).read_text(encoding="utf-8")
        for f in ["primary_code", "secondary_code", "evidence_span", "needs_discussion"]:
            assert f in p

    def test_notes_rendered(self):
        p = Path(render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")["prompt_path"]).read_text(encoding="utf-8")
        assert "备注" in p

    def test_no_tmp_leftover(self):
        r = render(REAL_YAML, Path(tempfile.mkdtemp()) / "out")
        assert len(list(Path(r["prompt_path"]).parent.glob("*.tmp"))) == 0


class TestFieldErrors:
    def test_def_empty(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["definition"] = []
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_def_blank(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["definition"] = [""]
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_def_str_fails(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["definition"] = "abc"
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_incl_str_fails_no_char_render(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["inclusion_rules"] = "AB"
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_non_string_item(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["inclusion_rules"] = ["ok", 123]
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_code_name_empty(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["code_name"] = ""
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_missing_notes(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; del cs[0]["notes"]
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_unknown_field(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs[0]["priority_rules"] = ["x"]
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")


class TestStructureErrors:
    def test_empty_yaml(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_root_list(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("- x")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_no_version(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("codes: []")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_version_int(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS], version=123)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_no_codes(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("version: v0.1")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_codes_not_list(self):
        with tempfile.TemporaryDirectory() as d:
            with open(Path(d) / "cb.yaml", "w") as f: yaml.dump({"version": "v0.1", "codes": "x"}, f)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_empty_codes(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [])
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_missing_is4(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc(c) for c in ["IS1","IS2","IS3"]])
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_duplicate_is1(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc("IS1"), _vc("IS1"), _vc("IS2"), _vc("IS3")])
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_unknown_is5(self):
        with tempfile.TemporaryDirectory() as d:
            cs = [_vc(c) for c in EXPECTED_CODE_IDS]; cs.append(_vc("IS5"))
            _write_cb(Path(d) / "cb.yaml", cs)
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_wrong_order(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc(c) for c in ["IS2","IS1","IS3","IS4"]])
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")

    def test_code_not_dict(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "cb.yaml").write_text("version: v0.1\ncodes: [1, 2, 3, 4]")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", Path(d) / "out")


class TestVersionAndOverwrite:
    def test_version_mismatch(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            with pytest.raises(RenderError, match="Expected version"):
                render(Path(d) / "cb.yaml", Path(d) / "out", expected_version="v9.9")

    def test_fail_no_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "out"; out.mkdir()
            existing = out / "coder_prompt_v0.1.md"
            existing.write_text("original", encoding="utf-8")
            (Path(d) / "cb.yaml").write_text("garbage")
            with pytest.raises(RenderError): render(Path(d) / "cb.yaml", out)
            assert existing.read_text(encoding="utf-8") == "original"

    def test_atomic_no_tmp_left(self):
        with tempfile.TemporaryDirectory() as d:
            _write_cb(Path(d) / "cb.yaml", [_vc(c) for c in EXPECTED_CODE_IDS])
            r = render(Path(d) / "cb.yaml", Path(d) / "out")
            assert len(list(Path(r["prompt_path"]).parent.glob("*.tmp"))) == 0
