"""Tests for pilot_sampler.py — Round 1 structural difficulty + Round 2+ explicit units."""
import csv, tempfile, yaml
from pathlib import Path
from auto_coding.pilot_sampler import sample


def _write_csv(path, rows, fields=None):
    if fields is None:
        fields = list(rows[0].keys())
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(rows)


def _make_unit(uid, group="g01", speaker="s1", text="test", **kw):
    d = {
        "unit_id": uid,
        "group_id": group,
        "speaker_id": speaker,
        "unit_text": text,
    }
    d.update(kw)
    return d


def _write_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


class TestRound01StructuralDifficulty:
    def test_structural_short_text(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                is_short = (i % 5 == 0)  # spread across positions
                text = "ab" if is_short else f"普通文本{gid}_{i}"
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", text,
                                       short_text_flag="TRUE" if is_short else "FALSE",
                                       missing_context_flag="FALSE"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "structural_short_text" in reasons

    def test_structural_long_text(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                is_long = (i % 5 == 1)
                text = "x" * 150 if is_long else f"text{gid}_{i}"
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", text,
                                       long_text_flag="TRUE" if is_long else "FALSE",
                                       missing_context_flag="FALSE"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "structural_long_text" in reasons

    def test_structural_missing_context(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                is_mc = (i % 5 == 2)
                text = f"普通文本内容_{gid}_{i}"  # > 5 chars, won't trigger short
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", text,
                                       missing_context_flag="TRUE" if is_mc else "FALSE",
                                       short_text_flag="FALSE",
                                       context_before="" if is_mc else "ctx",
                                       context_after=""))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "structural_missing_context" in reasons

    def test_structural_multi_function(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                is_pmf = (i % 5 == 3)
                text = f"多功能文本_{gid}_{i}内容"  # > 5 chars
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", text,
                                       possible_multi_function_flag="TRUE" if is_pmf else "FALSE",
                                       missing_context_flag="FALSE",
                                       short_text_flag="FALSE",
                                       context_before="ctx",
                                       context_after="ctx2"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "structural_multi_function" in reasons


class TestRound01NoBoundary:
    def test_no_boundary_without_config(self):
        """Round 1 without risk_config should never produce boundary-related reasons."""
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(100)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "high_risk_boundary" not in reasons
            assert "high_risk_existing" not in reasons
            assert "high_risk_difficulty" not in reasons
            assert "explicit_unit" not in reasons

    def test_works_without_risk_flags_field(self):
        """Round 1 works fine when risk_flags column is absent."""
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(50)]
        for r in rows:
            r.pop("risk_flags", None)
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows, fields=["unit_id", "group_id", "speaker_id", "unit_text"])
            r = sample(upath, Path(d) / "out", target_size=20, seed=42)
            assert r["sampled_count"] == 20
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            assert all(row["risk_flags"] == "" for row in sampled)


class TestRound02PlusExplicitUnits:
    def test_explicit_units_from_config(self):
        """Round 2+: explicit_units from risk config are carried forward."""
        rows = [_make_unit(f"u{i}", text=f"text{i}",
                           missing_context_flag="FALSE") for i in range(200)]

        config = {
            "source_round_id": "round_01",
            "target_round_id": "round_02",
            "status": "candidate",
            "explicit_units": [
                {"unit_id": "u150", "risk_type": "previous_label_disagreement",
                 "confused_codes": ["IS2", "IS3"], "source": "disagreement_table",
                 "evidence_ids": ["D0001"], "status": "candidate"},
                {"unit_id": "u151", "risk_type": "unresolved_adjudication",
                 "confused_codes": ["IS2", "IS4"], "source": "adjudication_results",
                 "evidence_ids": ["D0002"], "status": "candidate"},
            ],
        }

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            cpath = Path(d) / "risk_config.yaml"
            _write_csv(upath, rows)
            _write_yaml(cpath, config)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42,
                       risk_config_path=cpath)

            assert r["risk_config_used"] is True
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "explicit_unit" in reasons


class TestGroupStratified:
    def test_basic_sampling(self):
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(20):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", f"text_{gid}_{i}",
                                       short_text_flag="FALSE", long_text_flag="FALSE",
                                       missing_context_flag="FALSE", possible_multi_function_flag="FALSE"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r1 = sample(upath, Path(d) / "out", target_size=300, seed=42)
            r2 = sample(upath, Path(d) / "out2", target_size=300, seed=42)
            assert r1["sampled_count"] == 300
            assert r1["groups_covered"] == 18
            with open(Path(r1["output_path"]), encoding="utf-8-sig") as f:
                ids1 = [r["unit_id"] for r in csv.DictReader(f)]
            with open(Path(r2["output_path"]), encoding="utf-8-sig") as f:
                ids2 = [r["unit_id"] for r in csv.DictReader(f)]
            assert ids1 == ids2
            assert len(ids1) == len(set(ids1))


class TestControlGroup:
    def test_control_group_param(self):
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(10):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", f"text{i}"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42, control_group="g05")
            assert r["control_group"] == "g05"
            assert r["control_group_count"] > 0

    def test_function_arg_overrides_yaml(self):
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(5):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", f"text{i}"))
        config = {"control_sampling": {"group_ids": ["g05"]}}
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            cpath = Path(d) / "config.yaml"
            _write_csv(upath, rows)
            _write_yaml(cpath, config)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42,
                       risk_config_path=cpath, control_group="g08")
            assert r["control_group"] == "g08"


