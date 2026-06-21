"""Phase 1 — Strict line-by-line state machine parser for initial_codebook.md.

Only supports the standardized 10-field format. No table/form C/fallback parsing.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml

FIELD_MAP = {
    "定义": "definition",
    "包含标准": "inclusion_rules",
    "排除标准": "exclusion_rules",
    "典型标记词": "typical_markers",
    "反例标记词": "counter_markers",
    "正例": "positive_examples",
    "反例": "negative_examples",
    "与其他标签的边界": "boundary_cases",
    "低信息文本处理": "low_information_rules",
    "备注": "notes",
}

LABEL_ORDER = ["IS1", "IS2", "IS3", "IS4"]
FIELD_ORDER = list(FIELD_MAP.keys())

RE_LABEL = re.compile(r"^##[ \t]+(IS1|IS2|IS3|IS4)[ \t]+(.+?)\s*$")
RE_FIELD = re.compile(r"^\*\*(定义|包含标准|排除标准|典型标记词|反例标记词|正例|反例|与其他标签的边界|低信息文本处理|备注)\*\*:[ \t]*$")
RE_LIST_ITEM = re.compile(r"^[ \t]*-[ \t]+(.+?)\s*$")
RE_CONTINUATION = re.compile(r"^[ \t]{2,}(.+?)\s*$")


class ParseError(Exception):
    def __init__(self, msg: str, line_no: int = 0, line_text: str = ""):
        self.line_no = line_no
        self.line_text = line_text
        super().__init__(f"Line {line_no}: {msg}" + (f" [{line_text[:80]}]" if line_text else ""))


def _validate_label_complete(code: dict, line_no: int) -> None:
    """Verify a label has exactly all 10 fields in order, each non-empty."""
    for fn in FIELD_ORDER:
        fk = FIELD_MAP[fn]
        if fk not in code:
            raise ParseError(f"Missing field {fn} in {code['code_id']}", line_no)
        if not isinstance(code[fk], list) or len(code[fk]) == 0:
            raise ParseError(f"Empty field {fn} in {code['code_id']}", line_no)


def parse_markdown_codebook(text: str) -> list[dict]:
    """Parse standardized initial_codebook.md into a list of code dicts using a state machine."""
    lines = text.split("\n")
    codes: list[dict] = []
    current_code: dict | None = None
    current_field: str | None = None
    last_item: str | None = None
    seen_fields: set[str] = set()
    next_expected: int = 0
    in_appendix = False

    for line_no, raw_line in enumerate(lines, 1):
        line = raw_line.rstrip()
        stripped = line.strip()

        # Detect appendix start
        if stripped.startswith("# 附录"):
            in_appendix = True
            if current_code is not None and current_field is not None:
                # Finalize the last field's items
                pass
            continue
        if in_appendix:
            # Check for bogus IS labels in appendix
            if re.match(r"^##\s+IS\d", stripped):
                raise ParseError("IS label found in appendix section", line_no, stripped)
            continue

        # Skip blank lines, separators, blockquote, top-level headings
        if not stripped or stripped == "---" or stripped.startswith(">") or stripped.startswith("# "):
            continue

        # Label header
        label_m = RE_LABEL.match(stripped)
        if label_m:
            code_id = label_m.group(1)
            code_name = label_m.group(2).strip()
            expected_id = LABEL_ORDER[len(codes)] if len(codes) < 4 else None
            if code_id != expected_id:
                raise ParseError(
                    f"Expected label {expected_id}, got {code_id}", line_no, stripped)
            if len(codes) >= 4:
                raise ParseError("More than 4 labels found", line_no, stripped)

            # Validate previous label had all 10 fields
            if current_code is not None:
                _validate_label_complete(current_code, line_no)

            current_code = {
                "code_id": code_id, "code_name": code_name, "definition": [],
                "inclusion_rules": [], "exclusion_rules": [],
                "typical_markers": [], "counter_markers": [],
                "positive_examples": [], "negative_examples": [],
                "boundary_cases": [], "low_information_rules": [], "notes": [],
            }
            current_field = None
            last_item = None
            seen_fields = set()
            next_expected = 0
            codes.append(current_code)
            continue

        # Field header
        field_m = RE_FIELD.match(stripped)
        if field_m:
            if current_code is None:
                raise ParseError("Field outside any label section", line_no, stripped)
            field_name = field_m.group(1)
            if field_name not in FIELD_MAP:
                raise ParseError(f"Unknown field: {field_name}", line_no, stripped)
            # Duplicate check
            if field_name in seen_fields:
                raise ParseError(
                    f"Duplicate field '{field_name}' (previously seen in this label)",
                    line_no, stripped,
                )
            seen_fields.add(field_name)
            # Order check
            expected = FIELD_ORDER[next_expected] if next_expected < len(FIELD_ORDER) else None
            if field_name != expected:
                raise ParseError(
                    f"Expected field '{expected}', got '{field_name}'",
                    line_no, stripped,
                )
            next_expected += 1
            current_field = field_name
            last_item = None
            continue

        # List item
        item_m = RE_LIST_ITEM.match(line)
        if item_m:
            if current_code is None or current_field is None:
                raise ParseError("List item outside label/field", line_no, stripped)
            content = item_m.group(1)
            field_key = FIELD_MAP[current_field]
            current_code[field_key].append(content)
            last_item = content
            continue

        # Continuation line
        cont_m = RE_CONTINUATION.match(line)
        if cont_m:
            if last_item is None:
                raise ParseError("Continuation without preceding list item", line_no, stripped)
            # Append continuation to the last item
            field_key = FIELD_MAP[current_field]
            if current_code[field_key]:
                current_code[field_key][-1] += " " + cont_m.group(1).strip()
            continue

        # Anything else is unexpected
        raise ParseError(f"Unexpected content outside field", line_no, stripped)

    # Validate last label completeness
    if current_code is not None:
        _validate_label_complete(current_code, len(lines))

    if len(codes) != 4:
        raise ParseError(f"Expected 4 labels, found {len(codes)}")
    for code in codes:
        for fn in FIELD_ORDER:
            fk = FIELD_MAP[fn]
            if fk not in code:
                raise ParseError(f"Missing field {fn} in {code['code_id']}")
            if len(code[fk]) == 0:
                raise ParseError(f"Empty field {fn} in {code['code_id']}")

    return codes


def standardize(initial_codebook_path: str | Path, out_dir: str | Path, version: str = "v0.1") -> dict:
    """Full standardize pipeline: read -> parse -> save YAML.

    Writes to .tmp first, atomically replaces on success.
    """
    text = Path(initial_codebook_path).read_text(encoding="utf-8")
    codes = parse_markdown_codebook(text)

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    yaml_path = out_dir / f"codebook_{version}.yaml"
    tmp_path = out_dir / f"codebook_{version}.yaml.tmp"

    data = {"version": version, "source_file": str(initial_codebook_path), "codes": codes}
    with open(tmp_path, "w", encoding="utf-8") as f:
        yaml.dump(data, f, allow_unicode=True, default_flow_style=False, sort_keys=False)

    # Atomic replace
    tmp_path.replace(yaml_path)

    # Render Markdown
    md_path = out_dir / f"codebook_{version}.md"
    save_codebook_markdown(codes, version, md_path)

    return {"yaml_path": str(yaml_path), "code_count": len(codes), "version": version,
            "md_path": str(md_path)}


def save_codebook_markdown(codes: list[dict], version: str, path: str | Path) -> None:
    """Render structured codebook back to human-readable Markdown.

    Outputs all 10 fields per label in FIELD_ORDER.
    Preserves all list items in original order.
    """
    lines = [f"# Codebook {version}", "", f"Source: standardized from initial_codebook.md", ""]
    FIELD_LABELS_ZH = [
        ("定义", "definition"),
        ("包含标准", "inclusion_rules"),
        ("排除标准", "exclusion_rules"),
        ("典型标记词", "typical_markers"),
        ("反例标记词", "counter_markers"),
        ("正例", "positive_examples"),
        ("反例", "negative_examples"),
        ("与其他标签的边界", "boundary_cases"),
        ("低信息文本处理", "low_information_rules"),
        ("备注", "notes"),
    ]
    for code in codes:
        cid = code.get("code_id", "?")
        cname = code.get("code_name", "?")
        lines.append(f"## {cid} {cname}")
        lines.append("")
        for zh_label, en_key in FIELD_LABELS_ZH:
            items = code.get(en_key, [])
            lines.append(f"**{zh_label}**:")
            if items:
                for item in items:
                    lines.append(f"- {item}")
            lines.append("")
        lines.append("---")
        lines.append("")
    Path(path).write_text("\n".join(lines), encoding="utf-8")
