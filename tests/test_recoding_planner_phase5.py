"""Phase 5 tests for RecodingPlanner."""
import json, tempfile
from pathlib import Path
from auto_coding.recoding_planner import plan


def _jl(p, items):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestPlan:
    def _setup(self, d, changes=None, adj=None):
        rd = d / "04_pilot" / "round_01"; rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        (d / "01_codebook" / "codebook_revision_proposal_round_01.json").write_text(json.dumps({
            "round_id":"round_01","source_codebook_version":"v0.2","target_codebook_version":"v0.3",
            "changes": changes or []}))
        _jl(rd / "adjudication_results.jsonl", adj or [])

    def test_no_changes_no_recoding(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d))
            r = plan(str(d))
            assert r["requires_recoding"] is False

    def test_requires_recoding_when_change(self):
        with tempfile.TemporaryDirectory() as d:
            self._setup(Path(d), changes=[{"change_id":"C0001","requires_recoding":True,
                         "evidence_decisions":["D0001"],"affected_patterns":["IS2-IS3"]}],
                        adj=[{"decision_id":"D0001","unit_id":"u1","unresolved":True}])
            r = plan(str(d))
            assert r["requires_recoding"] is True
            assert "u1" in r["carryover_disagreement_unit_ids"]
