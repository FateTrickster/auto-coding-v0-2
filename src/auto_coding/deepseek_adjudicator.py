"""v1.1 — DeepSeekAdjudicationAgent: strict LLM output boundaries.

LLM outputs ONLY: final_primary_code, decision_reason, codebook_change_needed,
                  suggested_codebook_change, requires_recoding, unresolved.
Program generates ALL metadata.
"""

from __future__ import annotations

import csv, json
from datetime import datetime, timezone
from pathlib import Path

LLM_ADJ = {"final_primary_code", "decision_reason", "codebook_change_needed",
           "suggested_codebook_change", "requires_recoding", "unresolved"}


def _jl(p: Path) -> list[dict]:
    if not p.exists(): return []
    return [json.loads(l) for l in p.read_text(encoding="utf-8").splitlines() if l.strip()]


def _v(raw: dict) -> tuple[dict, list]:
    c = {}; ig = []
    for k in LLM_ADJ: c[k] = raw.get(k)
    for b in ("codebook_change_needed", "requires_recoding", "unresolved"):
        if not isinstance(c.get(b), bool): c[b] = False
    ig = [k for k in raw if k not in LLM_ADJ]
    return c, ig


def run_deepseek_adjudication(project_dir: str | Path, round_id: str = "round_01",
                              codebook_version: str = "v1.0", mode: str = "mock",
                              retry_unresolved_once: bool = False) -> dict:
    root = Path(project_dir)
    rd = root / "09_deepseek_runs" / round_id; ts = datetime.now(timezone.utc).isoformat()

    a = _jl(rd / "coder_A_results.jsonl"); b = _jl(rd / "coder_B_results.jsonl")
    if not a or not b: return {"total": 0, "resolved": 0, "unresolved": 0,
                               "low_confidence_agreement_count": 0}

    am = {r["unit_id"]: r for r in a}; bm = {r["unit_id"]: r for r in b}
    dis = []
    low_conf_agree = []
    confidence_threshold = 0.70

    for uid in sorted(set(am) | set(bm)):
        ra = am.get(uid, {}); rb = bm.get(uid, {})
        if not ra.get("parse_ok") or not rb.get("parse_ok"): continue
        la = ra.get("primary_code"); lb = rb.get("primary_code")
        if la == lb:
            # Low-confidence agreement watchlist
            ca = float(ra.get("confidence", 0.5) or 0.5)
            cb = float(rb.get("confidence", 0.5) or 0.5)
            ua = ra.get("uncertain", False)
            ub = rb.get("uncertain", False)
            if ca < confidence_threshold or cb < confidence_threshold or ua or ub:
                low_conf_agree.append({
                    "unit_id": uid, "coder_A_label": la, "coder_B_label": lb,
                    "coder_A_confidence": ca, "coder_B_confidence": cb,
                    "coder_A_uncertain": ua, "coder_B_uncertain": ub,
                    "coder_A_reason": ra.get("reason", ""),
                    "coder_B_reason": rb.get("reason", ""),
                })
            continue
        dis.append({"unit_id": uid, "unit_text": "", "coder_A_label": la or "", "coder_B_label": lb or "",
                    "coder_A_reason": ra.get("reason",""), "coder_B_reason": rb.get("reason","")})

    # Write low-confidence agreement watchlist
    if low_conf_agree:
        _save(rd / "low_confidence_agreement_items.jsonl", low_conf_agree)
        with open(rd / "low_confidence_agreement_items.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(low_conf_agree[0].keys()))
            w.writeheader(); w.writerows(low_conf_agree)

    if dis:
        with open(rd / "disagreement_table.csv", "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(dis[0].keys())); w.writeheader(); w.writerows(dis)

    results = _mock_adj(dis, ts) if mode == "mock" else _ds_adj(dis, root, codebook_version, ts)

    # Retry unresolved
    if retry_unresolved_once and mode != "mock":
        unresolved = [(i, r) for i, r in enumerate(results) if r.get("unresolved")]
        if unresolved:
            valid = _load_valid_labels(root, codebook_version)
            from .deepseek_client import DeepSeekClient
            client = DeepSeekClient()
            for idx, r in unresolved:
                d = dis[idx] if idx < len(dis) else None
                if not d: continue
                # Conservative retry: pick the higher-confidence coder's label
                a_conf = float(am.get(d["unit_id"], {}).get("confidence", 0.5) or 0.5)
                b_conf = float(bm.get(d["unit_id"], {}).get("confidence", 0.5) or 0.5)
                final = d["coder_A_label"] if a_conf >= b_conf else d["coder_B_label"]
                results[idx] = _r(f"D{idx+1:04d}", d, final if final in valid else None,
                    f"[RETRY] Higher confidence coder selected ({'A' if a_conf >= b_conf else 'B'})",
                    ts, unresolved=(final not in valid),
                    resolution_attempts=2)
    _save(rd / "adjudication_results.jsonl", results)
    un = sum(1 for r in results if r.get("unresolved"))
    return {"total": len(results), "resolved": len(results) - un, "unresolved": un,
            "low_confidence_agreement_count": len(low_conf_agree)}


def _load_valid_labels(root, cv):
    import yaml
    cb_path = root / "01_codebook" / f"codebook_{cv}.yaml"
    if not cb_path.exists() and cv == "v1.0":
        cb_path = root / "01_codebook" / "final_codebook_v1.0.yaml"
    cb = yaml.safe_load(cb_path.read_text(encoding="utf-8")) if cb_path.exists() else {"codes": []}
    return {c.get("label") or c.get("code_id","") for c in cb.get("codes", [])}


def _mock_adj(dis, ts):
    return [_r(f"D{i:04d}", d, d.get("coder_A_label","") or d.get("coder_B_label",""), "[MOCK]", ts)
            for i, d in enumerate(dis, 1)]


def _ds_adj(dis, root, cv, ts):
    import yaml; from .deepseek_client import DeepSeekClient
    client = DeepSeekClient()
    cb_path = root / "01_codebook" / f"codebook_{cv}.yaml"
    if not cb_path.exists() and cv == "v1.0": cb_path = root / "01_codebook" / "final_codebook_v1.0.yaml"
    codebook = yaml.safe_load(cb_path.read_text(encoding="utf-8"))
    valid = {c.get("label") or c.get("code_id","") for c in codebook.get("codes", [])}
    results = []
    for i, d in enumerate(dis, 1):
        did = f"D{i:04d}"
        try:
            resp = client.chat_json("Adjudicate.", json.dumps({
                "task": "adjudicate", "coder_A": d.get("coder_A_label",""),
                "coder_B": d.get("coder_B_label",""),
                "A_reason": d.get("coder_A_reason",""),
                "B_reason": d.get("coder_B_reason",""),
            }, ensure_ascii=False), max_tokens=500)
            llm, ig = _v(resp)
            final = llm.get("final_primary_code","")
            results.append(_r(did, d, final if final in valid else None,
                llm.get("decision_reason",""), ts, codebook_change_needed=llm.get("codebook_change_needed", False),
                suggested_codebook_change=llm.get("suggested_codebook_change",""),
                requires_recoding=llm.get("requires_recoding", False),
                unresolved=final not in valid, ignored=ig))
        except Exception as e:
            results.append(_r(did, d, None, f"Error: {e}", ts, unresolved=True))
    return results


def _r(did, d, final, reason, ts, codebook_change_needed=False, suggested_codebook_change="",
       requires_recoding=False, unresolved=False, **kw):
    la = d.get("coder_A_label",""); lb = d.get("coder_B_label","")
    return {
        "final_primary_code": final, "decision_reason": reason,
        "codebook_change_needed": codebook_change_needed,
        "suggested_codebook_change": suggested_codebook_change,
        "requires_recoding": requires_recoding, "unresolved": unresolved,
        "unresolved_reason": reason if unresolved else "",
        "escalation_needed": unresolved,
        "resolution_attempts": 1 if not unresolved else 2,
        "decision_id": did, "unit_id": d.get("unit_id",""), "unit_text": d.get("unit_text",""),
        "coder_A_label": la, "coder_B_label": lb, "final_secondary_code": None,
        "adjudication_method": "deepseek_adjudication", "disagreement_type": "label_disagreement",
        "affected_pattern": f"{la}-{lb}" if la and lb else "", "parse_ok": True, "error": "",
        "timestamp": ts, "ignored_llm_fields": kw.get("ignored", []),
    }


def _save(p: Path, items: list[dict]):
    with open(p, "w", encoding="utf-8") as f:
        for it in items: f.write(json.dumps(it, ensure_ascii=False) + "\n")
