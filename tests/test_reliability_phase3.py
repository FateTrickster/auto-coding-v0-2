"""Tests for Phase 3 ReliabilityAgent."""
import json, tempfile
from pathlib import Path
from auto_coding.reliability import compute_reliability


def _write_jsonl(path: Path, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def _make_result(unit_id, primary, coder_id, parse_ok=True, uncertain=False):
    return {"unit_id": unit_id, "primary_code": primary, "secondary_code": None,
            "confidence": 0.8, "uncertain": uncertain, "needs_discussion": False,
            "evidence_span": "test", "reason": "test",
            "codebook_version": "v0.2", "coder_id": coder_id, "parse_ok": parse_ok}


class TestComputeReliability:
    def test_perfect_agreement(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "IS3", "A")]
            b = [_make_result("u1", "IS2", "B"), _make_result("u2", "IS3", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["cohen_kappa"] == 1.0
            assert m["percent_agreement"] == 1.0

    def test_complete_disagreement(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result(f"u{i}", "IS1", "A") for i in range(5)]
            b = [_make_result(f"u{i}", "IS4", "B") for i in range(5)]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["cohen_kappa"] < 0.1

    def test_invalid_label_filtered(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "ISX", "A")]
            b = [_make_result("u1", "IS2", "B"), _make_result("u2", "IS2", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["n_invalid"] >= 1
            assert m["n_valid_pairs"] == 1

    def test_missing_unit_detected(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "IS3", "A")]
            b = [_make_result("u1", "IS2", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["n_missing"] >= 1

    def test_label_distribution(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "IS3", "A"),
                 _make_result("u3", "IS3", "A")]
            b = [_make_result("u1", "IS2", "B"), _make_result("u2", "IS3", "B"),
                 _make_result("u3", "IS4", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["label_distribution_A"]["IS3"] == 2
            assert m["label_distribution_B"]["IS4"] == 1

    def test_confusion_matrix_output(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "IS3", "A")]
            b = [_make_result("u1", "IS2", "B"), _make_result("u2", "IS4", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert (rd / "confusion_matrix.csv").exists()
            assert (rd / "agreement_metrics.json").exists()
            assert (rd / "reliability_report.md").exists()

    def test_uncertain_rate(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A", uncertain=True),
                 _make_result("u2", "IS3", "A", uncertain=False)]
            b = [_make_result("u1", "IS2", "B", uncertain=False),
                 _make_result("u2", "IS3", "B", uncertain=False)]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["uncertain_rate_A"] == 0.5
            assert m["uncertain_rate_B"] == 0.0

    def test_krippendorff_alpha(self):
        with tempfile.TemporaryDirectory() as d:
            base = Path(d)
            rd = base / "04_pilot" / "round_01"
            rd.mkdir(parents=True)
            a = [_make_result("u1", "IS2", "A"), _make_result("u2", "IS3", "A")]
            b = [_make_result("u1", "IS2", "B"), _make_result("u2", "IS3", "B")]
            _write_jsonl(rd / "coder_A_results.jsonl", a)
            _write_jsonl(rd / "coder_B_results.jsonl", b)
            m = compute_reliability(str(base))
            assert m["krippendorff_alpha"] >= 0.9


class TestCohenKappa:
    def test_perfect_agreement(self):
        from auto_coding.reliability import _cohen_kappa
        a = ["IS2", "IS2", "IS3", "IS3"]
        b = ["IS2", "IS2", "IS3", "IS3"]
        k = _cohen_kappa(a, b)
        assert abs(k - 1.0) < 0.01

    def test_complete_disagreement(self):
        from auto_coding.reliability import _cohen_kappa
        a = ["IS1", "IS1", "IS1", "IS1"]
        b = ["IS4", "IS4", "IS4", "IS4"]
        k = _cohen_kappa(a, b)
        assert k < 0.1

    def test_weighted_kappa(self):
        from auto_coding.reliability import _cohen_kappa
        a = ["IS1", "IS2", "IS3", "IS4"]
        b = ["IS2", "IS2", "IS3", "IS4"]
        k_w = _cohen_kappa(a, b, weighted=True)
        k_uw = _cohen_kappa(a, b, weighted=False)
        assert k_w >= k_uw  # weighted should be >= unweighted for adjacent disagreement

    def test_single_label_all_same(self):
        from auto_coding.reliability import _cohen_kappa
        a = ["IS2", "IS2", "IS2"]
        b = ["IS2", "IS2", "IS2"]
        k = _cohen_kappa(a, b)
        assert abs(k - 1.0) < 0.01

    def test_edge_empty(self):
        from auto_coding.reliability import _cohen_kappa
        assert _cohen_kappa([], []) == 0.0
        assert _cohen_kappa(["IS1"], []) == 0.0
