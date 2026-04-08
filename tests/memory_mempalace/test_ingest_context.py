from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "memory/mempalace-memory/scripts/ingest_context.py"
STATUS_SCRIPT = ROOT / "memory/mempalace-memory/scripts/status.py"
EXPORT_SCRIPT = ROOT / "memory/mempalace-memory/scripts/export_findings.py"


class IngestContextTests(unittest.TestCase):
    def test_ingest_context_imports_records_without_duplicates(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            outbox = tmp_path / "context.md"
            outbox.write_text(
                "## ctx-1\n"
                "- dedup_key: ctx:1\n"
                "- time: 2026-04-08T00:00:00+08:00\n"
                "- source: browser_history\n"
                "- type: user_signal\n"
                "- title: Context item\n"
                "- tags: [ctx]\n"
                "- summary: First context record\n"
                "- raw: https://example.com\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["GTN_MEMPALACE_DATA_DIR"] = str(tmp_path / "data")
            env["GTN_MEMPALACE_IDENTITY_PATH"] = str(tmp_path / "identity.md")

            subprocess.run([sys.executable, str(SCRIPT), str(outbox)], check=True, env=env, cwd=ROOT)
            subprocess.run([sys.executable, str(SCRIPT), str(outbox)], check=True, env=env, cwd=ROOT)

            status_json = subprocess.check_output(
                [sys.executable, str(STATUS_SCRIPT)], env=env, cwd=ROOT, text=True
            )
            status = json.loads(status_json)
            self.assertEqual(status["total_entries"], 1)
            self.assertEqual(status["counts_by_bucket"].get("context"), 1)

            export_json = subprocess.check_output(
                [sys.executable, str(EXPORT_SCRIPT)], env=env, cwd=ROOT, text=True
            )
            self.assertEqual(json.loads(export_json), [])


if __name__ == "__main__":
    unittest.main()
