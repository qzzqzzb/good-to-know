from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

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
    def _seed_memory_artifacts(self, run_dir: Path) -> dict[str, Path]:
        wakeup_path = run_dir / "memory-wakeup.txt"
        findings_path = run_dir / "memory-findings.json"
        wakeup_text = "I build local-first AI tools.\nRuntime finding\n"
        findings_payload = [
            {
                "entry_id": "finding-1",
                "dedup_key": "finding:1",
                "time": "2026-04-08T10:00:00+08:00",
                "source": "web_search",
                "title": "Runtime finding",
                "tags": ["memory"],
                "score": 9,
                "summary": "Runtime summary.",
                "why_recommended": "Needed for wake-up quality.",
                "digest": "Runtime digest.",
                "raw": "https://example.com/runtime",
            }
        ]
        wakeup_path.write_text(wakeup_text, encoding="utf-8")
        findings_path.write_text(json.dumps(findings_payload), encoding="utf-8")
        return {"wakeup": wakeup_path, "findings": findings_path}

    def test_build_outputs_writes_and_uses_memory_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            run_dir = tmp_path / "run-123"
            stack = {"memory_skill": "memory/mempalace-memory", "output_skills": [], "run_output_dir": "runs"}
            with patch.object(run_active_stack, "build_memory_artifacts", side_effect=lambda stack, dest: self._seed_memory_artifacts(dest)):
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

    def test_build_outputs_generates_payloads_for_multiple_output_skills(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)

            run_dir = tmp_path / "run-payloads"
            stack = {
                "memory_skill": "memory/mempalace-memory",
                "output_skills": ["output/notion-briefing", "output/feishu-briefing"],
                "run_output_dir": "runs",
            }

            with patch.object(run_active_stack, "build_memory_artifacts", side_effect=lambda stack, dest: self._seed_memory_artifacts(dest)):
                run_active_stack.build_outputs(stack, run_id="run-payloads", run_dir=run_dir)

            self.assertTrue((run_dir / "notion-payload.json").exists())
            self.assertTrue((run_dir / "feishu-payload.json").exists())


if __name__ == "__main__":
    unittest.main()
