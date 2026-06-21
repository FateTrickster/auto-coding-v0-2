"""Phase 2 — CoderTrainingAgent: train coders with shared coding examples.

Simulates human coding workflow steps 7-8: joint reading → shared coding.
Currently implements mock/rule-based mode. Real LLM mode deferred.
"""

from __future__ import annotations

import copy
import csv
import json
import random
from collections import Counter
from pathlib import Path

import yaml

# ── Mock rules for training analysis ──────────────────────

MOCK_TRAINING_RULES = [
    (["是不是", "那先", "数据反了", "不太对", "没看懂", "不懂",
      "怎么办", "标准差吗", "感觉会出问题"], "IS3"),
    (["谢谢", "okok谢谢", "咱们先", "要不要", "我来", "我可以",
      "我写", "我负责"], "IS4"),
    (["不是吧", "无语", "烦"], "IS1"),
    (["okok", "好的", "可以", "ok", "嗯", "行"], "IS2"),
]

DEFAULT_CODE = "IS2"

ALT_MAP = {"IS3": "IS2", "IS4": "IS2", "IS1": "IS2", "IS2": "IS4"}

ISSUE_MAP = {
    "IS3": ("missing_boundary_case", ["IS2", "IS3"]),
    "IS4": ("missing_boundary_case", ["IS2", "IS4"]),
    "IS1": ("missing_boundary_case", ["IS1", "IS2"]),
    "IS2": ("low_information_rule_missing", ["IS2"]),
}


def _find_primary(text: str) -> str:
    for keywords, code in MOCK_TRAINING_RULES:
        for kw in keywords:
            if kw in text:
                return code
    if len(text) <= 5:
        return "IS2"
    return DEFAULT_CODE


