"""Phase 5 tests for CodebookRefiner."""
import json, tempfile, yaml
from pathlib import Path
from auto_coding.codebook_schema import make_valid_code
from auto_coding.codebook_refiner import refine


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestRefine:
    def _setup(self, d, adj_items=None, cb_codes=None):
        rd = d / "04_pilot" / "round_01"; rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
        _jl(rd / "adjudication_results.jsonl", adj_items or [])
        (rd / "disagreement_analysis.json").write_text(json.dumps({"adjudication_count": len(adj_items or [])}))
        cb = {"version": "v0.2_candidate", "codes": cb_codes or [
            make_valid_code(c) for c in ["IS1","IS2","IS3","IS4"]]}
        with open(d / "01_codebook" / "codebook_v0.2_candidate.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)

    def test_generates_proposal(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"decision_id":"D0001","unresolved":True,"affected_pattern":"IS2-IS3",
                             "decision_reason":"both disagree","suggested_codebook_change":"review IS2-IS3",
                             "codebook_change_needed":True,"coder_A_label":"IS2","coder_B_label":"IS3"}])
            r = refine(str(b))
            assert r["changes_count"] >= 1
            prop = b / "01_codebook" / "codebook_revision_proposal_round_01.json"
            assert prop.exists()
            with open(prop) as f: data = json.load(f)
            assert len(data["changes"]) >= 1
            assert data["changes"][0]["evidence_decisions"] == ["D0001"]

    def test_does_not_overwrite_source(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"decision_id":"D0001","unresolved":True,"affected_pattern":"IS2-IS3",
                             "decision_reason":"x","suggested_codebook_change":"y",
                             "codebook_change_needed":True,"coder_A_label":"IS2","coder_B_label":"IS3"}])
            refine(str(b))
            src = b / "01_codebook" / "codebook_v0.2_candidate.yaml"
            assert src.exists()

    def test_no_unresolved_generates_empty_changes(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"decision_id":"D0001","unresolved":False,"affected_pattern":"",
                             "decision_reason":"ok","codebook_change_needed":False}])
            r = refine(str(b))
            assert r["changes_count"] == 0

    def test_v03_candidate_preserves_labels(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup(b, [{"decision_id":"D0001","unresolved":True,"affected_pattern":"IS2-IS3",
                             "decision_reason":"x","suggested_codebook_change":"y",
                             "codebook_change_needed":True,"coder_A_label":"IS2","coder_B_label":"IS3"}])
            refine(str(b))
            v3 = b / "01_codebook" / "codebook_v0.3_candidate.yaml"
            with open(v3, encoding="utf-8") as f:
                data = yaml.safe_load(f)
            assert len(data["codes"]) == 4
