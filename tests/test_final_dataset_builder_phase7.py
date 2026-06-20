import csv, json, tempfile
from pathlib import Path
from auto_coding.final_dataset_builder import build

class TestFinalDataset:
    def test_builds(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); (b / "00_inputs").mkdir(parents=True)
            out = b / "07_final"; out.mkdir(parents=True)
            with open(b / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["unit_id","turn_id","group_id","speaker_id","session_id","timestamp","unit_text"])
                w.writeheader(); w.writerow({"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1","session_id":"","timestamp":"","unit_text":"test"})
            with open(out / "final_consensus_labels.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","final_primary_code":"IS2"})+"\n")
            with open(out / "final_adjudication_results.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","decision_id":"FD0001"})+"\n")
            r = build(str(b))
            assert r["total"] == 1

    def test_one_row_per_unit(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); (b / "00_inputs").mkdir(parents=True)
            out = b / "07_final"; out.mkdir(parents=True)
            with open(b / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["unit_id","turn_id","group_id","speaker_id","session_id","timestamp","unit_text"])
                w.writeheader()
                w.writerow({"unit_id":"u1","turn_id":"t1","group_id":"g1","speaker_id":"s1","session_id":"","timestamp":"","unit_text":"a"})
                w.writerow({"unit_id":"u2","turn_id":"t2","group_id":"g1","speaker_id":"s2","session_id":"","timestamp":"","unit_text":"b"})
            with open(out / "final_consensus_labels.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","final_primary_code":"IS2"})+"\n")
                f.write(json.dumps({"unit_id":"u2","final_primary_code":"IS3"})+"\n")
            (out / "final_adjudication_results.jsonl").write_text("")
            r = build(str(b))
            assert r["total"] == 2
