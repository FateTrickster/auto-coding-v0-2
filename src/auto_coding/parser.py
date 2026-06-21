"""Robust JSON parsing from LLM responses.

Strategy (in order):
  1. Direct json.loads
  2. Extract ```json ... ``` fenced block, json.loads
  3. Extract ``` ... ``` (no language tag), json.loads
  4. Balanced object extraction via brace matching
  5. All fail → return error for upstream retry or logging

Does NOT perform character-level heuristic repair of malformed JSON.
DeepSeek uses JSON object response format; bad JSON is retried, not guessed.
"""

from __future__ import annotations

import json
import re
from typing import Any


def robust_json_parse(text: str) -> tuple[dict | None, str | None]:
    """Try multiple strategies to extract a JSON object from LLM output.

    Returns:
        (parsed_dict_or_None, error_message_or_None)
    """
    if not text or not text.strip():
        return None, "Empty response text"

    text = text.strip()

    # Strategy 1: direct json.loads
    try:
        obj = json.loads(text)
        if isinstance(obj, dict):
            return obj, None
    except json.JSONDecodeError:
        pass

    # Strategy 2: extract ```json ... ``` code block
    json_block = _extract_code_block(text, "json")
    if json_block:
        try:
            obj = json.loads(json_block)
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError:
            pass

    # Strategy 3: extract ``` ... ``` (no language tag)
    generic_block = _extract_code_block(text, None)
    if generic_block:
        try:
            obj = json.loads(generic_block)
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError:
            pass

    # Strategy 4: find first JSON object by brace matching
    obj = _find_first_json_object(text)
    if obj is not None:
        return obj, None

    return None, "Could not parse JSON from response"


def _extract_code_block(text: str, lang: str | None = "json") -> str | None:
    """Extract content from a markdown code block."""
    if lang:
        pattern = rf"```{lang}\s*\n(.*?)```"
    else:
        pattern = r"```\s*\n(.*?)```"
    m = re.search(pattern, text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return None


def _find_first_json_object(text: str) -> dict | None:
    """Try to find the first balanced JSON object in text."""
    start = text.find("{")
    if start == -1:
        return None

    depth = 0
    in_string = False
    escape = False
    for i in range(start, len(text)):
        ch = text[i]
        if escape:
            escape = False
            continue
        if ch == "\\" and in_string:
            escape = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                candidate = text[start : i + 1]
                try:
                    obj = json.loads(candidate)
                    if isinstance(obj, dict):
                        return obj
                except json.JSONDecodeError:
                    pass
                break

    return None


def validate_coding_output(
    parsed: dict, valid_labels: tuple[str, ...]
) -> tuple[dict | None, str | None]:
    """Validate parsed JSON has required coding fields.

    Returns cleaned dict with required fields, or (None, error).
    """
    if not isinstance(parsed, dict):
        return None, "Parsed result is not a dict"

    label = parsed.get("label")
    if label not in valid_labels:
        return None, f"Invalid label: {label!r}, expected one of {valid_labels}"

    result = {
        "label": label,
        "confidence": _safe_float(parsed.get("confidence")),
        "rationale": str(parsed.get("rationale", "")),
        "evidence_span": str(parsed.get("evidence_span", "")),
        "uncertainty": str(parsed.get("uncertainty", "无")),
        "alternative_label": _safe_alt_label(parsed.get("alternative_label"), valid_labels),
        "why_not_alternative": str(parsed.get("why_not_alternative", "无")),
    }
    return result, None


def _safe_float(val: Any) -> float | None:
    """Safely convert to float or None."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _safe_alt_label(val: Any, valid_labels: tuple[str, ...]) -> str | None:
    """Validate alternative_label."""
    if val is None:
        return None
    s = str(val).strip()
    if s in valid_labels:
        return s
    return None
