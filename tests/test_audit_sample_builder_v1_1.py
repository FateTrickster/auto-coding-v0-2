"""v1.1 tests for audit_sample_builder."""
import csv, json, tempfile
from pathlib import Path
from auto_coding.audit_sample_builder import build_audit_sample


def _setup(d: Path, n: int = 50):
    (d / "00_inputs").mkdir(parents=True)
    (d / "06_formal_coding").mkdir(parents=True)
    (d / "07_final").mkdir(parents=True)

    # unit_table
    with open(d / "00_inputs" / "unit_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_id", "unit_text", "context_before", "context_after", "group_id", "speaker_id"])
        w.writeheader()
        for i in range(n):
            w.writerow({"unit_id": f"u{i}", "unit_text": f"text-{i}", "context_before": "", "context_after": "", "group_id": "g1", "speaker_id": "s1"})

    # final_coding_table
    labels = ["IS2", "IS3", "IS3", "IS4", "IS2", "IS2", "IS2", "IS4", "IS3", "IS1"]
    with open(d / "07_final" / "final_coding_table.csv", "w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["unit_id", "unit_text", "final_primary_code", "group_id", "speaker_id"])
        w.writeheader()
        for i in range(n):
            w.writerow({"unit_id": f"u{i}", "unit_text": f"text-{i}", "final_primary_code": labels[i % len(labels)], "group_id": "g1", "speaker_id": "s1"})

    # consensus
    with open(d / "07_final" / "final_consensus_labels.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"unit_id": f"u{i}", "final_primary_code": labels[i % len(labels)]}) + "\n")

    # formal A/B with some disagreement
    with open(d / "06_formal_coding" / "coder_A_formal.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            f.write(json.dumps({"unit_id": f"u{i}", "primary_code": labels[i % len(labels)], "parse_ok": True}) + "\n")

    with open(d / "06_formal_coding" / "coder_B_formal.jsonl", "w", encoding="utf-8") as f:
        for i in range(n):
            code = "IS2" if i % 10 == 0 else labels[i % len(labels)]  # 10% disagreement
            f.write(json.dumps({"unit_id": f"u{i}", "primary_code": code, "parse_ok": True}) + "\n")


class TestBuildAuditSample:
    def test_builds_stratified_sample(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d), n=50)
            m = build_audit_sample(str(d), target_size=20)
            assert m["actual_size"] <= m["target_size"]
            assert m["actual_size"] >= 5

    def test_generates_template_csv(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d), n=30)
            m = build_audit_sample(str(d), target_size=15)
            tp = Path(m["template_path"])
            assert tp.exists()
            with open(tp, encoding="utf-8", newline="") as f:
                rows = list(csv.DictReader(f))
            assert "human_label" in rows[0]
            assert rows[0]["human_label"] == ""  # empty for human to fill

    def test_generates_mock_labels(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d), n=20)
            build_audit_sample(str(d), target_size=10)
            ml_path = Path(d) / "08_validation" / "mock_labels_for_sample.jsonl"
            assert ml_path.exists()

    def test_label_distribution_recorded(self):
        with tempfile.TemporaryDirectory() as d:
            _setup(Path(d), n=40)
            m = build_audit_sample(str(d), target_size=15)
            assert "label_distribution" in m
            assert sum(m["label_distribution"].values()) == m["actual_size"]