class TestErrorHandling:
    def test_missing_required_field_raises(self):
        rows = [{"unit_id": "u1", "group_id": "g1", "speaker_id": "s1"}]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows, fields=["unit_id", "group_id", "speaker_id"])
            try:
                sample(upath, Path(d) / "out")
                assert False
            except ValueError as e:
                assert "unit_text" in str(e)

    def test_duplicate_unit_id_raises(self):
        rows = [_make_unit("u1", text="a"), _make_unit("u1", text="b")]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            try:
                sample(upath, Path(d) / "out")
                assert False
            except ValueError:
                pass

    def test_target_size_zero_raises(self):
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, [_make_unit("u1")])
            try:
                sample(upath, Path(d) / "out", target_size=0)
                assert False
            except ValueError:
                pass


class TestSmallDataset:
    def test_all_selected(self):
        rows = [_make_unit(f"u{i}") for i in range(5)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=100, seed=42)
            assert r["sampled_count"] == 5


class TestOutputFormat:
    def test_fields_and_report(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(100)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            for fld in ["unit_id", "group_id", "speaker_id", "unit_text", "risk_flags", "sample_reason"]:
                assert fld in sampled[0], f"Missing: {fld}"
            report = Path(r["report_path"]).read_text(encoding="utf-8")
            assert "Pool 构成" in report
            for k in ["input_count", "target_size", "sampled_count", "groups_covered",
                      "speakers_covered", "risk_config_used", "control_group",
                      "output_path", "report_path"]:
                assert k in r, f"Missing return key: {k}"


class TestReproducibility:
    def test_different_seed_different_result(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(200)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r1 = sample(upath, Path(d) / "out1", target_size=100, seed=42)
            r2 = sample(upath, Path(d) / "out2", target_size=100, seed=99)
            with open(Path(r1["output_path"]), encoding="utf-8-sig") as f:
                ids1 = set(r["unit_id"] for r in csv.DictReader(f))
            with open(Path(r2["output_path"]), encoding="utf-8-sig") as f:
                ids2 = set(r["unit_id"] for r in csv.DictReader(f))
            assert ids1 != ids2


class TestCoverageAnalysis:
    def test_group_all_covered(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", f"text_{gid}_{i}",
                                       missing_context_flag="FALSE", short_text_flag="FALSE",
                                       context_before="ctx"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            assert r["coverage"]["groups"]["missing"] == []
            assert not r["needs_resampling"]

    def test_group_missing_triggers_resampling(self):
        rows = []
        for g in range(1, 6):
            gid = f"g{g:02d}"
            for i in range(20):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", f"text_{gid}_{i}",
                                       missing_context_flag="FALSE", short_text_flag="FALSE",
                                       context_before="ctx"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            # target_size=5 barely covers 5 groups; Pool 1 only gets 4 slots (70%)
            r = sample(upath, Path(d) / "out", target_size=5, seed=42)
            # A group may be uncovered; with target=5 >= groups=5, this triggers resampling
            if r["needs_resampling"]:
                assert len(r["coverage"]["groups"]["missing"]) > 0
            # target_size == len(groups) edge case: missing groups are a real gap
            assert r["needs_resampling"] or len(r["coverage_warnings"]) > 0

    def test_structural_type_coverage_stats(self):
        rows = []
        for g in range(1, 4):
            gid = f"g{g:02d}"
            for i in range(20):
                is_short = (i % 5 == 0)
                text = "ab" if is_short else f"普通文本_{gid}_{i}"
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"s{i%3}", text,
                                       short_text_flag="TRUE" if is_short else "FALSE",
                                       missing_context_flag="FALSE",
                                       context_before="ctx"))
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42)
            st = r["coverage"]["structural_types"]
            assert st["short_text"]["population_count"] > 0
            assert st["short_text"]["sampled_count"] > 0
            assert st["short_text"]["covered"] is True

    def test_no_false_positive_structural_gap(self):
        """Type not existing in population should not trigger uncovered warning."""
        rows = [_make_unit(f"u{i}", text=f"text{i}",
                           missing_context_flag="FALSE", short_text_flag="FALSE",
                           context_before="ctx")
                for i in range(50)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=20, seed=42)
            st = r["coverage"]["structural_types"]
            for tname, tinfo in st.items():
                if tinfo["population_count"] == 0:
                    assert tinfo["covered"] is True, f"{tname} should be covered when pop=0"

    def test_full_population_coverage(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(5)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=100, seed=42)
            assert r["sampled_count"] == 5
            assert r["coverage"]["sample_ratio"] == 1.0
            assert any("全量选取" in w for w in r["coverage_warnings"])

    def test_report_contains_coverage_sections(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}",
                           missing_context_flag="FALSE", context_before="ctx")
                for i in range(100)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42)
            report = Path(r["report_path"]).read_text(encoding="utf-8")
            assert "样本覆盖审查" in report
            assert "Group 覆盖" in report
            assert "Speaker 覆盖" in report
            assert "结构类型覆盖" in report
            assert "补样判断" in report

    def test_coverage_matches_csv(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}",
                           missing_context_flag="FALSE", context_before="ctx")
                for i in range(100)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42)
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                csv_rows = list(csv.DictReader(f))
            assert r["coverage"]["sampled_count"] == len(csv_rows)

    def test_no_v01_file_generated(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(50)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=20, seed=42)
            out_dir = Path(r["output_path"]).parent
            assert not (out_dir / "pilot_sample_units_v0.1.csv").exists()
            assert not (out_dir / "pilot_sample_review_report.md").exists()

    def test_return_keys_include_coverage(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(50)]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=20, seed=42)
            assert "coverage" in r
            assert "needs_resampling" in r
            assert "coverage_warnings" in r
