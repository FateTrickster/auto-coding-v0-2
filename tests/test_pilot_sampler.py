"""Tests for pilot_sampler.py — config-driven stratified sampling."""
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


def _make_unit(uid, group="g01", speaker="s1", text="test", risk_flags="", **kw):
    d = {
        "unit_id": uid,
        "group_id": group,
        "speaker_id": speaker,
        "unit_text": text,
        "risk_flags": risk_flags,
    }
    d.update(kw)
    return d


def _write_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True)


class TestBasicSampling:
    def test_18_groups_20_each_target_300(self):
        """18 groups, 20 units each = 360 total, target 300.
        Risk via risk_flags and structural flags, not hardcoded keywords."""
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(20):
                risk = ""
                st_flag = "FALSE"
                mc_flag = "FALSE"
                pmf_flag = "FALSE"
                if g == 5 and i < 6:
                    text = "g05对照文本"
                    risk = "context_dependent"
                elif i % 7 == 0:
                    text = f"组{gid}文本{i}"
                    risk = "boundary_risk"
                elif i % 7 == 1:
                    text = f"短文本{i % 3}"
                    st_flag = "TRUE" if len(text) <= 3 else "FALSE"
                elif i % 7 == 2:
                    text = f"组{gid}普通文本_{i}"
                    mc_flag = "TRUE"
                elif i % 7 == 3:
                    text = f"多功能文本？是的。还有更多。"
                    pmf_flag = "TRUE"
                else:
                    text = f"普通文本_{gid}_{i}"
                rows.append(_make_unit(
                    f"{gid}_u{i:03d}", gid, f"sp_{gid}_{i%3}", text, risk,
                    short_text_flag=st_flag,
                    missing_context_flag=mc_flag,
                    possible_multi_function_flag=pmf_flag,
                ))

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table_v0.1.csv"
            _write_csv(upath, rows)
            r1 = sample(upath, Path(d) / "out", target_size=300, seed=42)
            r2 = sample(upath, Path(d) / "out2", target_size=300, seed=42)

            assert r1["sampled_count"] == 300
            assert r1["groups_covered"] == 18

            csv_path = Path(r1["output_path"])
            with open(csv_path, encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            assert len(sampled) == 300
            ids = [r["unit_id"] for r in sampled]
            assert len(ids) == len(set(ids))

            # Verify pool2 subtypes present
            reasons = set(r["sample_reason"] for r in sampled)
            assert "high_risk_existing" in reasons
            assert "high_risk_difficulty" in reasons

            # Reproducible
            with open(Path(r2["output_path"]), encoding="utf-8-sig") as f:
                sampled2 = list(csv.DictReader(f))
            ids2 = [r["unit_id"] for r in sampled2]
            assert ids == ids2


class TestRiskConfigDriven:
    def test_boundary_pattern_from_config(self):
        """Configured boundary patterns are matched, not hardcoded keywords."""
        rows = []
        for i in range(50):
            rows.append(_make_unit(f"u{i}", text=f"普通文本{i}"))
        # Add some that match the config pattern
        rows.append(_make_unit("u_bound1", text="PROJECT_SPECIFIC_PATTERN出现在这里"))
        rows.append(_make_unit("u_bound2", text="包含PROJECT_SPECIFIC_PATTERN的文本"))
        rows.append(_make_unit("u_bound3", text="这没有那个词"))

        config = {
            "risk_sampling": {
                "enabled": True,
                "use_existing_risk_flags": False,
                "boundary_patterns": [
                    {"pattern": "PROJECT_SPECIFIC_PATTERN", "risk_type": "boundary_A_B", "source": "test_codebook"},
                ],
            },
            "generic_difficulty": {
                "short_text_max_length": None,
                "include_missing_context": False,
                "include_possible_multi_function": False,
            },
            "control_sampling": {"group_ids": []},
        }

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            cpath = Path(d) / "risk_config.yaml"
            _write_csv(upath, rows)
            _write_yaml(cpath, config)
            r = sample(upath, Path(d) / "out", target_size=20, seed=42,
                       risk_config_path=cpath)

            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))

            boundary_rows = [r for r in sampled if r["sample_reason"] == "high_risk_boundary"]
            assert len(boundary_rows) >= 1
            boundary_ids = {r["unit_id"] for r in boundary_rows}
            assert "u_bound1" in boundary_ids or "u_bound2" in boundary_ids

    def test_different_config_different_behavior(self):
        """Changing YAML pattern changes what gets sampled."""
        rows = [_make_unit(f"u{i}", text=f"普通文本{i}") for i in range(100)]
        rows.append(_make_unit("uA", text="PATTERN_A文本"))
        rows.append(_make_unit("uB", text="PATTERN_B文本"))

        config_a = {
            "risk_sampling": {
                "enabled": True, "use_existing_risk_flags": False,
                "boundary_patterns": [{"pattern": "PATTERN_A"}],
            },
            "generic_difficulty": {"short_text_max_length": None, "include_missing_context": False, "include_possible_multi_function": False},
            "control_sampling": {"group_ids": []},
        }
        config_b = {
            "risk_sampling": {
                "enabled": True, "use_existing_risk_flags": False,
                "boundary_patterns": [{"pattern": "PATTERN_B"}],
            },
            "generic_difficulty": {"short_text_max_length": None, "include_missing_context": False, "include_possible_multi_function": False},
            "control_sampling": {"group_ids": []},
        }

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)

            ca = Path(d) / "config_a.yaml"
            cb = Path(d) / "config_b.yaml"
            _write_yaml(ca, config_a)
            _write_yaml(cb, config_b)

            ra = sample(upath, Path(d) / "out_a", target_size=30, seed=42, risk_config_path=ca)
            rb = sample(upath, Path(d) / "out_b", target_size=30, seed=42, risk_config_path=cb)

            with open(Path(ra["output_path"]), encoding="utf-8-sig") as f:
                ids_a = {r["unit_id"] for r in csv.DictReader(f) if r["sample_reason"] == "high_risk_boundary"}
            with open(Path(rb["output_path"]), encoding="utf-8-sig") as f:
                ids_b = {r["unit_id"] for r in csv.DictReader(f) if r["sample_reason"] == "high_risk_boundary"}

            assert ids_a != ids_b


