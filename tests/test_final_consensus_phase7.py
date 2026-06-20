import json, tempfile
from pathlib import Path
from auto_coding.final_consensus import build_final_consensus

class TestFinalConsensus:
    def test_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); fd = b / "06_formal_coding"; fd.mkdir(parents=True)
            with open(fd / "coder_A_formal.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","primary_code":"IS2","parse_ok":True})+"\n")
            with open(fd / "coder_B_formal.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","primary_code":"IS2","parse_ok":True})+"\n")
            r = build_final_consensus(str(b))
            assert r["agreement"] == 1

    def test_adjudication(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); fd = b / "06_formal_coding"; fd.mkdir(parents=True)
            with open(fd / "coder_A_formal.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","primary_code":"IS2","parse_ok":True,"confidence":0.9})+"\n")
            with open(fd / "coder_B_formal.jsonl", "w", encoding="utf-8") as f:
                f.write(json.dumps({"unit_id":"u1","primary_code":"IS3","parse_ok":True,"confidence":0.7})+"\n")
            r = build_final_consensus(str(b))
            assert r["adjudication"] == 1
            assert (b / "07_final" / "final_decision_log.md").exists()
