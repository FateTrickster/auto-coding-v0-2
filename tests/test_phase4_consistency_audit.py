"""Phase 4 consistency audit — verifies all cross-file invariants."""
import csv, json, tempfile
from pathlib import Path
from auto_coding.disagreement_analysis import analyze
from auto_coding.adjudicator import adjudicate
from auto_coding.consensus_builder import build
from auto_coding.decision_log import generate


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


def _setup(d, a_items, b_items, rel_metrics=None):
    rd = d / "04_pilot" / "round_01"; rd.mkdir(parents=True)
    (d / "00_inputs").mkdir(parents=True)
    (d / "01_codebook").mkdir(parents=True)
    _jl(rd / "coder_A_results.jsonl", a_items)
    _jl(rd / "coder_B_results.jsonl", b_items)
    # Write reliability metrics
    with open(rd / "agreement_metrics.json", "w", encoding="utf-8") as f:
        m = rel_metrics or {"n_valid_pairs": len(a_items), "percent_agreement": 1.0}
        json.dump(m, f)
    # Write minimal codebook for adjudicator
    import yaml
    with open(d / "01_codebook" / "codebook_v0.2_candidate.yaml", "w", encoding="utf-8") as f:
        yaml.dump({"codes": [{"label":"IS1","code_id":"IS1"},{"label":"IS2","code_id":"IS2"},
                             {"label":"IS3","code_id":"IS3"},{"label":"IS4","code_id":"IS4"}]}, f, allow_unicode=True)
    (d / "04_pilot").mkdir(parents=True, exist_ok=True)
    # Write empty pilot csv
    with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(["unit_id","unit_text"])


class TestInvariants:
    def test_agreement_plus_disagreement_equals_valid(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS4","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["agreement_count"] + r["label_disagreement_count"] == r["valid_pairs"]

    def test_computed_pct_matches(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            expected = r["agreement_count"] / max(r["valid_pairs"], 1)
            assert abs(r["computed_percent_agreement"] - expected) < 0.001

    def test_label_disagreement_not_exceed_valid(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["label_disagreement_count"] <= r["valid_pairs"]

    def test_review_not_less_than_label_dis(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":True,"needs_discussion":False,"confidence":0.5,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            r = analyze(str(b))
            assert r["review_candidate_count"] >= r["label_disagreement_count"]

    def test_consensus_agreement_equals_agreement_count(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            analyze(str(b))
            adjudicate(str(b))
            r = build(str(b))
            assert r["agreement"] == 1

    def test_adjudication_results_equals_adjudication_count(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            analysis = analyze(str(b))
            adj = adjudicate(str(b))
            assert adj["total"] == analysis["adjudication_count"]

    def test_decision_log_entries_equal_adjudication(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            analyze(str(b))
            adj = adjudicate(str(b))
            dlog = generate(str(b))
            assert dlog["decisions"] == adj["total"]

    def test_consensus_total_equals_valid_pairs(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS3","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"},
                    {"unit_id":"u2","primary_code":"IS4","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}])
            analyze(str(b))
            adjudicate(str(b))
            r = build(str(b))
            assert r["agreement"] + r["adjudication"] + r["unresolved"] == 2

    def test_consistency_check_passed_when_matches(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            _setup(b,
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   [{"unit_id":"u1","primary_code":"IS2","parse_ok":True,"uncertain":False,"needs_discussion":False,"confidence":0.8,"reason":"r"}],
                   {"n_valid_pairs": 1, "percent_agreement": 1.0})
            r = analyze(str(b))
            assert r["consistency_check_passed"] is True
