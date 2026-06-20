"""Phase 4 tests for DecisionLogAgent."""
import json, tempfile
from pathlib import Path
from auto_coding.decision_log import generate


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestDecisionLog:
    def test_generates(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "adjudication_results.jsonl", [
                {"decision_id":"D0001","unit_id":"u1","unit_text":"test","coder_A_label":"IS2",
                 "coder_B_label":"IS3","final_primary_code":"IS2","decision_reason":"r",
                 "disagreement_type":"label_disagreement","codebook_change_needed":False,
                 "suggested_codebook_change":"","requires_recoding":False,"unresolved":False},
            ])
            r = generate(str(b))
            assert r["decisions"] == 1
            log = (rd / "decision_log.md").read_text(encoding="utf-8")
            assert "D0001" in log
            assert "test" in log

    def test_unresolved_included(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "adjudication_results.jsonl", [
                {"decision_id":"D0001","unit_id":"u1","unit_text":"unresolved case",
                 "coder_A_label":"IS2","coder_B_label":"IS3","final_primary_code":None,
                 "decision_reason":"Cannot decide","disagreement_type":"label_disagreement",
                 "codebook_change_needed":True,"suggested_codebook_change":"review",
                 "requires_recoding":False,"unresolved":True},
            ])
            generate(str(b))
            log = (rd / "decision_log.md").read_text(encoding="utf-8")
            assert "unresolved case" in log
            assert "是" in log  # unresolved=是
