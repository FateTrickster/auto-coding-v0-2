"""Phase 1 — Render validated codebook YAML into CoderAgent system prompt.

Uses shared codebook_schema.py. Atomic writes, strict validation, version check.
"""

from __future__ import annotations

import os, tempfile
from pathlib import Path

import yaml

from .codebook_schema import (
    EXPECTED_CODE_IDS, PROMPT_FIELDS, validate_codebook_data,
)


class RenderError(Exception):
    """Raised on invalid codebook YAML or rendering failure."""


def render(codebook_yaml_path: str | Path, out_dir: str | Path,
           expected_version: str | None = None) -> dict:
    """Render codebook YAML → coder_prompt_{version}.md with atomic write."""
    yaml_path = Path(codebook_yaml_path)
    out_dir = Path(out_dir); out_dir.mkdir(parents=True, exist_ok=True)

    # Load
    try:
        with open(yaml_path, "r", encoding="utf-8") as f: data = yaml.safe_load(f)
    except Exception as e: raise RenderError(f"YAML parse error: {e}")

    # Strict validation — no auto-normalize
    errs = validate_codebook_data(data)
    if errs: raise RenderError("; ".join(errs))

    version = data["version"]
    if expected_version is not None and version != expected_version:
        raise RenderError(f"Expected version {expected_version}, YAML version is {version}")

    codes = data["codes"]
    lines = _build_prompt(codes, version)

    # Atomic write: tmp → final
    final_path = out_dir / f"coder_prompt_{version}.md"
    tmp_fd, tmp_path = tempfile.mkstemp(suffix=".md.tmp", dir=str(out_dir))
    try:
        with os.fdopen(tmp_fd, "w", encoding="utf-8") as f: f.write("\n".join(lines))
        os.replace(tmp_path, str(final_path))
    except Exception:
        if os.path.exists(tmp_path): os.unlink(tmp_path)
        raise

    return {"prompt_path": str(final_path), "code_count": len(codes)}


def _build_prompt(codes: list[dict], version: str) -> list[str]:
    lines = [
        "# 角色",
        "",
        "你是独立编码员。你将在后续用户消息中收到一个编码单元及其 unit_id。",
        "",
        "# 编码任务",
        "",
        "请严格依据当前 codebook 对编码单元进行编码。",
        "",
        "# 当前 codebook 版本",
        "",
        version,
        "",
        "# 代码列表",
        "",
    ]
    for code in codes:
        cid = code.get("code_id", "?"); cname = code.get("code_name", "?")
        lines.append(f"## {cid} {cname}"); lines.append("")
        for en_key, zh_label in PROMPT_FIELDS:
            items = code.get(en_key, [])
            lines.append(f"**{zh_label}**:")
            for item in items: lines.append(f"- {item}")
            lines.append("")
        lines.append("---"); lines.append("")

    labels_str = ", ".join(EXPECTED_CODE_IDS)
    lines += [
        "# 编码决策顺序",
        "",
        "请按以下顺序逐层判断：",
        "1. 阅读定义；2. 检查包含标准；3. 检查排除标准；",
        "4. 检查与其他标签的边界；5. 参考典型/反例标记词（仅是证据）；",
        "6. 参考正例/反例；7. 低信息文本用低信息规则；8. 确定唯一 primary_code。",
        "",
        "排除标准和边界规则优先于标记词。不能仅凭单个关键词编码。",
        "备注仅辅助理解，与正式规则冲突时以正式规则为准。",
        "",
        "# 编码要求",
        "",
        "1. 只依据当前 codebook；2. 不新增标签；3. 不修改 codebook；",
        "4. 只输出一个合法 JSON 对象，不要 Markdown 代码块或解释文字；",
        "5. 必须给出 evidence_span（原文连续片段，不得改写或概括）；",
        "6. 必须给出 reason（引用定义/包含/排除/边界规则）；",
        "7. 不确定时 uncertain=true；8. 不参考另一个编码员结果。",
        "",
        "# 输出 JSON",
        "",
        "{",
        f'  "primary_code": "{"/".join(EXPECTED_CODE_IDS)}",',
        '  "secondary_code": null,',
        '  "confidence": 0.92,',
        '  "evidence_span": "原文连续片段",',
        '  "reason": "判断理由",',
        '  "uncertain": false,',
        '  "needs_discussion": false',
        "}",
        "",
        "# 字段说明",
        f"- primary_code: 必须为 {labels_str} 之一。",
        "- secondary_code: 必须为 null（本任务为单标签编码）。",
        "- confidence: 0.0-1.0，保留两位小数。",
        "- evidence_span: 原文连续片段，不改写、不概括、不凭空生成。",
        "- reason: 简明判断依据，引用定义和规则。",
        "- uncertain: 证据不足或多标签边界接近时为 true，否则 false。",
        "- needs_discussion: 规则无法唯一解决或需要人工裁决时为 true。",
        "  （与 uncertain 不同：uncertain=自身置信不足，needs_discussion=需要后续讨论或人工复核）。",
        "",
        "# 有效标签",
        "",
        labels_str,
        "",
        "请只使用以上标签。不要创造新标签。",
    ]
    return lines
