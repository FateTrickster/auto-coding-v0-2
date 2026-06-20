"""LLM client: real API (OpenAI-compatible) + mock mode."""

from __future__ import annotations

import json
import random
from dataclasses import dataclass
from typing import Any

import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

from .config import Config


@dataclass
class LLMResponse:
    content: str
    model: str
    finish_reason: str = "stop"


class LLMClient:
    """OpenAI-compatible chat completions client."""

    def __init__(self, config: Config, agent_label: str = "A"):
        self.config = config
        self.agent_label = agent_label
        self.model = config.model_coder_a if agent_label == "A" else config.model_coder_b

    def chat(self, system_prompt: str, user_message: str) -> LLMResponse:
        """Send a chat completion request."""
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_message},
        ]
        return self._call_api(messages)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        reraise=True,
    )
    def _call_api(self, messages: list[dict]) -> LLMResponse:
        """Make the HTTP request with retry logic. Handles empty responses."""
        url = f"{self.config.base_url.rstrip('/')}/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.config.api_key}",
            "Content-Type": "application/json",
        }
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": self.config.temperature,
            "max_tokens": self.config.max_tokens,
        }

        timeout = httpx.Timeout(self.config.request_timeout)

        def _do_request() -> LLMResponse:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=payload, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if not content or not content.strip():
                return None  # signal empty response
            return LLMResponse(
                content=content,
                model=data.get("model", self.model),
                finish_reason=choice.get("finish_reason", "stop"),
            )

        result = _do_request()
        if result is not None:
            return result

        # Retry once for empty response
        result = _do_request()
        if result is not None:
            return result

        raise RuntimeError("Empty response from API after retry")


# ── Mock mode ───────────────────────────────────────────────

# Mock rules: keyword-based, Agent B gets small divergence
MOCK_RULES = [
    (["谢谢", "辛苦了", "我帮你", "加油", "咱们一起", "我们先", "我们要不先"], "IS4"),
    (["无语", "烦死了", "烦", "讨厌", "想死", "不是吧"], "IS1"),
    (["没看懂", "不懂", "是不是数据反了", "为什么这里要用", "怎么办", "咋办",
      "不太对", "什么是", "原因是什么", "什么意思", "标准差吗", "标准差吗？",
      "数据反了", "是不是错了", "理解错了", "怎么弄"], "IS3"),
    (["okok", "可以", "行", "对", "嗯", "好的", "收到"], "IS2"),
]

# Agent B will intentionally disagree on these specific IDs (for testing)
MOCK_B_DIVERGE_IDS: set[str] = set()


def _init_mock_diverge(total_ids: list[str], diverge_ratio: float = 0.05):
    """Select a small subset of IDs where Agent B will diverge."""
    global MOCK_B_DIVERGE_IDS
    # Keep existing if already set
    if MOCK_B_DIVERGE_IDS:
        return
    n = max(1, int(len(total_ids) * diverge_ratio))
    selected = random.sample(total_ids, min(n, len(total_ids)))
    MOCK_B_DIVERGE_IDS = set(selected)


def _mock_label(
    content: str, item_id: str, agent_label: str, valid_labels: tuple[str, ...]
) -> tuple[str, float, str, str | None]:
    """Mock coding based on keyword rules."""
    content_lower = content.lower()

    # Determine base label
    label = "IS2"  # default
    matched_rule = "default IS2"
    for keywords, lbl in MOCK_RULES:
        for kw in keywords:
            if kw.lower() in content_lower:
                label = lbl
                matched_rule = f"keyword '{kw}' -> {lbl}"
                break
        if label != "IS2":
            break

    # Agent B: diverge on selected IDs
    if agent_label == "B" and item_id in MOCK_B_DIVERGE_IDS:
        # Pick a different label
        others = [l for l in valid_labels if l != label]
        label = random.choice(others)
        matched_rule = f"[MOCK DIVERGE B] changed to {label}"

    # Confidence: 0.90 for strong keywords, 0.70 for default
    if label == "IS2" and matched_rule == "default IS2":
        confidence = 0.65
    elif matched_rule.startswith("[MOCK DIVERGE"):
        confidence = 0.55
    else:
        confidence = 0.88

    # Evidence span: first 60 chars
    evidence = content[:60] if len(content) > 60 else content

    alt_label: str | None = None
    if confidence < 0.75:
        others = [l for l in valid_labels if l != label]
        alt_label = others[0]

    return label, confidence, evidence, alt_label


def run_mock_coding(
    inputs: list[dict],
    agent_label: str,
    valid_labels: tuple[str, ...],
    seed: int = 42,
) -> list[dict]:
    """Run mock coding for an agent.

    Agent B has slight intentional divergence for testing.
    """
    rng = random.Random(seed + (1 if agent_label == "B" else 0))
    global MOCK_B_DIVERGE_IDS
    # Re-seed per agent for reproducibility
    random.seed(seed + (1 if agent_label == "B" else 0))

    all_ids = [item["id"] for item in inputs]
    _init_mock_diverge(all_ids, diverge_ratio=0.06)

    results = []
    for item in inputs:
        label, confidence, evidence, alt = _mock_label(
            item["content"], item["id"], agent_label, valid_labels
        )

        # Build rationale
        rationale = f"[MOCK] Agent {agent_label}: content classified as {label} based on keyword matching."
        why_not = "无"
        uncertainty = "无"
        if alt:
            why_not = f"[MOCK] Alternative {alt} was considered but ruled out by keyword rules."
            uncertainty = "边界样本，低置信度"

        raw = json.dumps({
            "id": item["id"],
            "label": label,
            "confidence": confidence,
            "rationale": rationale,
            "evidence_span": evidence,
            "uncertainty": uncertainty,
            "alternative_label": alt,
            "why_not_alternative": why_not,
        }, ensure_ascii=False)

        results.append({
            "id": item["id"],
            "label": label,
            "confidence": confidence,
            "rationale": rationale,
            "evidence_span": evidence,
            "uncertainty": uncertainty,
            "alternative_label": alt,
            "why_not_alternative": why_not,
            "agent": agent_label,
            "model": f"mock-{agent_label}",
            "raw_response": raw,
            "parse_ok": True,
            "error": None,
        })

    return results
