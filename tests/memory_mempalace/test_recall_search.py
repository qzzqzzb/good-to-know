from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.memory_mempalace.helpers import load_memory_module


class RecallSearchTests(unittest.TestCase):
    def test_recall_and_search_delegate_to_upstream_stack(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_memory_module(tmp_path, name="mempalace_memory_recall_search")
            findings = tmp_path / "findings.md"
            findings.write_text(
                "## finding-1\n"
                "- dedup_key: find:1\n"
                "- time: 2026-04-08T12:00:00+08:00\n"
                "- source: web_search\n"
                "- type: finding\n"
                "- title: Room filtered finding\n"
                "- tags: [memory, runtime]\n"
                "- score: 9\n"
                "- summary: This note proves search and recall work.\n"
                "- why_recommended: >\n"
                "  Needed for phase 1.5 verification.\n"
                "- digest: >\n"
                "  Search digest.\n"
                "- raw: https://example.com/search\n",
                encoding="utf-8",
            )
            module.ingest_outbox(findings, bucket="findings")

            recall_text = module.build_recall_text(wing="gtn", room="memory", n_results=5)
            search_text = module.build_search_text("phase 1.5 verification", wing="gtn", room="memory", n_results=5)

            self.assertIn("Room filtered finding", recall_text)
            self.assertIn("SEARCH RESULTS", search_text)
            self.assertIn("Room filtered finding", search_text)


if __name__ == "__main__":
    unittest.main()
