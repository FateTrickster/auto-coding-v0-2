"""Tests for CoderTrainingAgent."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.codebook_schema import make_valid_code
from auto_coding.coder_training import CoderTrainingAgent


def _write_csv(path: Path, rows: list[dict]) -> None:
    fields = ["unit_id", "unit_text", "context_before", "context_after",
              "group_id", "speaker_id", "sample_reason", "risk_flags"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def _write_codebook(path: Path) -> None:
    data = {"version": "v0.1", "codes": [make_valid_code(c) for c in ["IS1","IS2","IS3","IS4"]]}
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


class TestSelectTrainingSamples:
    def test_selects_up_to_max(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rows = [{"unit_id": f"u{i}", "unit_text": f"t{i}", "risk_flags": "",
                     "sample_reason": "", "group_id": "g01", "speaker_id": "s1",
                     "context_before": "", "context_after": ""} for i in range(50)]
            _write_csv(base / "pilot.csv", rows)
            agent = CoderTrainingAgent(max_items=30)
            samples = agent.select_training_samples(base / "pilot.csv")
            assert len(samples) == 30

    def test_prioritizes_risk_flags(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rows = []
            for i in range(5):
                rows.append({"unit_id": f"hr{i}", "unit_text": f"risk{i}",
                             "risk_flags": "high_risk_boundary", "sample_reason": "",
                             "group_id": "g01", "speaker_id": "s1",
                             "context_before": "", "context_after": ""})
            for i in range(45):
                rows.append({"unit_id": f"n{i}", "unit_text": f"normal{i}",
                             "risk_flags": "", "sample_reason": "",
                             "group_id": "g01", "speaker_id": "s1",
                             "context_before": "", "context_after": ""})
            _write_csv(base / "pilot.csv", rows)
            agent = CoderTrainingAgent(max_items=30)
            samples = agent.select_training_samples(base / "pilot.csv")
            hr_count = sum(1 for s in samples if s["unit_id"].startswith("hr"))
            assert hr_count >= 3  # most of the 20 HR slots


class TestGenerateSharedExamples:
    def test_mock_mode_generates(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _write_codebook(base / "cb.yaml")
            with open(base / "cb.yaml", encoding="utf-8") as f:
                cb = yaml.safe_load(f)
            samples = [{"unit_id": "u1", "unit_text": "是不是数据反了", "risk_flags": "",
                        "sample_reason": "", "group_id": "g01", "speaker_id": "s1",
                        "context_before": "", "context_after": ""}]
            agent = CoderTrainingAgent()
            ex = agent.generate_shared_coding_examples(samples, cb)
            assert len(ex) == 1
            assert ex[0]["candidate_primary_code"] == "IS3"
            assert "IS2" in ex[0]["possible_alternative_codes"]


class TestGenerateIssues:
    def test_aggregates_issues(self):
        agent = CoderTrainingAgent()
        ex = [
            {"unit_id": "u1", "candidate_primary_code": "IS3",
             "possible_alternative_codes": ["IS2"],
             "issue_types": ["missing_boundary_case"]},
            {"unit_id": "u2", "candidate_primary_code": "IS3",
             "possible_alternative_codes": ["IS2"],
             "issue_types": ["missing_boundary_case"]},
            {"unit_id": "u3", "candidate_primary_code": "IS4",
             "possible_alternative_codes": ["IS2"],
             "issue_types": ["missing_boundary_case"]},
        ]
        issues = agent.generate_training_issues(ex, {})
        assert len(issues["issues"]) >= 1


class TestRevisionSuggestions:
    def test_generates_for_medium_plus(self):
        agent = CoderTrainingAgent()
        issues = {"round_id": "r1", "total_training_items": 10, "issues": [
            {"issue_id": "TI001", "issue_type": "missing_boundary_case",
             "target_codes": ["IS2", "IS3"], "evidence_units": ["u1","u2","u3"],
             "description": "边界缺失", "suggested_fix": "补充边界", "severity": "medium"},
            {"issue_id": "TI002", "issue_type": "missing_boundary_case",
             "target_codes": ["IS1"], "evidence_units": ["u4"],
             "description": "单标签问题", "suggested_fix": "x", "severity": "low"},
        ]}
        sug = agent.generate_revision_suggestions(issues, {})
        assert len(sug["suggestions"]) == 1


class TestBuildCandidate:
    def test_generates_candidate(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            _write_codebook(base / "cb.yaml")
            with open(base / "cb.yaml", encoding="utf-8") as f:
                cb = yaml.safe_load(f)
            agent = CoderTrainingAgent()
            sug = {"suggestions": [{
                "suggestion_id": "TS001", "change_type": "add_boundary_case",
                "target_codes": ["IS2", "IS3"], "proposed_text": "新增边界规则",
                "reason": "test", "evidence_training_items": ["u1"], "risk": "low",
            }]}
            cand = agent.build_candidate_codebook(cb, sug)
            assert cand is not None
            assert cand["version"] == "v0.2_candidate"

    def test_no_suggestions_no_candidate(self):
        agent = CoderTrainingAgent()
        cand = agent.build_candidate_codebook({"codes": []}, {"suggestions": []})
        assert cand is None


class TestFullRun:
    def test_run_mock_pipeline(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            # Create project structure
            (base / "01_codebook").mkdir(parents=True)
            (base / "04_pilot").mkdir(parents=True)
            _write_codebook(base / "01_codebook" / "codebook_v0.1.yaml")

            rows = []
            for i in range(40):
                txt = ["是不是数据反了", "谢谢大家", "okok", "无语", "我们可以先写", "好的", "没看懂",
                       "那先计算均值吗", "不是吧", "感觉会出问题"][i % 10]
                rows.append({"unit_id": f"u{i}", "unit_text": txt, "risk_flags": "",
                             "sample_reason": "", "group_id": "g01", "speaker_id": "s1",
                             "context_before": "", "context_after": ""})
            _write_csv(base / "04_pilot" / "pilot_sample_units.csv", rows)

            agent = CoderTrainingAgent(max_items=30)
            result = agent.run(base, max_items=30)
            assert result["training_samples"] == 30
            assert result["issues"] >= 1
            assert result["candidate_generated"] is True

            # Verify output files
            assert (base / "03_training" / "shared_coding_examples_round01.jsonl").exists()
            assert (base / "03_training" / "training_issues_round01.json").exists()
            assert (base / "01_codebook" / "codebook_v0.2_candidate.yaml").exists()
