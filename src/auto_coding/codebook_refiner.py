"""Phase 5 — CodebookRefiner: generate codebook revision proposals.

Supports mock (rule-based) and deepseek modes.
Never overwrites source codebook. Only supplements rules/examples.
"""

from __future__ import annotations

import copy, json
from pathlib import Path
import yaml

ALLOWED_CHANGE_TYPES = {
    "add_boundary_case", "add_inclusion_rule", "add_exclusion_rule",
    "add_positive_example", "add_negative_example", "add_low_information_rule",
    "add_uncertain_rule", "add_priority_rule", "clarify_definition", "no_change",
}


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _load(p: Path) -> dict:
    if not p.exists(): return {}
    return json.loads(p.read_text(encoding="utf-8"))


def refine(project_dir: str | Path, round_id: str = "round_01",
           source_version: str = "v0.2_candidate",
           target_version: str = "v0.3_candidate",
           mode: str = "mock") -> dict:
    project_dir = Path(project_dir)
    rd = project_dir / "04_pilot" / round_id
    cb_dir = project_dir / "01_codebook"
    pr_dir = project_dir / "02_prompts"

    adj = _jl(rd / "adjudication_results.jsonl")
    cb_path = cb_dir / f"codebook_{source_version}.yaml"
    with open(cb_path, "r", encoding="utf-8") as f:
        codebook = yaml.safe_load(f)

    changes = _mock_changes(adj) if mode == "mock" else _deepseek_changes(adj, codebook)

    proposal = {"round_id": round_id, "source_codebook_version": source_version,
                "target_codebook_version": target_version, "mode": mode, "changes": changes}
    prop_path = cb_dir / f"codebook_revision_proposal_{round_id}.json"
    with open(prop_path, "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    candidate = _build_candidate(codebook, changes, target_version)
    _save_yaml(cb_dir / f"codebook_{target_version}.yaml", candidate)
    from .prompt_renderer import render
    render(str(cb_dir / f"codebook_{target_version}.yaml"), pr_dir, expected_version=target_version)
    _save_md(cb_dir / f"codebook_{target_version}.md", candidate)

    return {"changes_count": len(changes), "proposal_path": str(prop_path)}


def _mock_changes(adj: list[dict]) -> list[dict]:
    changes = []; seen = set(); ci = 1
    for r in adj:
        if r.get("unresolved") and r.get("affected_pattern"):
            p = r["affected_pattern"]
            if p in seen: continue
            seen.add(p)
            codes = sorted(set(p.split("-")))
            changes.append({"change_id": f"C{ci:04d}", "change_type": "add_boundary_case",
                            "target_codes": codes, "reason": r.get("decision_reason", ""),
                            "evidence_decisions": [r["decision_id"]],
                            "proposed_text": r.get("suggested_codebook_change", ""),
                            "risk": "low", "requires_recoding": False,
                            "affected_patterns": [p]})
            ci += 1
    for r in adj:
        if r.get("codebook_change_needed") and r["decision_id"] not in {
            c["evidence_decisions"][0] for c in changes}:
            changes.append({"change_id": f"C{ci:04d}", "change_type": "add_boundary_case",
                            "target_codes": [r.get("coder_A_label",""), r.get("coder_B_label","")],
                            "reason": r.get("decision_reason",""),
                            "evidence_decisions": [r["decision_id"]],
                            "proposed_text": r.get("suggested_codebook_change",""),
                            "risk": "low", "requires_recoding": False,
                            "affected_patterns": [r.get("affected_pattern","")]})
            ci += 1
    return changes


def _deepseek_changes(adj: list[dict], codebook: dict) -> list[dict]:
    try:
        from .deepseek_client import DeepSeekClient
        client = DeepSeekClient()
        result = client.chat_json("You revise codebooks.", json.dumps({
            "task": "Propose codebook changes.", "unresolved": [r for r in adj if r.get("unresolved")][:5],
            "codes": [c.get("code_id", c.get("label","?")) for c in codebook.get("codes",[])]}, ensure_ascii=False))
        changes = result.get("changes", [])
        for c in changes:
            if c.get("change_type") not in ALLOWED_CHANGE_TYPES:
                c["change_type"] = "add_boundary_case"
        return changes
    except Exception:
        return _mock_changes(adj)


def _build_candidate(codebook: dict, changes: list[dict], tv: str) -> dict:
    c = copy.deepcopy(codebook); c["version"] = tv; c["source_version"] = codebook.get("version", "v0.2")
    for ch in changes:
        if ch["change_type"] == "no_change": continue
        for code in c.get("codes", []):
            cid = code.get("label") or code.get("code_id", "")
            if cid in ch.get("target_codes", []) and ch.get("proposed_text"):
                code.setdefault("boundary_cases", []); tag = f"[{tv}] {ch['proposed_text']}"
                if tag not in code["boundary_cases"]: code["boundary_cases"].append(tag)
    return c


def _save_yaml(p: Path, d: dict):
    with open(p, "w", encoding="utf-8") as f:
        yaml.dump(d, f, allow_unicode=True, default_flow_style=False, sort_keys=False)


def _save_md(p: Path, data: dict):
    lines = [f"# Codebook {data.get('version','candidate')}", ""]
    for c in data.get("codes", []):
        cid = c.get("label") or c.get("code_id", "?"); cn = c.get("name_zh") or c.get("code_name", "?")
        lines.append(f"## {cid} {cn}")
        d = c.get("revised_operational_definition") or c.get("definition", "")
        if d: lines.extend(["", f"**定义**: {str(d)[:200]}", ""])
        for fld, lbl in [("inclusion_rules","纳入"),("exclusion_rules","排除"),
                         ("positive_examples","正例"),("boundary_cases","边界")]:
            items = c.get(fld, [])
            if items:
                lines.append(f"**{lbl}**:");
                for it in items: lines.append(f"- {it}")
                lines.append("")
        lines.append("---")
    p.write_text("\n".join(lines), encoding="utf-8")
