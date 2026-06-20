"""File I/O utilities."""

from __future__ import annotations

import json
from pathlib import Path


def read_jsonl(path: str | Path) -> list[dict]:
    """Read a JSONL file into a list of dicts."""
    items = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                items.append(json.loads(line))
    return items


def write_jsonl(path: str | Path, items: list[dict]) -> None:
    """Write a list of dicts to a JSONL file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for item in items:
            f.write(json.dumps(item, ensure_ascii=False) + "\n")


def write_json(path: str | Path, data: dict | list) -> None:
    """Write to a JSON file."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def ensure_dir(path: str | Path) -> Path:
    """Ensure a directory exists; return Path."""
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p