class TestControlGroup:
    def test_control_group_param(self):
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(10):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"sp_{gid}", f"{gid}文本{i}"))

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42, control_group="g05")

            assert r["control_group"] == "g05"
            assert r["control_group_count"] > 0

            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            cg_rows = [r for r in sampled if r["sample_reason"] == "control_group"]
            assert len(cg_rows) > 0

    def test_control_group_case_insensitive(self):
        rows = [_make_unit(f"u{i}", "G05", "s1", f"text{i}") for i in range(20)]
        rows += [_make_unit(f"u{i+20}", "g06", "s2", f"text{i+20}") for i in range(20)]

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=15, seed=42, control_group="g05")

            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            cg_rows = [r for r in sampled if r["sample_reason"] == "control_group"]
            assert len(cg_rows) > 0

    def test_function_arg_overrides_yaml(self):
        """CLI/function control_group overrides YAML."""
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(5):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"sp_{gid}", f"text{i}"))

        config = {"control_sampling": {"group_ids": ["g05"]}}

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            cpath = Path(d) / "config.yaml"
            _write_csv(upath, rows)
            _write_yaml(cpath, config)
            r = sample(upath, Path(d) / "out", target_size=30, seed=42,
                       risk_config_path=cpath, control_group="g08")

            assert r["control_group"] == "g08"
            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            cg_rows = [r for r in sampled if r["sample_reason"] == "control_group"]
            cg_groups = {r["group_id"] for r in cg_rows}
            assert "g08" in cg_groups


