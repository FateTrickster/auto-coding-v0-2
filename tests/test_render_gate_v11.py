"""v1.1 test for render-prompt review gate."""
import json, tempfile, yaml
from pathlib import Path
from typer.testing import CliRunner
from auto_coding.cli import app


runner = CliRunner()


def _setup_project(d, can_proceed=True):
    d = Path(d)
    (d / "01_codebook").mkdir(parents=True)
    (d / "02_prompts").mkdir(parents=True)
    # Write a valid codebook YAML
    cb = {"version": "v0.1", "codes": [
        {"code_id": c, "code_name": c, "definition": ["d"], "inclusion_rules": ["i"],
         "exclusion_rules": ["e"], "typical_markers": ["t"], "counter_markers": ["c"],
         "positive_examples": ["p"], "negative_examples": ["n"], "boundary_cases": ["b"],
         "low_information_rules": ["l"], "notes": ["o"]}
        for c in ["IS1", "IS2", "IS3", "IS4"]
    ]}
    with open(d / "01_codebook" / "codebook_v0.1.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cb, f, allow_unicode=True)
    # Write review result
    with open(d / "01_codebook" / "codebook_missing_fields.json", "w", encoding="utf-8") as f:
        json.dump({"can_proceed_to_training": can_proceed}, f)


class TestRenderGate:
    def test_passes_when_review_ok(self):
        with tempfile.TemporaryDirectory() as d:
            _setup_project(d, can_proceed=True)
            result = runner.invoke(app, ["render-prompt", "--project-dir", d])
            assert result.exit_code == 0
            assert "Rendered prompt" in result.stdout

    def test_blocks_when_review_failed(self):
        with tempfile.TemporaryDirectory() as d:
            _setup_project(d, can_proceed=False)
            result = runner.invoke(app, ["render-prompt", "--project-dir", d])
            assert result.exit_code == 1
            assert "BLOCKED" in result.stdout

    def test_force_overrides_block(self):
        with tempfile.TemporaryDirectory() as d:
            _setup_project(d, can_proceed=False)
            result = runner.invoke(app, ["render-prompt", "--project-dir", d, "--force"])
            assert result.exit_code == 0
            assert "Rendered prompt" in result.stdout

    def test_no_review_file_passes(self):
        with tempfile.TemporaryDirectory() as d:
            _setup_project(d, can_proceed=True)
            (Path(d) / "01_codebook" / "codebook_missing_fields.json").unlink()
            result = runner.invoke(app, ["render-prompt", "--project-dir", d])
            assert result.exit_code == 0
