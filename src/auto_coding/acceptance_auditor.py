"""v1.0 — AcceptanceAuditor: computed checks from actual files, no fixed narratives."""

from __future__ import annotations

import csv, json
from pathlib import Path


def audit(project_dir: str | Path) -> dict:
    root = Path(project_dir)
    checks: list[dict] = []

    # ── File existence ───────────────────────────────────────
    expected_files = [
        ("00_inputs/unit_table.csv", "Input table"),
        ("01_codebook/final_codebook_v1.0.yaml", "Final codebook YAML"),
        ("06_formal_coding/coder_A_formal.jsonl", "Coder A formal"),
        ("06_formal_coding/coder_B_formal.jsonl", "Coder B formal"),
        ("07_final/final_consensus_labels.jsonl", "Final consensus"),
        ("07_final/final_coding_table.csv", "Final coding table"),
        ("99_logs/archive_manifest.json", "Archive manifest"),
    ]
    for path, desc in expected_files:
        ex = (root / path).exists()
        checks.append({"check_name": f"file_exists:{desc}", "passed": ex,
                       "details": path if ex else f"MISSING: {path}"})

    # ── Row counts ───────────────────────────────────────────
    unit_n = _count_csv(root / "00_inputs" / "unit_table.csv")
    a_n = _count_jsonl(root / "06_formal_coding" / "coder_A_formal.jsonl")
    b_n = _count_jsonl(root / "06_formal_coding" / "coder_B_formal.jsonl")
    con_n = _count_jsonl(root / "07_final" / "final_consensus_labels.jsonl")
    tbl_n = _count_csv(root / "07_final" / "final_coding_table.csv")

    for label, expected, actual in [
        ("unit_table", unit_n, unit_n), ("coder_A", unit_n, a_n),
        ("coder_B", unit_n, b_n), ("consensus", unit_n, con_n),
        ("final_table", unit_n, tbl_n),
    ]:
        checks.append({"check_name": f"row_count:{label}", "passed": actual == expected,
                       "details": f"expected={expected}, actual={actual}"})

    # ── Consensus math ───────────────────────────────────────
    if con_n > 0:
        ag = _count_jsonl_where(root / "07_final" / "final_consensus_labels.jsonl", "consensus_source", "agreement")
        adj = _count_jsonl_where(root / "07_final" / "final_consensus_labels.jsonl", "consensus_source", "adjudication")
        un = _count_jsonl_where(root / "07_final" / "final_consensus_labels.jsonl", "consensus_source", "unresolved")
        ok = ag + adj + un == con_n
        checks.append({"check_name": "final_consensus_math", "passed": ok,
                       "details": f"agreement={ag}, adjudication={adj}, unresolved={un}, sum={ag+adj+un}"})

    # ── Coding table quality ─────────────────────────────────
    if tbl_n > 0:
        dup = 0; empty_code = 0; illegal = 0; valid = {"IS1","IS2","IS3","IS4"}
        seen = set()
        with open(root / "07_final" / "final_coding_table.csv", encoding="utf-8", newline="") as f:
            for r in csv.DictReader(f):
                uid = r.get("unit_id","")
                if uid in seen: dup += 1
                seen.add(uid)
                code = r.get("final_primary_code","")
                if not code: empty_code += 1
                elif code not in valid: illegal += 1
        checks.append({"check_name": "final_table_dup_ids", "passed": dup == 0, "details": f"duplicates={dup}"})
        checks.append({"check_name": "final_table_empty_codes", "passed": empty_code == 0, "details": f"empty_codes={empty_code}"})
        checks.append({"check_name": "final_table_legal_labels", "passed": illegal == 0, "details": f"illegal={illegal}"})

    # ── DeepSeek usage detection ─────────────────────────────
    real_calls = _count_jsonl(root / "09_deepseek_runs" / "round_01" / "logs" / "deepseek_api_calls.jsonl")

    # ── Reliability ──────────────────────────────────────────
    rel_path = root / "06_formal_coding" / "formal_agreement_metrics.json"
    kappa = None; pct = None
    if rel_path.exists():
        r = json.loads(rel_path.read_text(encoding="utf-8"))
        kappa = r.get("cohen_kappa"); pct = r.get("percent_agreement")

    # ── Verdict ──────────────────────────────────────────────
    all_pass = all(c["passed"] for c in checks)
    risks = []
    if real_calls == 0: risks.append("no_real_deepseek_calls_detected")
    status = "PASS" if all_pass else "FAIL"

    result = {
        "status": status,
        "formal_coding": {"coder_A_rows": a_n, "coder_B_rows": b_n, "kappa": kappa, "percent_agreement": pct},
        "deepseek": {"real_api_calls": real_calls},
        "risks": risks,
        "checks": checks,
    }
    return result


def _count_csv(p: Path) -> int:
    if not p.exists(): return 0
    with open(p, encoding="utf-8", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _count_jsonl(p: Path) -> int:
    if not p.exists(): return 0
    return sum(1 for _ in p.read_text(encoding="utf-8").splitlines() if _.strip())


def _count_jsonl_where(p: Path, key: str, val: str) -> int:
    if not p.exists(): return 0
    count = 0
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip(): continue
        try:
            if json.loads(line).get(key) == val: count += 1
        except: pass
    return count
