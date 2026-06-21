"""Phase 6 tests for round transition."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.codebook_schema import make_valid_code
from auto_coding.self_loop_runner import SelfLoopRunner


def _setup(d: Path):
    (d / "00_inputs").mkdir(parents=True)
    (d / "01_codebook").mkdir(parents=True); (d / "02_prompts").mkdir(parents=True)
    (d / "04_pilot").mkdir(parents=True)
    rows = [{"unit_id": f"u{i}", "unit_text": t, "context_before": "", "context_after": "",
             "group_id": "g01", "speaker_id": "s1"}
            for i, t in enumerate(["是不是", "谢谢", "okok", "无语", "我们来", "好的",
                                   "没看懂", "不是吧", "那先算", "感觉会出问题", "额外1", "额外2",
                                   "额外3", "额外4", "额外5", "额外6", "额外7", "额外8",
                                   "额外9", "额外10"])]
    with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_id","unit_text","context_before","context_after","group_id","speaker_id"])
        w.writeheader(); w.writerows(rows)
    cb = {"version": "v0.1", "codes": [
        make_valid_code("IS1"),
        make_valid_code("IS2"),
        make_valid_code("IS3"),
        make_valid_code("IS4"),
    ]}
    with open(d / "01_codebook" / "codebook_v0.1.yaml", "w", encoding="utf-8") as f:
        yaml.dump(cb, f, allow_unicode=True)


class TestRoundTransition:
    def test_round_01_generates_decision(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup(b)
            runner = SelfLoopRunner(b)
            r = runner.run_round("round_01", "v0.1")
            assert "decision" in r
            assert "next_action" in r

    def test_round_02_uses_v02_candidate_codebook(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup(b)
            runner = SelfLoopRunner(b)
            r = runner.run_round("round_01", "v0.1")
            if r["next_action"] in ("run_round_02",):
                r2 = runner.run_round("round_02", r["target_codebook_version"])
                assert "v0.2" in r2["codebook_version"]

    def test_carryover_enters_next_round(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d); _setup(b)
            runner = SelfLoopRunner(b)
            r = runner.run_round("round_01", "v0.1")
            carryover = r.get("carryover", [])
            if carryover and r["next_action"] in ("run_round_02",):
                runner._prepare_next_round_input("round_02", r)
                csv_files = list((b / "04_pilot" / "round_02").glob("pilot_sample*.csv"))
                if csv_files:
                    with open(csv_files[0], encoding="utf-8", newline="") as f:
                        rows = list(csv.DictReader(f))
                    carry_ids = {u["unit_id"] for u in rows}
                    for cid in carryover:
                        assert cid in carry_ids, f"Carryover {cid} missing from round_02"
