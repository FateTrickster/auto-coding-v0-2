"""v1.0 acceptance auditor tests."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.acceptance_auditor import audit


class TestAudit:
    def _setup(self, d: Path):
        (d / "00_inputs").mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
        (d / "06_formal_coding").mkdir(parents=True)
        (d / "07_final").mkdir(parents=True); (d / "99_logs").mkdir(parents=True)

        # unit_table
        with open(d / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","turn_id","group_id","speaker_id","session_id","timestamp"])
            w.writeheader()
            for i in range(1, 6): w.writerow({"unit_id":f"u{i}","unit_text":f"t{i}","turn_id":f"t{i}","group_id":"g1","speaker_id":"s1","session_id":"","timestamp":""})

        # final_codebook
        cb = {"version":"v1.0","frozen":True,"source_candidate_version":"v0.3","freeze_round_id":"round_03","codes":[{"label":"IS1"},{"label":"IS2"},{"label":"IS3"},{"label":"IS4"}]}
        with open(d / "01_codebook" / "final_codebook_v1.0.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)
        (d / "01_codebook" / "codebook_freeze_report.md").write_text("forced freeze")
        (d / "02_prompts" / "coder_prompt_v1.0.md").write_text("# Prompt v1.0")

        # formal coding
        for agent in ["A","B"]:
            with open(d / "06_formal_coding" / f"coder_{agent}_formal.jsonl", "w", encoding="utf-8") as f:
                for i in range(1, 6): f.write(json.dumps({"unit_id":f"u{i}","primary_code":"IS2","parse_ok":True})+"\n")
        (d / "06_formal_coding" / "formal_agreement_metrics.json").write_text(json.dumps({"cohen_kappa":0.92,"percent_agreement":0.99}))
        (d / "06_formal_coding" / "formal_reliability_report.md").write_text("# Report")

        # final
        with open(d / "07_final" / "final_consensus_labels.jsonl", "w", encoding="utf-8") as f:
            for i in range(1,6): f.write(json.dumps({"unit_id":f"u{i}","final_primary_code":"IS2","consensus_source":"agreement","unresolved":False})+"\n")
        with open(d / "07_final" / "final_coding_table.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["unit_id","turn_id","group_id","speaker_id","session_id","timestamp","unit_text","final_primary_code","codebook_version","decision_id","final_note"])
            w.writeheader()
            for i in range(1,6): w.writerow({"unit_id":f"u{i}","final_primary_code":"IS2","codebook_version":"v1.0","decision_id":"","final_note":""})
        (d / "07_final" / "final_decision_log.md").write_text("# Decision Log")
        (d / "07_final" / "final_dataset_report.md").write_text("# Dataset Report")

        # state
        (d / "99_logs" / "self_loop_state.json").write_text(json.dumps({"freeze_allowed":False,"last_decision":"stop_max_rounds"}))
        (d / "99_logs" / "archive_manifest.json").write_text(json.dumps({"files":[{"path":"x","size":1,"mtime":1,"sha256_short":"abc"}]}))

    def test_passes_with_complete_data(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); self._setup(b)
            r = audit(str(b))
            assert r["status"] == "PASS", f"Expected PASS, got FAIL: {r['checks']}"

    def test_fails_with_missing_files(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            (b / "00_inputs").mkdir(parents=True)
            r = audit(str(b))
            assert r["status"] == "FAIL"

    def test_deepseek_calls_detected(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); self._setup(b)
            r = audit(str(b))
            assert "real_api_calls" in r["deepseek"]
            assert r["deepseek"]["real_api_calls"] == 0

    def test_row_consistency(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); self._setup(b)
            r = audit(str(b))
            assert r["formal_coding"]["coder_A_rows"] == 5
