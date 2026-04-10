from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
INGEST_FINDINGS = ROOT / "memory/mempalace-memory/scripts/ingest_findings.py"
EXPORT = ROOT / "memory/mempalace-memory/scripts/export_findings.py"
MEMPALACE_AVAILABLE = importlib.util.find_spec("mempalace") is not None


@unittest.skipUnless(MEMPALACE_AVAILABLE, "mempalace package is not installed in this test environment")
class ExportFindingsTests(unittest.TestCase):
    def test_export_findings_writes_expected_json_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            findings = tmp_path / "findings.md"
            findings.write_text(
                "## f1\n"
                "- dedup_key: repo:one\n"
                "- time: 2026-04-08T01:00:00+08:00\n"
                "- source: web_search\n"
                "- type: finding\n"
                "- title: Repo One\n"
                "- tags: [agents, memory]\n"
                "- score: 8\n"
                "- summary: Summary text\n"
                "- why_recommended: Why now\n"
                "- digest: >\n"
                "  Digest text\n"
                "- raw: https://example.com/repo-one\n",
                encoding="utf-8",
            )
            env = os.environ.copy()
            env["GTN_MEMPALACE_DATA_DIR"] = str(tmp_path / "data")
            env["GTN_MEMPALACE_IDENTITY_PATH"] = str(tmp_path / "identity.md")

            subprocess.run([sys.executable, str(INGEST_FINDINGS), str(findings)], check=True, env=env, cwd=ROOT)
            output = tmp_path / "memory-findings.json"
            subprocess.run([sys.executable, str(EXPORT), "--output", str(output)], check=True, env=env, cwd=ROOT)
            payload = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(len(payload), 1)
            item = payload[0]
            self.assertEqual(item["dedup_key"], "repo:one")
            self.assertEqual(item["title"], "Repo One")
            self.assertEqual(item["score"], 8)
            self.assertEqual(item["tags"], ["agents", "memory"])


if __name__ == "__main__":
    unittest.main()
