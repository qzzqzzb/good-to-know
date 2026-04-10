from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

from tests.memory_mempalace.helpers import load_memory_module
MEMPALACE_AVAILABLE = importlib.util.find_spec("mempalace") is not None


@unittest.skipUnless(MEMPALACE_AVAILABLE, "mempalace package is not installed in this test environment")
class MemoryModuleTests(unittest.TestCase):
    def test_ingest_context_and_wakeup_from_empty_and_seeded_palace(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_memory_module(tmp_path, name="mempalace_memory_module_ctx")

            empty_wakeup = module.build_wakeup_text()
            self.assertIn("No stored memories yet", empty_wakeup)

            outbox = tmp_path / "context-outbox.md"
            outbox.write_text(
                "## ctx-1\n"
                "- dedup_key: ctx:1\n"
                "- time: 2026-04-08T10:00:00+08:00\n"
                "- source: browser_history\n"
                "- type: user_signal\n"
                "- title: Browsed memory system ideas\n"
                "- summary: Looked at memory system notes.\n"
                "- raw: https://example.com/context\n",
                encoding="utf-8",
            )

            imported = module.ingest_outbox(outbox, bucket="context")
            self.assertEqual(imported, 1)

            seeded_wakeup = module.build_wakeup_text()
            self.assertIn("Browsed memory system ideas", seeded_wakeup)
            self.assertIn("Looked at memory system notes", seeded_wakeup)

    def test_findings_export_is_json_and_deduplicated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_memory_module(tmp_path, name="mempalace_memory_module_findings")
            outbox = tmp_path / "findings-outbox.md"
            outbox.write_text(
                "## finding-1\n"
                "- dedup_key: finding:1\n"
                "- time: 2026-04-08T10:00:00+08:00\n"
                "- source: web_search\n"
                "- type: finding\n"
                "- title: Example finding\n"
                "- tags: [memory, agents]\n"
                "- score: 8\n"
                "- summary: Short summary.\n"
                "- why_recommended: >\n"
                "  Because it improves retrieval.\n"
                "- digest: >\n"
                "  Longer digest.\n"
                "- raw: https://example.com/finding\n",
                encoding="utf-8",
            )

            module.ingest_outbox(outbox, bucket="findings")
            module.ingest_outbox(outbox, bucket="findings")
            payload = module.export_findings_payload()

            self.assertEqual(len(payload), 1)
            self.assertEqual(payload[0]["title"], "Example finding")
            self.assertEqual(payload[0]["tags"], ["memory", "agents"])
            self.assertEqual(payload[0]["score"], 8)

    def test_status_reports_repo_local_paths(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            module = load_memory_module(tmp_path, name="mempalace_memory_module_status")
            module.record_user_profile("I care about agents and product design.")
            status = module.status_payload()

            self.assertEqual(Path(status["palace_dir"]).resolve(), (tmp_path / "module-data" / "palace").resolve())
            self.assertEqual(Path(status["identity_path"]).resolve(), (tmp_path / "identity.md").resolve())
            self.assertEqual(status["counts_by_bucket"]["context"], 1)
            self.assertNotIn("/.mempalace/", json.dumps(status))


if __name__ == "__main__":
    unittest.main()
