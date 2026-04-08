import json
import importlib.util
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


run_active_stack = load_module(ROOT / "runtime/codex-agent-loop/scripts/run_active_stack.py", "run_active_stack")


class BuildBriefingRunIdTests(unittest.TestCase):
    def test_build_briefing_accepts_explicit_run_id_and_dir(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            findings = tmp_path / "findings.json"
            wakeup = tmp_path / "memory-wakeup.txt"
            findings.write_text(
                json.dumps(
                    [
                        {
                            "entry_id": "x",
                            "dedup_key": "x",
                            "time": "2026-04-07T00:00:00+08:00",
                            "source": "web_search",
                            "title": "Example",
                            "tags": ["test"],
                            "score": 7,
                            "summary": "Summary",
                            "why_recommended": "Why",
                            "digest": "Digest",
                            "raw": "https://example.com",
                        }
                    ]
                ),
                encoding="utf-8",
            )
            wakeup.write_text("Wake-up text\n", encoding="utf-8")
            run_dir = tmp_path / "custom-run"
            subprocess.run(
                [
                    sys.executable,
                    "runtime/codex-agent-loop/scripts/build_briefing.py",
                    str(findings),
                    "--wakeup-path",
                    str(wakeup),
                    "--run-id",
                    "run-123",
                    "--run-dir",
                    str(run_dir),
                ],
                check=True,
            )
            payload = json.loads((run_dir / "briefing.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["run_id"], "run-123")
            self.assertEqual(payload["memory_wakeup"], "Wake-up text\n")

    def test_stack_run_output_dir_honors_stack_value(self) -> None:
        stack = {"run_output_dir": "custom-runs"}
        self.assertEqual(run_active_stack.stack_run_output_dir(stack), ROOT / "custom-runs")


if __name__ == "__main__":
    unittest.main()
