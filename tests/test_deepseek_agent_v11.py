"""v1.1 tests for DeepSeekClient and agents."""
import os, tempfile, json, yaml, csv
from pathlib import Path
import pytest
from auto_coding.deepseek_client import DeepSeekClient, RealDeepSeekDisabledError
from auto_coding.deepseek_adjudicator import run_deepseek_adjudication
from auto_coding.deepseek_codebook_refiner import run_deepseek_refine


class TestDeepSeekClient:
    def test_blocks_without_env(self):
        c = DeepSeekClient()
        with pytest.raises(RealDeepSeekDisabledError):
            c.chat_json("sys", "user")

    def test_cache_works(self):
        with tempfile.TemporaryDirectory() as d:
            cache = Path(d) / "cache"
            c = DeepSeekClient(cache_dir=cache)
            # Cache write/read without real call
            key = c._cache_key("s", "u", 100)
            c._cache_set(key, {"test": "ok"})
            result = c._cache_get(key)
            assert result == {"test": "ok"}

    def test_call_log_empty_initially(self):
        c = DeepSeekClient()
        assert len(c.call_log) == 0
        assert c.total_tokens == 0

    def test_api_key_check(self):
        c = DeepSeekClient()
        # API key may or may not be set — only check that the attribute exists
        assert hasattr(c, "api_key")


class TestDeepSeekAdjudicator:
    def _setup(self, d: Path):
        rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        cb = {"version":"v1.0","codes":[{"label":"IS1"},{"label":"IS2"},{"label":"IS3"},{"label":"IS4"}]}
        with open(d / "01_codebook" / "codebook_v1.0.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)
        # Write coder results with disagreement
        with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id":"u1","primary_code":"IS2","parse_ok":True,"confidence":0.8,"reason":"A"})+"\n")
        with open(rd / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id":"u1","primary_code":"IS3","parse_ok":True,"confidence":0.8,"reason":"B"})+"\n")

    def test_mock_adjudicates(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            r = run_deepseek_adjudication(str(d), mode="mock")
            assert r["total"] >= 1


class TestDeepSeekRefiner:
    def test_mock_refine(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            rd = b / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
            with open(rd / "adjudication_results.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unresolved":True,"coder_A_label":"IS2","coder_B_label":"IS3","decision_id":"D0001"})+"\n")
            r = run_deepseek_refine(str(b), mode="mock", exclude_unresolved=False)
            assert r["changes_count"] >= 1
