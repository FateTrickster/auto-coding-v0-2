import json, tempfile
from pathlib import Path
from auto_coding.archive_manager import archive

class TestArchive:
    def test_generates_manifest(self):
        with tempfile.TemporaryDirectory() as d:
            b = Path(d)
            (b / "01_codebook").mkdir(parents=True)
            (b / "01_codebook" / "test.yaml").write_text("test")
            (b / "99_logs").mkdir(parents=True)
            r = archive(str(b))
            assert r["file_count"] >= 1
            with open(b / "99_logs" / "archive_manifest.json", encoding="utf-8") as f:
                m = json.load(f)
            assert len(m["files"]) >= 1
