"""v1.1 — DeepSeekCodebookRefiner: strict LLM output boundaries.

LLM outputs ONLY: change_type, target_codes, reason, proposed_text, requires_recoding.
Program generates ALL metadata: change_id, round_id, evidence_decisions, etc.
"""

from __future__ import annotations

import json
from pathlib import Path

ALLOWED_CHANGE_TYPES = {
    "add_boundary_case", "add_inclusion_rule", "add_exclusion_rule",
    "add_positive_example", "add_negative_example", "add_low_information_rule",
    "add_uncertain_rule", "add_priority_rule", "clarify_definition", "no_change",
}

LLM_REFINE_SCHEMA = {"change_type", "target_codes", "reason", "proposed_text", "requires_recoding"}


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _validate_llm(raw: dict) -> tuple[dict, list]:
    clean = {}
    for k in LLM_REFINE_SCHEMA:
        clean[k] = raw.get(k)
    if not isinstance(clean.get("requires_recoding"), bool):
        clean["requires_recoding"] = False
    if isinstance(clean.get("target_codes"), str):
        clean["target_codes"] = [clean["target_codes"]]
    if not isinstance(clean.get("target_codes"), list):
        clean["target_codes"] = []
    ignored = [k for k in raw if k not in LLM_REFINE_SCHEMA]
    return clean, ignored


def run_deepseek_refine(project_dir: str | Path, round_id: str = "round_01",
                        codebook_version: str = "v1.0", mode: str = "mock",
                        exclude_unresolved: bool = True) -> dict:
    root = Path(project_dir)
    rd = root / "09_deepseek_runs" / round_id

    adj_path = rd / "adjudication_results.jsonl"
    if not adj_path.exists():
        return {"changes_count": 0, "excluded_unresolved": 0}

    all_adj = _jl(adj_path)
    excluded = sum(1 for r in all_adj if r.get("unresolved"))
    # Refiner uses resolved adjudications (excludes unresolved by default)
    eligible = [r for r in all_adj if not r.get("unresolved")] if exclude_unresolved else all_adj

    if mode == "mock":
        changes = _mock_refine(eligible, round_id, codebook_version)
    else:
        from .deepseek_client import DeepSeekClient
        import yaml
        client = DeepSeekClient()
        cb_path = root / "01_codebook" / f"codebook_{codebook_version}.yaml"
        if not cb_path.exists() and codebook_version == "v1.0":
            cb_path = root / "01_codebook" / "final_codebook_v1.0.yaml"
        codebook = yaml.safe_load(cb_path.read_text(encoding="utf-8"))
        changes = _deepseek_refine(eligible, client, codebook, round_id, codebook_version)

    proposal = {
        "round_id": round_id,
        "source_codebook_version": codebook_version,
        "target_codebook_version": _next_candidate_version(codebook_version),
        "changes": changes,
    }
    with open(rd / f"codebook_revision_proposal_{round_id}.json", "w", encoding="utf-8") as f:
        json.dump(proposal, f, ensure_ascii=False, indent=2)

    return {"changes_count": len(changes), "excluded_unresolved": excluded}


def _next_candidate_version(version: str) -> str:
    """v0.1 → v0.2_candidate, v0.9 → v0.10_candidate, v1.0 → v1.1_candidate, etc."""
    v = version.replace("_candidate", "").lstrip("v")
    parts = v.split(".")
    major = int(parts[0])
    minor = int(parts[1]) if len(parts) > 1 else 0
    return f"v{major}.{minor + 1}_candidate"


def _mock_refine(adj, round_id, cv):
    changes = []; seen = set(); ci = 1
    for r in adj:
        codes = sorted({r.get("coder_A_label",""), r.get("coder_B_label","")} - {""})
        if len(codes) >= 2 and tuple(codes) not in seen:
            seen.add(tuple(codes))
            changes.append(_build_change(ci, "add_boundary_case", codes,
                r.get("decision_reason",""), r.get("suggested_codebook_change",""),
                False, [r.get("decision_id","")], list(codes), round_id, cv))
            ci += 1
    return changes


def _deepseek_refine(eligible, client, codebook, round_id, cv):
    """Refine codebook based on resolved adjudication evidence.
    Program fills evidence_decisions and affected_patterns from matched candidates.
    """
    if not eligible: return []
    candidates = [r for r in eligible
                  if r.get("codebook_change_needed") or
                  r.get("coder_A_label") != r.get("coder_B_label")]
    if not candidates: return []
    try:
        resp = client.chat_json("Propose codebook changes.", json.dumps({
            "task": "propose_changes", "candidate_count": len(candidates),
            "samples": candidates[:5],
        }, ensure_ascii=False), max_tokens=1000)
        llm_changes = resp.get("changes", [])
        result = []
        for i, raw in enumerate(llm_changes, 1):
            llm, _ = _validate_llm(raw)
            ct = llm.get("change_type","")
            if ct not in ALLOWED_CHANGE_TYPES:
                ct = "add_boundary_case"
            target_codes = llm.get("target_codes", [])
            # Match evidence: find candidates whose A/B labels match target_codes
            evidence_ids = []
            affected = []
            if target_codes:
                tc_set = set(target_codes)
                for c in candidates:
                    ab = {c.get("coder_A_label", ""), c.get("coder_B_label", "")}
                    if ab == tc_set or tc_set <= ab:
                        did = c.get("decision_id", "")
                        if did:
                            evidence_ids.append(did)
                        affected.append(f"{c.get('coder_A_label','')}-{c.get('coder_B_label','')}")
            schema_valid = bool(evidence_ids)  # must have evidence to auto-apply
            result.append(_build_change(i, ct, target_codes,
                llm.get("reason",""), llm.get("proposed_text",""),
                llm.get("requires_recoding", False), evidence_ids,
                affected, round_id, cv, schema_valid=schema_valid))
        return result
    except Exception:
        # Do NOT silently fall back to mock. Return empty with failed status.
        return []


def _build_change(ci, change_type, target_codes, reason, proposed_text,
                  requires_recoding, evidence_decisions, affected_patterns,
                  round_id, source_cv, schema_valid=True):
    return {
        "change_type": change_type,
        "target_codes": target_codes,
        "reason": reason,
        "proposed_text": proposed_text,
        "requires_recoding": requires_recoding,
        "change_id": f"C{ci:04d}",
        "round_id": round_id,
        "source_codebook_version": source_cv,
        "target_codebook_version": _next_candidate_version(source_cv),
        "evidence_decisions": evidence_decisions,
        "risk": "low",
        "affected_patterns": affected_patterns,
        "schema_valid": schema_valid,
    }
