"""Phase 4 tests for ConsensusBuilderAgent."""
import json, tempfile
from pathlib import Path
from auto_coding.consensus_builder import build


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestBuild:
    def test_agreement_direct(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "coder_A_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "coder_B_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "adjudication_results.jsonl", [])
            r = build(str(b))
            assert r["agreement"] == 1
            assert r["adjudication"] == 0

    def test_adjudication_used(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "coder_A_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "coder_B_results.jsonl", [{"unit_id":"u1","primary_code":"IS3","parse_ok":True}])
            _jl(rd / "adjudication_results.jsonl", [{"unit_id":"u1","final_primary_code":"IS2","unresolved":False,"decision_id":"D0001"}])
            r = build(str(b))
            assert r["adjudication"] == 1

    def test_unresolved(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "coder_A_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "coder_B_results.jsonl", [{"unit_id":"u1","primary_code":"IS3","parse_ok":True}])
            _jl(rd / "adjudication_results.jsonl", [{"unit_id":"u1","final_primary_code":None,"unresolved":True,"decision_id":"D0001"}])
            r = build(str(b))
            assert r["unresolved"] == 1

    def test_one_per_unit(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); rd = b / "04_pilot" / "round_01"; rd.mkdir(parents=True)
            _jl(rd / "coder_A_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True},{"unit_id":"u2","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "coder_B_results.jsonl", [{"unit_id":"u1","primary_code":"IS2","parse_ok":True},{"unit_id":"u2","primary_code":"IS2","parse_ok":True}])
            _jl(rd / "adjudication_results.jsonl", [])
            r = build(str(b))
            assert r["total"] == 2
