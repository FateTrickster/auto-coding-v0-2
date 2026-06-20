"""Phase 7 — ArchiveManager: generate archive manifest."""

from __future__ import annotations

import hashlib, json, os
from datetime import datetime
from pathlib import Path


def archive(project_dir: str | Path) -> dict:
    project_dir = Path(project_dir)
    out = project_dir / "99_logs"
    out.mkdir(parents=True, exist_ok=True)

    key_dirs = ["00_inputs", "01_codebook", "02_prompts", "03_training",
                "04_pilot", "06_formal_coding", "07_final", "99_logs"]
    manifest = {"archive_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "project_dir": str(project_dir), "files": []}

    for dn in key_dirs:
        d = project_dir / dn
        if not d.exists(): continue
        for fp in sorted(d.rglob("*")):
            if fp.is_file() and "__pycache__" not in str(fp):
                try:
                    st = fp.stat()
                    h = hashlib.sha256(fp.read_bytes()).hexdigest()[:16]
                    manifest["files"].append({
                        "path": str(fp.relative_to(project_dir)),
                        "size": st.st_size,
                        "mtime": st.st_mtime,
                        "sha256_short": h,
                    })
                except Exception: pass

    with open(out / "archive_manifest.json", "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)
    return {"file_count": len(manifest["files"])}
