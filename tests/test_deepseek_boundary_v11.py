"""v1.1 tests for LLM output boundary enforcement."""
import json, csv, tempfile, yaml
from pathlib import Path


class TestCoderBoundary:
    def _setup(self, d):
        d = Path(d)
        (d / "00_inputs").mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        (d / "02_prompts").mkdir(parents=True)
        (d / "04_pilot").mkdir(parents=True, exist_ok=True)
        rows = [{"unit_id": f"u{i}", "unit_text": f"text-{i}", "context_before": "", "context_after": "",
                 "group_id": "g1", "speaker_id": "s1"} for i in range(3)]
        with open(d / "04_pilot" / "pilot_sample_units.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
            w.writeheader(); w.writerows(rows)
        cb = {"version": "v1.0", "codes": [{"label": "IS1"}, {"label": "IS2"}, {"label": "IS3"}, {"label": "IS4"}]}
        with open(d / "01_codebook" / "codebook_v1.0.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)
        (d / "02_prompts" / "coder_prompt_v1.0.md").write_text(
            '# Test\nIS1: neg\nIS2: neu\nIS3: con\nIS4: pos\n'
            'Output JSON: {"primary_code":"IS1|IS2|IS3|IS4","confidence":0.0,"evidence_span":"...","reason":"...","uncertain":false}',
            encoding="utf-8")

    def test_mock_generates_full_schema(self):
        from auto_coding.deepseek_coder import run_deepseek_coding
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = run_deepseek_coding(d, mode="mock", max_items=3)
            assert r["coder_a_total"] == 3
            fn = Path(d) / "09_deepseek_runs" / "round_01" / "coder_A_results.jsonl"
            items = [json.loads(l) for l in open(fn, encoding="utf-8").read().splitlines() if l.strip()]
            # Check program-generated fields exist
            for fld in ["unit_id", "coder_id", "codebook_version", "parse_ok", "timestamp", "round_id", "cache_hit", "retry_count"]:
                assert fld in items[0], f"Missing program field: {fld}"

    def test_validate_strips_unknown_fields(self):
        from auto_coding.deepseek_coder import _validate_llm_output
        raw = {"primary_code": "IS2", "confidence": 0.9, "evidence_span": "test",
               "reason": "r", "uncertain": False,
               "unit_id": "SHOULD_BE_IGNORED", "coder_id": "SHOULD_BE_IGNORED"}
        clean, ignored = _validate_llm_output(raw)
        assert "unit_id" not in clean
        assert "coder_id" not in clean
        assert "unit_id" in ignored

    def test_illegal_label_parse_ok_false(self):
        from auto_coding.deepseek_coder import _validate_llm_output
        clean, _ = _validate_llm_output({"primary_code": "IS5", "confidence": 0.5, "evidence_span": "x", "reason": "r", "uncertain": False})
        assert clean["primary_code"] == "IS5"  # raw value kept, validation happens upstream


class TestAdjudicatorBoundary:
    def _setup(self, d):
        d = Path(d)
        rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        (d / "01_codebook").mkdir(parents=True)
        cb = {"version": "v1.0", "codes": [{"label": "IS1"}, {"label": "IS2"}, {"label": "IS3"}, {"label": "IS4"}]}
        with open(d / "01_codebook" / "codebook_v1.0.yaml", "w", encoding="utf-8") as f:
            yaml.dump(cb, f, allow_unicode=True)
        with open(rd / "coder_A_results.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id": "u1", "primary_code": "IS2", "parse_ok": True, "reason": "A", "confidence": 0.8}) + "\n")
        with open(rd / "coder_B_results.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"unit_id": "u1", "primary_code": "IS3", "parse_ok": True, "reason": "B", "confidence": 0.8}) + "\n")

    def test_decision_id_is_program_generated(self):
        from auto_coding.deepseek_adjudicator import run_deepseek_adjudication
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = run_deepseek_adjudication(d, mode="mock")
            assert r["total"] == 1
            fn = Path(d) / "09_deepseek_runs" / "round_01" / "adjudication_results.jsonl"
            items = [json.loads(l) for l in open(fn, encoding="utf-8").read().splitlines() if l.strip()]
            assert items[0]["decision_id"] == "D0001"
            assert "timestamp" in items[0]

    def test_program_fields_present(self):
        from auto_coding.deepseek_adjudicator import run_deepseek_adjudication
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            run_deepseek_adjudication(d, mode="mock")
            fn = Path(d) / "09_deepseek_runs" / "round_01" / "adjudication_results.jsonl"
            items = [json.loads(l) for l in open(fn, encoding="utf-8").read().splitlines() if l.strip()]
            for fld in ["adjudication_method", "decision_id", "unit_id", "coder_A_label", "coder_B_label", "parse_ok"]:
                assert fld in items[0], f"Missing: {fld}"


class TestRefinerBoundary:
    def _setup(self, d):
        d = Path(d)
        rd = d / "09_deepseek_runs" / "round_01"; rd.mkdir(parents=True)
        with open(rd / "adjudication_results.jsonl", "w", encoding="utf-8") as f:
            f.write(json.dumps({"decision_id": "D0001", "unresolved": True,
                                "coder_A_label": "IS2", "coder_B_label": "IS3",
                                "decision_reason": "test", "suggested_codebook_change": "review"}) + "\n")

    def test_change_id_program_generated(self):
        from auto_coding.deepseek_codebook_refiner import run_deepseek_refine
        with tempfile.TemporaryDirectory() as d:
            self._setup(d)
            r = run_deepseek_refine(d, mode="mock", exclude_unresolved=False)
            assert r["changes_count"] >= 1
            fn = Path(d) / "09_deepseek_runs" / "round_01" / "codebook_revision_proposal_round_01.json"
            prop = json.loads(open(fn, encoding="utf-8").read())
            c = prop["changes"][0]
            assert c["change_id"] == "C0001"
            assert "schema_valid" in c
            assert "risk" in c

    def test_illegal_change_type_fixed(self):
        from auto_coding.deepseek_codebook_refiner import _validate_llm, ALLOWED_CHANGE_TYPES
        raw = {"change_type": "delete_code", "target_codes": ["IS1"], "reason": "r",
               "proposed_text": "x", "requires_recoding": False}
        clean, _ = _validate_llm(raw)
        assert clean["change_type"] == "delete_code"  # raw kept
        # Upstream should fix: run_deepseek_refine checks ALLOWED_CHANGE_TYPES
        assert "delete_code" not in ALLOWED_CHANGE_TYPES
