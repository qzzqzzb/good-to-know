from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path

from tests.memory_mempalace.helpers import load_memory_module

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_active_stack = load_module(
    ROOT / "runtime/codex-agent-loop/scripts/run_active_stack.py",
    "run_active_stack_mempalace",
)


class RunActiveStackMempalaceTests(unittest.TestCase):
    def test_build_outputs_writes_and_uses_memory_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memory_module = load_memory_module(tmp_path, name="mempalace_memory_runtime")
            findings_outbox = tmp_path / "findings-outbox.md"
            findings_outbox.write_text(
                "## finding-1\n"
                "- dedup_key: finding:1\n"
                "- time: 2026-04-08T10:00:00+08:00\n"
                "- source: web_search\n"
                "- type: finding\n"
                "- title: Runtime finding\n"
                "- tags: [memory]\n"
                "- score: 9\n"
                "- summary: Runtime summary.\n"
                "- why_recommended: >\n"
                "  Needed for wake-up quality.\n"
                "- digest: >\n"
                "  Runtime digest.\n"
                "- raw: https://example.com/runtime\n",
                encoding="utf-8",
            )
            memory_module.record_user_profile("I build local-first AI tools.")
            memory_module.ingest_outbox(findings_outbox, bucket="findings")

            run_dir = tmp_path / "run-123"
            stack = {"memory_skill": "memory/mempalace-memory", "output_skills": [], "run_output_dir": "runs"}
            output_dir = run_active_stack.build_outputs(stack, run_id="run-123", run_dir=run_dir)

            self.assertEqual(output_dir.resolve(), run_dir.resolve())
            wakeup_path = run_dir / "memory-wakeup.txt"
            findings_path = run_dir / "memory-findings.json"
            briefing_path = run_dir / "briefing.json"
            self.assertTrue(wakeup_path.exists())
            self.assertTrue(findings_path.exists())
            self.assertTrue(briefing_path.exists())

            wakeup_text = wakeup_path.read_text(encoding="utf-8")
            self.assertIn("I build local-first AI tools.", wakeup_text)
            self.assertIn("Runtime finding", wakeup_text)

            findings_payload = json.loads(findings_path.read_text(encoding="utf-8"))
            self.assertEqual(findings_payload[0]["title"], "Runtime finding")

            briefing_payload = json.loads(briefing_path.read_text(encoding="utf-8"))
            self.assertEqual(briefing_payload["run_id"], "run-123")
            self.assertEqual(briefing_payload["memory_wakeup"], wakeup_text)
            self.assertEqual(briefing_payload["items"][0]["title"], "Runtime finding")


if __name__ == "__main__":
    unittest.main()
