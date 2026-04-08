from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST_FINDINGS = ROOT / "memory/mempalace-memory/scripts/ingest_findings.py"
WAKEUP = ROOT / "memory/mempalace-memory/scripts/read_wakeup.py"
STATUS = ROOT / "memory/mempalace-memory/scripts/status.py"


class WakeupAndStatusTests(unittest.TestCase):
    def test_empty_wakeup_and_status_use_repo_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            env = os.environ.copy()
            env["GTN_MEMPALACE_DATA_DIR"] = str(tmp_path / "data")
            env["GTN_MEMPALACE_IDENTITY_PATH"] = str(tmp_path / "identity.md")

            wakeup_text = subprocess.check_output(
                [sys.executable, str(WAKEUP)], env=env, cwd=ROOT, text=True
            )
            self.assertIn("No stored memories yet", wakeup_text)

            status_payload = json.loads(
                subprocess.check_output([sys.executable, str(STATUS)], env=env, cwd=ROOT, text=True)
            )
            self.assertEqual(status_payload["total_entries"], 0)
            self.assertEqual(Path(status_payload["palace_dir"]), (tmp_path / "data" / "palace").resolve())
            self.assertNotIn(".mempalace", status_payload["palace_dir"])

    def test_seeded_wakeup_includes_top_memory(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            findings = tmp_path / "findings.md"
            findings.write_text(
                "## f1\n"
                "- dedup_key: f:1\n"
                "- time: 2026-04-08T01:00:00+08:00\n"
                "- source: web_search\n"
                "- type: finding\n"
                "- title: Strong finding\n"
                "- tags: [memory]\n"
                "- score: 9\n"
                "- summary: This is important memory.\n"
                "- why_recommended: Because it matters now.\n"
                "- digest: >\n"
                "  Long digest.\n"
                "- raw: https://example.com/f1\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["GTN_MEMPALACE_DATA_DIR"] = str(tmp_path / "data")
            env["GTN_MEMPALACE_IDENTITY_PATH"] = str(tmp_path / "identity.md")

            subprocess.run([sys.executable, str(INGEST_FINDINGS), str(findings)], check=True, env=env, cwd=ROOT)
            wakeup_text = subprocess.check_output(
                [sys.executable, str(WAKEUP)], env=env, cwd=ROOT, text=True
            )
            self.assertIn("Strong finding", wakeup_text)
            self.assertIn("This is important memory", wakeup_text)


if __name__ == "__main__":
    unittest.main()
