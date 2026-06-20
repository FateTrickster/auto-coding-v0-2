import json, tempfile, yaml, csv
from pathlib import Path
import pytest
from auto_coding.formal_coding_manager import run_formal

class TestFormalCoding:
    def _setup(self, d, has_final_codebook=True):
        (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
        (d / "00_inputs").mkdir(parents=True)
        if has_final_codebook:
            cb = {"version":"v1.0","codes":[{"label":"IS1"},{"label":"IS2"},{"label":"IS3"},{"label":"IS4"}]}
            with open(d / "01_codebook" / "final_codebook_v1.0.yaml", "w", encoding="utf-8") as f:
                yaml.dump(cb, f, allow_unicode=True)
        rows = [{"unit_id":"u1","unit_text":"test","turn_id":"t1","group_id":"g1","speaker_id":"s1",
                 "session_id":"","timestamp":""}]
        with open(d / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","turn_id","group_id","speaker_id","session_id","timestamp"])
            w.writeheader(); w.writerows(rows)

    def test_fails_without_final_codebook(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), has_final_codebook=False)
            with pytest.raises(FileNotFoundError):
                run_formal(str(d))

    def test_runs_with_final_codebook(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            r = run_formal(str(d))
            assert r["coder_a_ok"] >= 1
            assert (Path(d) / "06_formal_coding" / "coder_A_formal.jsonl").exists()