class CoderTrainingAgent:
    def __init__(self, mode: str = "mock", max_items: int = 30, seed: int = 42):
        self.mode = mode
        self.max_items = max_items
        self.seed = seed

    def select_training_samples(self, pilot_csv_path: str | Path) -> list[dict]:
        p = Path(pilot_csv_path)
        if not p.exists():
            raise FileNotFoundError(f"Pilot not found: {p}")
        with open(p, "r", encoding="utf-8", newline="") as f:
            all_units = list(csv.DictReader(f))

        if len(all_units) <= self.max_items:
            selected = list(all_units)
        else:
            rng = random.Random(self.seed)
            hr = [u for u in all_units if u.get("risk_flags", "").strip()]
            norm = [u for u in all_units if not u.get("risk_flags", "").strip()]
            n_hr = min(len(hr), self.max_items * 2 // 3)
            n_norm = self.max_items - n_hr
            sel_hr = rng.sample(hr, n_hr) if len(hr) > n_hr else hr
            sel_norm = rng.sample(norm, n_norm) if len(norm) > n_norm else norm
            selected = sel_hr + sel_norm
            rng.shuffle(selected)
            selected = selected[:self.max_items]

        for u in selected:
            reasons = []
            if u.get("risk_flags", "").strip():
                reasons.append(f"risk:{u['risk_flags']}")
            if u.get("sample_reason", "").strip():
                reasons.append(u["sample_reason"])
            if not reasons:
                txt = u.get("unit_text", "")
                if len(txt) <= 5:
                    reasons.append("short_text")
                if "?" in txt:
                    reasons.append("question")
                if not reasons:
                    reasons.append("stratified_random")
            u["training_selection_reason"] = "; ".join(reasons)
        return selected

    def generate_shared_coding_examples(
        self, training_samples: list[dict], codebook: dict
    ) -> list[dict]:
        examples = []
        for u in training_samples:
            text = u.get("unit_text", "").strip()
            if not text:
                continue

            primary = _find_primary(text)
            alt = ALT_MAP.get(primary)
            alt_codes = [alt] if alt else []
            confusion = f"{primary}-{alt}" if alt else ""

            is_short = len(text) <= 5
            iss_type, _ = ISSUE_MAP.get(primary, ("missing_boundary_case", []))
            if is_short and primary == "IS2":
                iss_type = "low_information_rule_missing"

            note = ""
            if "boundary" in iss_type:
                note = f"该样例可用于说明 {primary} 与 {alt} 的边界。"
            elif "example" in iss_type:
                note = f"该样例是 {primary} 的典型正例。"
            elif "low_information" in iss_type:
                note = "极短文本，需低信息规则辅助。"

            examples.append({
                "unit_id": u.get("unit_id", ""),
                "unit_text": text,
                "candidate_primary_code": primary,
                "candidate_secondary_code": None,
                "confidence": 0.82,
                "evidence_span": text[:60],
                "reason": f"[MOCK] keyword → {primary}",
                "possible_alternative_codes": alt_codes,
                "confusion_risk": bool(alt),
                "confusion_pairs": [confusion] if confusion else [],
                "codebook_issue_detected": True,
                "issue_types": [iss_type],
                "suggested_training_note": note,
            })
        return examples

    def generate_training_issues(
        self, shared_examples: list[dict], codebook: dict
    ) -> dict:
        issue_map: dict[str, dict] = {}
        for ex in shared_examples:
            for itype in ex.get("issue_types", []):
                if itype not in issue_map:
                    issue_map[itype] = {
                        "issue_type": itype, "target_codes": set(), "evidence_units": []}
                primary = ex["candidate_primary_code"]
                issue_map[itype]["target_codes"].add(primary)
                for a in ex.get("possible_alternative_codes", []):
                    issue_map[itype]["target_codes"].add(a)
                issue_map[itype]["evidence_units"].append(ex["unit_id"])

        desc = {
            "missing_boundary_case": "标签对之间缺乏足够的边界案例说明。",
            "missing_positive_example": "缺少正例支持。",
            "low_information_rule_missing": "极短文本缺乏处理规则。",
        }
        fixes = {
            "missing_boundary_case": "补充边界案例，明确区分条件。",
            "missing_positive_example": "补充典型正例。",
            "low_information_rule_missing": "补充低信息文本处理规则。",
        }

        issues = []
        for idx, (itype, info) in enumerate(issue_map.items(), 1):
            n = len(info["evidence_units"])
            severity = "low" if n <= 2 else ("medium" if n <= 8 else "high")
            issues.append({
                "issue_id": f"TI{idx:04d}",
                "issue_type": itype,
                "target_codes": sorted(info["target_codes"]),
                "evidence_units": info["evidence_units"][:10],
                "description": desc.get(itype, f"培训发现 {itype}。"),
                "suggested_fix": fixes.get(itype, ""),
                "severity": severity,
                "count": n,
            })
        return {"round_id": "round01", "total_training_items": len(shared_examples), "issues": issues}

    def generate_revision_suggestions(
        self, training_issues: dict, codebook: dict
    ) -> dict:
        suggestions = []
        for issue in training_issues.get("issues", []):
            if issue["severity"] == "low":
                continue
            codes = issue.get("target_codes", [])
            if len(codes) < 2 and "boundary" in issue["issue_type"]:
                continue
            suggestions.append({
                "suggestion_id": f"TS{len(suggestions)+1:04d}",
                "change_type": "add_boundary_case",
                "target_codes": codes,
                "reason": issue["description"],
                "evidence_training_items": issue["evidence_units"][:5],
                "proposed_text": issue["suggested_fix"],
                "risk": "low",
            })
        return {
            "source_codebook_version": "v0.1",
            "target_candidate_version": "v0.2_candidate",
            "suggestions": suggestions,
        }

    def build_candidate_codebook(
        self, codebook: dict, revision_suggestions: dict
    ) -> dict | None:
        suggestions = revision_suggestions.get("suggestions", [])
        if not suggestions:
            return None
        candidate = copy.deepcopy(codebook)
        candidate["version"] = "v0.2_candidate"
        candidate["source_version"] = codebook.get("version", "v0.1")
        for sg in suggestions:
            target_codes = sg.get("target_codes", [])
            proposed = sg.get("proposed_text", "")
            for code in candidate.get("codes", []):
                cid = code.get("label") or code.get("code_id", "")
                if cid in target_codes:
                    code.setdefault("boundary_cases", [])
                    if proposed not in code["boundary_cases"]:
                        code["boundary_cases"].append(f"[v0.2] {proposed}")
        return candidate

    def run(self, project_dir: str | Path, codebook_version: str = "v0.1",
            round_id: str = "round01", max_items: int = 30) -> dict:
        project_dir = Path(project_dir)
        self.max_items = max_items
        tdir = project_dir / "03_training"
        tdir.mkdir(parents=True, exist_ok=True)
        cb_dir = project_dir / "01_codebook"
        pr_dir = project_dir / "02_prompts"

        with open(cb_dir / f"codebook_{codebook_version}.yaml", "r", encoding="utf-8") as f:
            codebook = yaml.safe_load(f)

        pilot = project_dir / "04_pilot" / "pilot_sample_units.csv"
        if not pilot.exists():
            raise FileNotFoundError(
                f"Pilot sample not found: {pilot}\n"
                f"Run `sample-pilot` first."
            )

        # Step 1
        samples = self.select_training_samples(pilot)
        self._csv(tdir / f"training_sample_units_{round_id}.csv", samples,
                  ["unit_id","unit_text","context_before","context_after",
                   "group_id","speaker_id","sample_reason","risk_flags",
                   "training_selection_reason"])

        # Step 2
        shared = self.generate_shared_coding_examples(samples, codebook)
        self._jsonl(tdir / f"shared_coding_examples_{round_id}.jsonl", shared)

        # Step 3
        issues = self.generate_training_issues(shared, codebook)
        self._json(tdir / f"training_issues_{round_id}.json", issues)
        self._md(tdir / f"training_issues_{round_id}.md", self._issues_report(issues))

        # Step 4
        sug = self.generate_revision_suggestions(issues, codebook)
        self._json(tdir / f"training_codebook_revision_suggestions_{round_id}.json", sug)

        # Step 5
        cand = self.build_candidate_codebook(codebook, sug)
        gen = cand is not None
        if gen:
            self._yaml(cb_dir / "codebook_v0.2_candidate.yaml", cand)
            self._md(cb_dir / "codebook_v0.2_candidate.md",
                     self._codebook_md(cand))
            from .prompt_renderer import render
            render(str(cb_dir / "codebook_v0.2_candidate.yaml"),
                   pr_dir, expected_version="v0.2_candidate")

        return {"training_samples": len(samples), "shared_examples": len(shared),
                "issues": len(issues["issues"]),
                "suggestions": len(sug["suggestions"]),
                "candidate_generated": gen}

    def _csv(self, p, rows, fields):
        with open(p, "w", encoding="utf-8", newline="") as f:
            w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
            w.writeheader(); w.writerows(rows)

    def _jsonl(self, p, items):
        with open(p, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")

    def _json(self, p, d):
        with open(p, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=2)

    def _yaml(self, p, d):
        with open(p, "w", encoding="utf-8") as f:
            yaml.dump(d, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    def _md(self, p, text):
        p.write_text(text, encoding="utf-8")

    def _issues_report(self, issues):
        lines = [f"# Training Issues — {issues['round_id']}", "",
                 f"Items: {issues['total_training_items']}, Issues: {len(issues['issues'])}", "",
                 "| ID | Type | Codes | Evidence | Severity |",
                 "|----|------|-------|----------|----------|"]
        for i in issues["issues"]:
            lines.append(f"| {i['issue_id']} | {i['issue_type']} | "
                         f"{','.join(i['target_codes'])} | "
                         f"{','.join(i['evidence_units'][:3])} | {i['severity']} |")
        lines += ["", "## Fixes"]
        for i in issues["issues"]:
            lines.append(f"- **{i['issue_id']}**: {i['suggested_fix']}")
        return "\n".join(lines)

    def _codebook_md(self, data):
        lines = [f"# Codebook {data.get('version','candidate')}", ""]
        for c in data.get("codes", []):
            lines.append(f"## {c.get('label','?')} {c.get('name_zh','?')}")
            d = c.get('revised_operational_definition','')
            if d: lines.extend(["", f"**定义**: {d[:200]}", ""])
            for fld, lbl in [("inclusion_rules","纳入"),("exclusion_rules","排除"),
                             ("positive_examples","正例"),("boundary_cases","边界")]:
                items = c.get(fld, [])
                if items:
                    lines.append(f"**{lbl}**:")
                    for it in items: lines.append(f"- {it}")
                    lines.append("")
            lines.append("---")
        return "\n".join(lines)
