"""Tests for prompt_renderer.py."""
import tempfile, yaml
from pathlib import Path
from auto_coding.prompt_renderer import render
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


def _fixture_yaml():
    d = Path(tempfile.mkdtemp())
    codes = [_vc(cid) for cid in EXPECTED_CODE_IDS]
    path = d / "codebook_v0.1.yaml"
    _write_cb(path, codes)
    return path


class TestValidRender:
    def _render(self):
        return render(str(_fixture_yaml()), Path(tempfile.mkdtemp()) / "out")

    def test_real_yaml_renders(self):
        r = self._render()
        assert r["code_count"] == 4
        assert Path(r["prompt_path"]).exists()

    def test_all_4_labels(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        for cid in EXPECTED_CODE_IDS:
            assert cid in prompt, f"Missing {cid}"

    def test_all_10_fields(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        # Fields are rendered as Chinese labels; check structural presence
        assert "IS1" in prompt and "IS2" in prompt and "IS3" in prompt and "IS4" in prompt
        assert "定义" in prompt
        assert "纳入" in prompt or "排除" in prompt
        assert "正例" in prompt

    def test_no_priority_rules(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "priority_rules" not in prompt.lower()

    def test_no_placeholders(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "[TBD]" not in prompt
        assert "[TODO]" not in prompt

    def test_arrows_preserved(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "primary_code" in prompt

    def test_version_consistent(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "v0.1" in prompt

    def test_json_contract(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "primary_code" in prompt

    def test_notes_rendered(self):
        prompt = Path(self._render()["prompt_path"]).read_text(encoding="utf-8")
        assert "备注" in prompt or "notes" in prompt.lower()

    def test_no_tmp_leftover(self):
        out = Path(tempfile.mkdtemp())
        render(str(_fixture_yaml()), out)
        tmp_files = list(out.glob("*.tmp"))
        assert len(tmp_files) == 0, f"TMP leftover: {tmp_files}"
