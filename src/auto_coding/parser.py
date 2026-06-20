"""Robust JSON parsing from LLM responses."""

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
        # Try repair on code block content
        repaired, ok = _repair_json(json_block)
        if ok and repaired:
            try:
                obj = json.loads(repaired)
                if isinstance(obj, dict):
                    return obj, None
            except json.JSONDecodeError:
                pass

    # Strategy 2b: extract ``` ... ``` (no language tag)
    generic_block = _extract_code_block(text, None)
    if generic_block:
        try:
            obj = json.loads(generic_block)
            if isinstance(obj, dict):
                return obj, None
        except json.JSONDecodeError:
            pass
        repaired, ok = _repair_json(generic_block)
        if ok and repaired:
            try:
                obj = json.loads(repaired)
                if isinstance(obj, dict):
                    return obj, None
            except json.JSONDecodeError:
                pass

    # Strategy 3: find first JSON object by brace matching
    obj = _find_first_json_object(text)
    if obj is not None:
        return obj, None

    # Strategy 4: repair the raw text directly
    repaired_raw, ok = _repair_json(text)
    if ok and repaired_raw:
        obj = _find_first_json_object(repaired_raw)
        if obj is not None:
            return obj, None

    return None, "Could not parse JSON from response"


def _repair_json(text: str) -> tuple[str | None, bool]:
    """Try to repair common LLM JSON errors.

    Handles:
      - Trailing commas before } or ]
      - Unescaped double quotes inside string values

    Returns (repaired_text, was_repaired). Returns (None, False) if unfixable.
    """
    repaired = text

    # Fix 1: trailing commas before } or ]
    fixed = re.sub(r",\s*([}\]])", r"\1", repaired)
    if fixed != repaired:
        repaired = fixed

    # Try parsing after comma fix
    try:
        json.loads(repaired)
        return repaired, (repaired != text)
    except json.JSONDecodeError:
        pass

    # Fix 2: unescaped double quotes in string values
    # Strategy: for each string value, scan for internal unescaped quotes
    # that look like LLM artifacts
    fixed_quotes = _fix_unescaped_quotes(repaired)
    if fixed_quotes != repaired:
        try:
            json.loads(fixed_quotes)
            return fixed_quotes, True
        except json.JSONDecodeError:
            pass

    # If we made any fix but still can't parse, return None
    if repaired != text:
        return None, False
    return None, False


def _fix_unescaped_quotes(text: str) -> str:
    """Fix unescaped double quotes inside JSON string values.

    Uses a heuristic: find key-value pairs where the string value
    contains what look like internal quotes (LLM quoting text),
    and escape them.
    """
    # Pattern: "key": "value with "unescaped" quotes"
    # We detect: after ": " a string value starts, and within that value
    # there are double-quote pairs that look like LLM quoting Chinese text.

    # Strategy: scan through the JSON, tracking whether we're inside
    # a string value, and look for patterns like 文字"文字  or  letter"letter
    # inside strings that suggest unescaped quotes.

    result = []
    i = 0
    in_key = False
    in_value = False
    value_start = -1
    depth = 0

    while i < len(text):
        ch = text[i]

        if ch == '"':
            if i > 0 and text[i - 1] == '\\':
                result.append(ch)
                i += 1
                continue

            if not in_key and not in_value:
                # Starting a key or value
                # Check context: what came before?
                before = text[max(0, i - 10):i].strip()
                if before.endswith(':') or before.endswith(':{'):
                    # This is a value start
                    in_value = True
                    value_start = i
                else:
                    in_key = True
                result.append(ch)
                i += 1
                continue

            if in_key:
                # Check if this closes the key (followed by :)
                rest = text[i + 1:i + 10].strip()
                if rest.startswith(':'):
                    in_key = False
                    result.append(ch)
                    i += 1
                    continue
                # Otherwise it might be part of a key — unlikely but keep going
                result.append(ch)
                i += 1
                continue

            if in_value:
                # This might close the value or be an unescaped internal quote
                rest = text[i + 1:i + 5].lstrip()
                if rest.startswith(',') or rest.startswith('}') or rest.startswith('\n'):
                    # This closes the value
                    in_value = False
                    result.append(ch)
                    i += 1
                    continue

                # Check: is this an unescaped internal quote?
                # Heuristic: if the character before is a letter/CJK char
                # and the character after is also a letter/CJK char,
                # it's likely an unescaped quote.
                prev_char = text[i - 1] if i > 0 else ''
                next_char = text[i + 1] if i + 1 < len(text) else ''

                prev_is_text = bool(prev_char) and (
                    prev_char.isalpha() or
                    ('一' <= prev_char <= '鿿') or
                    ('　' <= prev_char <= '〿')
                )
                next_is_text = bool(next_char) and (
                    next_char.isalpha() or
                    ('一' <= next_char <= '鿿') or
                    ('　' <= next_char <= '〿')
                )

                if prev_is_text or next_is_text:
                    # Escape this quote
                    result.append('\\')
                    result.append(ch)
                else:
                    result.append(ch)
                i += 1
                continue

        result.append(ch)
        i += 1

    return ''.join(result)


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
