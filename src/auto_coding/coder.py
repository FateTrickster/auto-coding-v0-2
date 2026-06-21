"""Phase 3 — MockCoderAgent: rule-based independent pilot coding (A/B).

Supports coder_id=A and coder_id=B with slight rule variation for disagreement simulation.
Does NOT call DeepSeek in mock mode.
"""

from __future__ import annotations

import csv
import json
import random
from pathlib import Path

import yaml

# ── Mock rule tables ──────────────────────────────────────

RULES_A = [
    (["是不是", "那先", "没看懂", "不懂", "不太对", "怎么办",
      "标准差吗", "感觉会出问题", "数据反了", "什么是"], "IS3"),
    (["谢谢", "okok谢谢", "咱们先", "要不要", "我来", "我可以",
      "我写", "我负责", "你先", "加油", "很好", "辛苦"], "IS4"),
    (["不是吧", "无语", "烦", "讨厌", "想死", "崩溃", "太难了",
      "不行", "不好"], "IS1"),
    (["okok", "ok", "好的", "可以", "嗯", "行", "对", "收到",
      "明白"], "IS2"),
]

RULES_B = [
    (["是不是", "那先", "没看懂", "不懂", "不太对",
      "标准差吗", "感觉会出问题", "数据反了", "什么是"], "IS3"),
    (["谢谢", "okok谢谢", "咱们先", "要不要", "我来", "我可以",
      "我写", "加油", "很好"], "IS4"),
    (["不是吧", "无语", "烦", "讨厌", "崩溃", "不行", "不好"], "IS1"),
    (["okok", "ok", "好的", "可以", "嗯", "行", "对", "收到",
      "明白", "我来写吗"], "IS2"),
]

# Agent B occasionally diverges from A on these patterns
B_DIVERGE = {
    "我来": ("IS2", "IS4"),
    "我可以": ("IS2", "IS4"),
    "我写": ("IS2", "IS4"),
    "怎么办": ("IS3", "IS2"),
}

DEFAULT_CODE = "IS2"


def _find_code(text: str, rules: list, coder_id: str, rng: random.Random) -> str:
    """Apply keyword rules to find primary code."""
    for keywords, code in rules:
        for kw in keywords:
            if kw in text:
                # Check for B divergence
                if coder_id == "B":
                    for div_kw, (from_c, to_c) in B_DIVERGE.items():
                        if div_kw in text and code == from_c and rng.random() < 0.25:
                            return to_c
                return code
    if len(text) <= 5:
        return "IS2"
    return DEFAULT_CODE


def _build_evidence(text: str) -> str:
    return text[:80] if len(text) > 80 else text


def _build_reason(primary: str, text: str, coder_id: str) -> str:
    markers = {
        "IS1": "negative",
        "IS2": "neutral",
        "IS3": "confused",
        "IS4": "positive",
    }
    return f"[MOCK] Coder {coder_id}: keyword-based classification as {primary} ({markers.get(primary, 'default')})"


class MockCoderAgent:
    """Rule-based coder for pilot coding. Independent per coder_id."""

    def __init__(self, coder_id: str = "A", seed: int = 42):
        self.coder_id = coder_id
        self.rng = random.Random(seed + (1 if coder_id == "B" else 0))
        self.rules = RULES_A if coder_id == "A" else RULES_B

    def code(self, units: list[dict], codebook_version: str) -> list[dict]:
        """Code a list of units. Returns list of result dicts."""
        results = []
        valids = {"IS1", "IS2", "IS3", "IS4"}
        for u in units:
            text = u.get("unit_text", "").strip()
            if not text:
                results.append(_error_result(u.get("unit_id", ""), self.coder_id,
                                             codebook_version, "empty text"))
                continue

            primary = _find_code(text, self.rules, self.coder_id, self.rng)
            if primary not in valids:
                results.append(_error_result(u.get("unit_id", ""), self.coder_id,
                                             codebook_version, f"invalid code: {primary}"))
                continue

            is_short = len(text) <= 5
            uncertain = (is_short or primary == "IS2")
            needs_discussion = (self.coder_id == "B" and text and
                                any(kw in text for kw in ["我来", "我可以", "怎么办",
                                                          "是不是", "那先"]))

            results.append({
                "unit_id": u.get("unit_id", ""),
                "primary_code": primary,
                "secondary_code": None,
                "confidence": 0.65 if is_short else 0.82,
                "uncertain": uncertain,
                "needs_discussion": needs_discussion,
                "evidence_span": _build_evidence(text),
                "reason": _build_reason(primary, text, self.coder_id),
                "codebook_version": codebook_version,
                "coder_id": self.coder_id,
                "parse_ok": True,
            })
        return results


def _error_result(unit_id: str, coder_id: str, version: str, error: str) -> dict:
    return {
        "unit_id": unit_id, "primary_code": None, "secondary_code": None,
        "confidence": None, "uncertain": True, "needs_discussion": False,
        "evidence_span": "", "reason": f"Error: {error}",
        "codebook_version": version, "coder_id": coder_id, "parse_ok": False,
        "error": error,
    }


def run_pilot_coding(
    project_dir: str | Path,
    round_id: str = "round_01",
    codebook_version: str = "v0.2_candidate",
    mode: str = "mock",
    seed: int = 42,
) -> dict:
    """Run both Coder A and Coder B on pilot sample units."""
    project_dir = Path(project_dir)
    round_dir = project_dir / "04_pilot" / round_id
    round_dir.mkdir(parents=True, exist_ok=True)

    # Load pilot units
    pilot_path = project_dir / "04_pilot" / "pilot_sample_units.csv"
    if not pilot_path.exists():
        raise FileNotFoundError(
            f"Pilot sample not found: {pilot_path}\n"
            f"Run `sample-pilot` first."
        )

    with open(pilot_path, "r", encoding="utf-8", newline="") as f:
        units = list(csv.DictReader(f))

    # Coder A
    agent_a = MockCoderAgent(coder_id="A", seed=seed)
    results_a = agent_a.code(units, codebook_version)
    _save_jsonl(round_dir / "coder_A_results.jsonl", results_a)

    # Coder B
    agent_b = MockCoderAgent(coder_id="B", seed=seed)
    results_b = agent_b.code(units, codebook_version)
    _save_jsonl(round_dir / "coder_B_results.jsonl", results_b)

    ok_a = sum(1 for r in results_a if r["parse_ok"])
    ok_b = sum(1 for r in results_b if r["parse_ok"])

    return {
        "coder_a_count": len(results_a), "coder_a_ok": ok_a,
        "coder_b_count": len(results_b), "coder_b_ok": ok_b,
        "round_dir": str(round_dir),
    }


def _save_jsonl(path: Path, items: list[dict]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")
