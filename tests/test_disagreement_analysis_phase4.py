"""Phase 4 tests for DisagreementAnalysisAgent."""
import csv, json, tempfile
from pathlib import Path
from auto_coding.disagreement_analysis import analyze


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestAnalyze:
    def _setup(self, d, a_items, b_items, pilot_rows=None):
        rd = d / "04_pilot" / "round_01"; rd.mkdir(parents=True)
        (d / "00_inputs").mkdir(parents=True)
        _jl(rd / "coder_A_results.jsonl", a_items)
        _jl(rd / "coder_B_results.jsonl", b_items)
        (d / "04_pilot").mkdir(parents=True, exist_ok=True)
        if pilot_rows:
            with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
                w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","context_before","context_after","group_id","speaker_id"])
                w.writeheader(); w.writerows(pilot_rows)

    def test_label_disagreement(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                        [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["review_candidate_count"] == 1

    def test_uncertain_detected(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":True,"needs_discussion":False,"confidence":0.5,"reason":"r"}],
                        [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["review_candidate_count"] >= 1

    def test_needs_discussion_detected(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":True,"confidence":0.7,"reason":"r"}],
                        [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["review_candidate_count"] >= 1

    def test_parse_error_detected(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":False,"uncertain":True,"reason":"err"}],
                        [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["review_candidate_count"] >= 1

    def test_missing_pair_detected(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                        [])
            r = analyze(str(b))
            assert r["review_candidate_count"] >= 1

    def test_outputs_generated(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                        [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            analyze(str(b))
            rd = b / "04_pilot" / "round_01"
            assert (rd / "disagreement_table.csv").exists()
            assert (rd / "disagreement_analysis.json").exists()
            assert (rd / "disagreement_summary.md").exists()