class TestNoConfigNoControl:
    def test_no_config_uses_existing_risk_flags(self):
        """Without config, Pool 2 uses existing risk_flags + generic difficulty."""
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(10):
                risk = "some_risk" if i < 3 else ""
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, f"sp_{gid}", f"text{i}", risk,
                                       short_text_flag="FALSE", missing_context_flag="FALSE",
                                       possible_multi_function_flag="FALSE"))

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)

            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)

            # Should have high_risk_existing from risk_flags
            assert "high_risk_existing" in reasons
            # Should NOT have high_risk_boundary (no config provided)
            assert "high_risk_boundary" not in reasons
            # Pool 3 skipped
            assert "control_group" not in reasons

            # Report should mention no config
            report = Path(r["report_path"]).read_text(encoding="utf-8")
            assert "未提供项目级边界规则" in report
            assert "未指定对照组" in report
            assert r["risk_config_used"] is False
            assert r["control_group"] is None

    def test_no_config_g05_not_prioritized(self):
        """Without control_group param, g05 is NOT special."""
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(10):
                rows.append(_make_unit(f"{gid}_u{i:03d}", gid, "s1", f"text{i}"))

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42)
            assert r["control_group"] is None
            assert r["control_group_count"] == 0


class TestRiskSamplingDisabled:
    def test_disabled_skips_pool2(self):
        config = {
            "risk_sampling": {"enabled": False, "use_existing_risk_flags": True, "boundary_patterns": []},
            "generic_difficulty": {},
            "control_sampling": {"group_ids": []},
        }
        rows = []
        for g in range(1, 19):
            gid = f"g{g:02d}"
            for i in range(10):
                rows.append(_make_unit(
                    f"{gid}_u{i:03d}", gid, "s1", f"text{i}",
                    risk_flags="high" if i < 3 else "",
                    short_text_flag="TRUE" if i < 5 else "FALSE",
                ))

        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            cpath = Path(d) / "config.yaml"
            _write_csv(upath, rows)
            _write_yaml(cpath, config)
            r = sample(upath, Path(d) / "out", target_size=50, seed=42, risk_config_path=cpath)

            with open(Path(r["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            reasons = set(r["sample_reason"] for r in sampled)
            assert "high_risk_existing" not in reasons
            assert "high_risk_boundary" not in reasons
            assert "high_risk_difficulty" not in reasons
            # Their quota goes to random_fill
            assert "random_fill" in reasons


class TestErrorHandling:
    def test_missing_required_field_raises(self):
        rows = [{"unit_id": "u1", "group_id": "g1", "speaker_id": "s1"}]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows, fields=["unit_id", "group_id", "speaker_id"])
            try:
                sample(upath, Path(d) / "out")
                assert False, "Should have raised"
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
            except ValueError as e:
                assert "u1" in str(e) or "Duplicate" in str(e)

    def test_target_size_zero_raises(self):
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, [_make_unit("u1")])
            try:
                sample(upath, Path(d) / "out", target_size=0)
                assert False
            except ValueError:
                pass

    def test_file_not_found_raises(self):
        try:
            sample(Path("/nonexistent/unit_table.csv"), Path("/tmp"))
            assert False
        except FileNotFoundError:
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
            assert "配置说明" in report

            for k in ["input_count", "target_size", "sampled_count", "groups_covered",
                      "speakers_covered", "high_risk_count", "control_group_count",
                      "risk_config_used", "control_group", "output_path", "report_path"]:
                assert k in r, f"Missing return key: {k}"

    def test_no_risk_flags_column(self):
        rows = [_make_unit(f"u{i}", text=f"text{i}") for i in range(50)]
        for r in rows:
            del r["risk_flags"]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            result = sample(upath, Path(d) / "out", target_size=20, seed=42)
            with open(Path(result["output_path"]), encoding="utf-8-sig") as f:
                sampled = list(csv.DictReader(f))
            assert all(r["risk_flags"] == "" for r in sampled)


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


class TestEmptyTextExcluded:
    def test_empty_text_filtered(self):
        rows = [
            _make_unit("u1", text="valid"),
            _make_unit("u2", text="   "),
            _make_unit("u3", text=""),
        ]
        with tempfile.TemporaryDirectory() as d:
            upath = Path(d) / "unit_table.csv"
            _write_csv(upath, rows)
            r = sample(upath, Path(d) / "out", target_size=10, seed=42)
            assert r["sampled_count"] == 1
