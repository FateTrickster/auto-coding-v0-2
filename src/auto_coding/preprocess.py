"""Preprocess Raw CSV data into JSONL coding inputs."""

from __future__ import annotations

import csv
import os
import re
from pathlib import Path

from .schemas import CodingInput, ContextMessage


def _extract_group_id(filepath: str | Path) -> str:
    """Extract gNN from a filename like '5.csv' or '/path/5.csv'."""
    name = Path(filepath).stem  # "5"
    # If there's a number, use it
    m = re.search(r"(\d+)", name)
    if m:
        return f"g{int(m.group(1)):02d}"
    # fallback: use filename stem
    return name


def _normalize_speaker(row: dict) -> str:
    """Return a human-readable speaker name."""
    name = row.get("sender_name", "").strip()
    if name:
        return name
    role = row.get("agent_role", "").strip()
    if role:
        return f"agent-{role}"
    return row.get("sender_username", "unknown")


def _is_student(row: dict) -> bool:
    """Check if sender_type indicates a student."""
    st = (row.get("sender_type") or "").lower()
    return "student" in st


def _is_agent(row: dict) -> bool:
    """Check if sender_type indicates an agent."""
    st = (row.get("sender_type") or "").lower()
    return "agent" in st


def load_csv_files(raw_dir: str | Path) -> list[dict]:
    """Load all CSV files from raw_dir, returning raw rows with source_file info.

    Handles two layouts:
      - raw_dir/Multi_messages_1-18/*.csv  (nested)
      - raw_dir/*.csv                       (flat)
    """
    raw_path = Path(raw_dir)
    csv_files: list[Path] = []

    # Check for nested directory first
    for item in raw_path.iterdir():
        if item.is_dir() and item.name.lower().startswith("multi"):
            csv_files = sorted(item.glob("*.csv"), key=lambda p: _sort_key(p))
            break
    else:
        # Flat: look directly
        csv_files = sorted(raw_path.glob("*.csv"), key=lambda p: _sort_key(p))

    if not csv_files:
        raise FileNotFoundError(f"No CSV files found in {raw_dir}")

    all_rows: list[dict] = []
    for fp in csv_files:
        group_id = _extract_group_id(fp)
        with open(fp, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                row["_group_id"] = group_id
                row["_source_file"] = str(fp)
                all_rows.append(row)

    return all_rows


def _sort_key(p: Path) -> int:
    """Sort by numeric prefix in filename."""
    nums = re.findall(r"\d+", p.stem)
    return int(nums[0]) if nums else 0


def preprocess(raw_dir: str | Path) -> tuple[list[dict], dict]:
    """Preprocess Raw CSV data.

    Returns:
        (coding_input_dicts, summary_stats)
    """
    raw_rows = load_csv_files(raw_dir)

    # 1. Collect all messages per group, with turn indices
    group_messages: dict[str, list[dict]] = {}
    for row in raw_rows:
        gid = row["_group_id"]
        group_messages.setdefault(gid, []).append(row)

    # 2. Sort each group by created_at, assign turn_index
    for gid, msgs in group_messages.items():
        msgs.sort(key=lambda r: r.get("created_at", ""))
        for ti, m in enumerate(msgs, start=1):
            m["_turn_index"] = ti
            m["_id"] = f"{gid}_t{ti:04d}"

    # 3. Build all messages (for context)
    all_messages: dict[str, list[dict]] = {}
    for gid, msgs in group_messages.items():
        all_messages[gid] = msgs

    coding_targets: list[dict] = []
    stats = {
        "total_raw_rows": len(raw_rows),
        "total_student_messages": 0,
        "total_agent_messages": 0,
        "filtered_empty_content": 0,
        "final_coding_targets": 0,
        "low_information_candidates": 0,
        "by_group": {},
    }

    for gid, msgs in all_messages.items():
        group_stats = {"student": 0, "agent": 0, "coding_targets": 0}
        for m in msgs:
            if _is_student(m):
                group_stats["student"] += 1
            elif _is_agent(m):
                group_stats["agent"] += 1

        stats["total_student_messages"] += group_stats["student"]
        stats["total_agent_messages"] += group_stats["agent"]

        # Build coding targets (only student, non-empty content)
        for mi, m in enumerate(msgs):
            if not _is_student(m):
                continue

            content = (m.get("content") or "").strip()
            if not content:
                stats["filtered_empty_content"] += 1
                continue

            # Build context: previous 3 messages
            turn_idx = m["_turn_index"]
            prev_msgs = []
            for pm in msgs:
                if pm["_turn_index"] < turn_idx:
                    prev_msgs.append(pm)
            prev_msgs = prev_msgs[-3:]  # last 3

            prev_context = []
            for pm in prev_msgs:
                p_content = (pm.get("content") or "")[:300]
                prev_context.append({
                    "speaker": _normalize_speaker(pm),
                    "sender_type": "student" if _is_student(pm) else "agent",
                    "content": p_content,
                })

            low_info = len(content) <= 5

            target = {
                "id": m["_id"],
                "group_id": gid,
                "turn_index": turn_idx,
                "created_at": m.get("created_at", ""),
                "speaker": _normalize_speaker(m),
                "sender_type": "student",
                "content": content,
                "previous_3_messages": prev_context,
                "low_information_candidate": low_info,
            }
            coding_targets.append(target)

            if low_info:
                stats["low_information_candidates"] += 1
            group_stats["coding_targets"] += 1

        stats["by_group"][gid] = group_stats

    stats["final_coding_targets"] = len(coding_targets)

    return coding_targets, stats
