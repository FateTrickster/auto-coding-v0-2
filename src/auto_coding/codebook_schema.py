"""Shared Codebook v0.1 Schema — single source of truth for field definitions."""

REQUIRED_FIELDS = [
    "code_id", "code_name", "definition",
    "inclusion_rules", "exclusion_rules",
    "typical_markers", "counter_markers",
    "positive_examples", "negative_examples",
    "boundary_cases", "low_information_rules", "notes",
]

STRING_FIELDS = {"code_id", "code_name"}
LIST_FIELDS = set(REQUIRED_FIELDS) - STRING_FIELDS
EXPECTED_CODE_IDS = ["IS1", "IS2", "IS3", "IS4"]

PROMPT_FIELDS = [
    ("definition", "定义"),
    ("inclusion_rules", "包含标准"),
    ("exclusion_rules", "排除标准"),
    ("typical_markers", "典型标记词"),
    ("counter_markers", "反例标记词"),
    ("positive_examples", "正例"),
    ("negative_examples", "反例"),
    ("boundary_cases", "与其他标签的边界"),
    ("low_information_rules", "低信息文本处理"),
    ("notes", "备注"),
]


def migrate_legacy_codebook(data: dict) -> dict:
    """Explicit migration for old-format codebooks. Call only when needed."""
    if not isinstance(data, dict): return data
    codes_in = data.get("codes", [])
    if not isinstance(codes_in, list): return data
    new_codes = []
    for c in codes_in:
        if not isinstance(c, dict): new_codes.append(c); continue
        nc = dict(c)
        if "label" in nc:
            nc["code_id"] = nc.pop("label")
        for f in REQUIRED_FIELDS:
            if f not in nc: nc[f] = c.get(f)
        if nc.get("code_id") is None: nc["code_id"] = "?"
        if nc.get("code_name") is None: nc["code_name"] = nc.get("code_id", "?")
        for lf in LIST_FIELDS:
            val = nc.get(lf)
            if val is None or (isinstance(val, list) and len(val) == 0):
                nc[lf] = ["(migrated)"]
            elif isinstance(val, str):
                nc[lf] = [val] if val.strip() else ["(migrated)"]
            elif not isinstance(val, list):
                nc[lf] = ["(migrated)"]
        new_codes.append(nc)
    result = dict(data); result["codes"] = new_codes
    if not result.get("version"): result["version"] = "v0.1"
    return result




def make_valid_code(cid: str = "IS1") -> dict:
    """Create a minimal valid code dict for the current Schema. For tests and bootstrapping."""
    return {
        "code_id": cid, "code_name": cid,
        "definition": [f"{cid} definition."],
        "inclusion_rules": [f"{cid} inclusion."],
        "exclusion_rules": [f"{cid} exclusion."],
        "typical_markers": [f"{cid} marker."],
        "counter_markers": [f"{cid} counter."],
        "positive_examples": [f"{cid} positive."],
        "negative_examples": [f"{cid} negative."],
        "boundary_cases": [f"{cid} boundary."],
        "low_information_rules": [f"{cid} low info."],
        "notes": [f"{cid} notes."],
    }


def validate_codebook_data(data: dict) -> list[str]:
    """Validate codebook YAML data structure. Returns list of error messages (empty = valid)."""
    errors = []

    if not isinstance(data, dict):
        errors.append("Root must be a mapping (dict)")
        return errors

    version = data.get("version")
    if not isinstance(version, str) or not version.strip():
        errors.append("version must be a non-empty string")

    codes_raw = data.get("codes")
    if codes_raw is None:
        errors.append("Missing 'codes' key")
    elif not isinstance(codes_raw, list):
        errors.append("'codes' must be a list")
    elif len(codes_raw) == 0:
        errors.append("'codes' is an empty list")
    else:
        for i, c in enumerate(codes_raw):
            if not isinstance(c, dict):
                errors.append(f"codes[{i}] is not a dict")

    if errors:
        return errors

    codes = codes_raw
    code_ids = [c.get("code_id") for c in codes]
    if len(set(code_ids)) != len(code_ids):
        errors.append("Duplicate code_id detected")
    missing = set(EXPECTED_CODE_IDS) - set(code_ids)
    extra = set(code_ids) - set(EXPECTED_CODE_IDS)
    if missing:
        errors.append(f"Missing code IDs: {sorted(missing)}")
    if extra:
        errors.append(f"Unknown code IDs: {sorted(extra)}")
    if code_ids != EXPECTED_CODE_IDS:
        errors.append(f"Code order wrong: expected {EXPECTED_CODE_IDS}, got {code_ids}")

    for code in codes:
        cid = code.get("code_id", "?")
        unknown = set(code.keys()) - set(REQUIRED_FIELDS)
        if unknown:
            errors.append(f"{cid}: unknown fields: {sorted(unknown)}")

        for sf in STRING_FIELDS:
            val = code.get(sf)
            if not isinstance(val, str) or not val.strip():
                errors.append(f"{cid}.{sf} must be a non-empty string")

        for lf in LIST_FIELDS:
            val = code.get(lf)
            if not isinstance(val, list):
                errors.append(f"{cid}.{lf} must be a list, got {type(val).__name__}")
            elif len(val) == 0:
                errors.append(f"{cid}.{lf} is an empty list")
            else:
                for j, item in enumerate(val):
                    if not isinstance(item, str) or not item.strip():
                        errors.append(f"{cid}.{lf}[{j}] is not a non-empty string")

    return errors
