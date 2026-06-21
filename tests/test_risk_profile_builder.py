"""Tests for risk_profile_builder.py."""
import csv, json, tempfile, yaml
from pathlib import Path
from auto_coding.risk_profile_builder import build_risk_config


def _write_csv(path, rows, fields=None):
    if fields is None and rows:
        fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields or [])
        w.writeheader()
        w.writerows(rows)


def _write_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f)


def _write_jsonl(path, items):
    with open(path, "w", encoding="utf-8") as f:
        for it in items:
            f.write(json.dumps(it, ensure_ascii=False) + "\n")


class TestBuildRiskConfig:
    def _setup_round01_outputs(self, d: Path):
        rd = d / "04_pilot" / "round_01"
        rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        (d / "04_pilot" / "risk_profiles").mkdir(parents=True, exist_ok=True)

        # Disagreement table with 3 label disagreements
        # Disagreement table: u1-u3 IS2-IS3, u4 IS2-IS4 label disagreements
        # u5 is agreement; u6 NOT in disagreement table (only appears in adjudication as unresolved)
        _write_csv(rd / "disagreement_table.csv", [
            {"unit_id": "u1", "unit_text": "text1", "coder_A_label": "IS2", "coder_B_label": "IS3",
             "is_label_disagreement": "True", "coder_A_confidence": "0.8", "coder_B_confidence": "0.7"},
            {"unit_id": "u2", "unit_text": "text2", "coder_A_label": "IS2", "coder_B_label": "IS3",
             "is_label_disagreement": "True", "coder_A_confidence": "0.6", "coder_B_confidence": "0.9"},
            {"unit_id": "u3", "unit_text": "text3", "coder_A_label": "IS2", "coder_B_label": "IS3",
             "is_label_disagreement": "True", "coder_A_confidence": "0.8", "coder_B_confidence": "0.5"},
            {"unit_id": "u4", "unit_text": "text4", "coder_A_label": "IS2", "coder_B_label": "IS4",
             "is_label_disagreement": "True", "coder_A_confidence": "0.7", "coder_B_confidence": "0.8"},
            {"unit_id": "u5", "unit_text": "text5", "coder_A_label": "IS2", "coder_B_label": "IS2",
             "is_label_disagreement": "False", "coder_A_confidence": "0.9", "coder_B_confidence": "0.9"},
        ])

        # Disagreement analysis JSON
        _write_json(rd / "disagreement_analysis.json", {
            "valid_pairs": 5, "label_disagreement_count": 4, "agreement_count": 1,
        })

        # Adjudication results with 1 unresolved
        # Adjudication results: u1 resolved, u6 unresolved (not a separate disagreement from above)
        _write_jsonl(rd / "adjudication_results.jsonl", [
            {"decision_id": "D0001", "unit_id": "u1", "coder_A_label": "IS2", "coder_B_label": "IS3",
             "final_primary_code": "IS2", "disagreement_type": "label", "unresolved": False,
             "decision_reason": "IS2 correct"},
            {"decision_id": "D0002", "unit_id": "u6", "coder_A_label": "IS2", "coder_B_label": "IS3",
             "final_primary_code": None, "disagreement_type": "label", "unresolved": True,
             "decision_reason": "cannot resolve"},
        ])

        # Codebook revision proposal with affected_patterns
        _write_json(d / "01_codebook" / "codebook_revision_proposal_round_01.json", {
            "changes": [
                {"change_id": "C0001", "target_codes": ["IS2", "IS3"],
                 "affected_patterns": ["IS2-IS3"], "evidence_decisions": ["D0001"],
                 "reason": "high confusion", "change_type": "add_boundary_case"},
            ],
        })

    def test_builds_candidate_from_round01_outputs(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            assert r["explicit_units_count"] > 0
            assert r["confusion_pairs_count"] > 0
            assert r["boundary_patterns_count"] > 0
            assert Path(r["output_path"]).exists()

    def test_disagreement_rows_become_explicit_units(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)
            eu_ids = {eu["unit_id"] for eu in config["explicit_units"]}
            # u1, u2, u3 are IS2-IS3 disagreements; u4 is IS2-IS4
            assert "u1" in eu_ids
            assert "u4" in eu_ids
            # u5 is agreement, should NOT be in explicit_units
            assert "u5" not in eu_ids

    def test_confusion_pairs_built(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)
            pairs = config["confusion_pairs"]
            assert len(pairs) >= 1
            # IS2-IS3 should be the top pair with count 3
            is23 = [p for p in pairs if set(p["codes"]) == {"IS2", "IS3"}]
            assert len(is23) == 1
            assert is23[0]["disagreement_count"] == 3

    def test_unresolved_adjudications_become_risk_units(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)
            unresolved = [eu for eu in config["explicit_units"]
                          if eu.get("risk_type") == "unresolved_adjudication"]
            assert len(unresolved) >= 1
            assert any(eu["unit_id"] == "u6" for eu in unresolved)

    def test_affected_patterns_from_revision_proposal_only(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)
            patterns = config["boundary_patterns"]
            # Should have "IS2-IS3" from revision proposal
            assert len(patterns) >= 1
            assert patterns[0]["match_type"] == "label_pair"
            assert patterns[0]["pattern"] == "IS2-IS3"
            assert patterns[0]["status"] == "candidate"

    def test_does_not_extract_keywords_from_unit_text(self):
        """boundary_patterns should NOT contain natural-language keywords from unit_text."""
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)
            patterns = config["boundary_patterns"]
            # All patterns should be label_pair match_type, not text contains
            for p in patterns:
                assert p["match_type"] == "label_pair"
                assert p["source"] == "codebook_revision_proposal"

    def test_all_items_have_status_and_evidence_ids(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            with open(Path(r["output_path"]), encoding="utf-8") as f:
                config = yaml.safe_load(f)

            for eu in config["explicit_units"]:
                assert "status" in eu, f"Missing status in {eu['unit_id']}"
                assert "evidence_ids" in eu, f"Missing evidence_ids in {eu['unit_id']}"
                assert eu["status"] == "candidate"

            for cp in config["confusion_pairs"]:
                assert "status" in cp
                assert "evidence_ids" in cp
                assert cp["status"] == "candidate"

            for bp in config["boundary_patterns"]:
                assert "status" in bp
                assert "evidence_ids" in bp
                assert bp["status"] == "candidate"

    def test_writes_to_risk_profiles_not_00_inputs(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            self._setup_round01_outputs(b)
            r = build_risk_config(b, "round_01", "round_02")
            out = Path(r["output_path"])
            assert "risk_profiles" in str(out)
            assert "00_inputs" not in str(out)
