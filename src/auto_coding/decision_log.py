"""Phase 4 — DecisionLogAgent: generate decision_log.md from adjudication."""

from __future__ import annotations

import json
from pathlib import Path


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def generate(project_dir: str | Path, round_id: str = "round_01") -> dict:
    rd = Path(project_dir) / "04_pilot" / round_id
    adj = _jl(rd / "adjudication_results.jsonl")

    lines = ["# Decision Log", "", f"Round: {round_id}", f"Decisions: {len(adj)}", "", "---", ""]
    for r in adj:
        lines += [
            f"## Decision {r['decision_id']}", "",
            f"**unit_id**: {r.get('unit_id','?')}", "",
            f"**原文**: {r.get('unit_text','')}", "",
            f"**coder_A**: {r.get('coder_A_label','?')}", "",
            f"**coder_B**: {r.get('coder_B_label','?')}", "",
            f"**最终决定**: {r.get('final_primary_code','unresolved')}", "",
            f"**决定理由**: {r.get('decision_reason','')}", "",
            f"**分歧类型**: {r.get('disagreement_type','?')}", "",
            f"**codebook 修改**: {r.get('suggested_codebook_change','不需要') if r.get('codebook_change_needed') else '不需要'}", "",
            f"**是否影响旧编码**: {'是' if r.get('requires_recoding') else '否'}", "",
            f"**unresolved**: {'是' if r.get('unresolved') else '否'}", "",
            "---", "",
        ]
    (rd / "decision_log.md").write_text("\n".join(lines), encoding="utf-8")
    return {"decisions": len(adj)}
