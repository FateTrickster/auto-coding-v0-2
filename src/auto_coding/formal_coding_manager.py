"""Phase 7 — FormalCodingManager: full double-coding with frozen codebook."""

from __future__ import annotations

import csv, json
from pathlib import Path


def run_formal(project_dir: str | Path, mode: str = "mock") -> dict:
    project_dir = Path(project_dir)
    out_dir = project_dir / "06_formal_coding"
    out_dir.mkdir(parents=True, exist_ok=True)

    cb_path = project_dir / "01_codebook" / "final_codebook_v1.0.yaml"
    if not cb_path.exists():
        raise FileNotFoundError("final_codebook_v1.0.yaml not found. Run freeze-codebook first.")

    unit_path = project_dir / "00_inputs" / "unit_table.csv"
    if not unit_path.exists():
        raise FileNotFoundError("unit_table.csv not found.")

    with open(unit_path, "r", encoding="utf-8", newline="") as f:
        units = list(csv.DictReader(f))

    from .coder import MockCoderAgent
    a = MockCoderAgent("A", seed=42); b = MockCoderAgent("B", seed=42)
    ra = a.code(units, "v1.0"); rb = b.code(units, "v1.0")
    _jl(out_dir / "coder_A_formal.jsonl", ra); _jl(out_dir / "coder_B_formal.jsonl", rb)

    ok_a = sum(1 for r in ra if r["parse_ok"]); ok_b = sum(1 for r in rb if r["parse_ok"])
    (out_dir / "formal_coding_progress.md").write_text(
        f"# Formal Coding Progress\n\n- Units: {len(units)}\n- Coder A: {ok_a}/{len(ra)} OK\n- Coder B: {ok_b}/{len(rb)} OK\n", encoding="utf-8")
    return {"coder_a_total": len(ra), "coder_a_ok": ok_a, "coder_b_total": len(rb), "coder_b_ok": ok_b}


def _jl(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
