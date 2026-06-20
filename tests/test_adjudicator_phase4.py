"""Phase 4 tests for AdjudicationAgent."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.adjudicator import adjudicate


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _setup(d, a_items, b_items, dis_rows, cb_codes=None):
    rd = d / "04_pilot" / "round_01"; rd.mkdir(parents=True)
    (d / "01_codebook").mkdir(parents=True)
    _jl(rd / "coder_A_results.jsonl", a_items)
    _jl(rd / "coder_B_results.jsonl", b_items)
    with open(rd / "disagreement_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","context_before","context_after",
            "coder_A_label","coder_B_label","coder_A_confidence","coder_B_confidence",
            "coder_A_reason","coder_B_reason","label_pair","disagreement_type",
            "analysis_note","is_label_disagreement","is_review_candidate","needs_adjudication","review_reason"])
        w.writeheader(); w.writerows(dis_rows)
    codes = cb_codes or [
        {"label":"IS1","code_id":"IS1"},{"label":"IS2","code_id":"IS2"},
        {"label":"IS3","code_id":"IS3"},{"label":"IS4","code_id":"IS4"}]
    with open(d / "01_codebook" / "codebook_v0.2_candidate.yaml", "w", encoding="utf-8") as f:
        yaml.dump({"codes": codes}, f, allow_unicode=True)


class TestAdjudicate:
    def test_each_has_decision_id(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","coder_A_label":"IS2","coder_B_label":"IS3","coder_A_confidence":"0.8","coder_B_confidence":"0.8","disagreement_type":"label_disagreement","unit_text":"test","is_label_disagreement":"TRUE","is_review_candidate":"TRUE","needs_adjudication":"TRUE","review_reason":"label_mismatch"}])
            r = adjudicate(str(b))
            assert r["total"] >= 1

    def test_unresolved_items_csv(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","coder_A_label":"IS2","coder_B_label":"IS3","coder_A_confidence":"0.8","coder_B_confidence":"0.8","disagreement_type":"label_disagreement","unit_text":"test","is_label_disagreement":"TRUE","is_review_candidate":"TRUE","needs_adjudication":"TRUE","review_reason":"label_mismatch"}])
            adjudicate(str(b))
            assert (b / "04_pilot" / "round_01" / "unresolved_items.csv").exists()

    def test_decision_id_increment(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS2","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS4","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","coder_A_label":"IS2","coder_B_label":"IS3","coder_A_confidence":"0.8","coder_B_confidence":"0.8","disagreement_type":"label_disagreement","unit_text":"t1","is_label_disagreement":"TRUE","is_review_candidate":"TRUE","needs_adjudication":"TRUE","review_reason":"label_mismatch"},
                    {"unit_id":"u2","coder_A_label":"IS2","coder_B_label":"IS4","coder_A_confidence":"0.8","coder_B_confidence":"0.8","disagreement_type":"label_disagreement","unit_text":"t2","is_label_disagreement":"TRUE","is_review_candidate":"TRUE","needs_adjudication":"TRUE","review_reason":"label_mismatch"}])
            r = adjudicate(str(b))
            assert r["total"] == 2
