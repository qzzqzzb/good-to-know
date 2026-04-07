from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from runtime.gtn_local_product.models import StateData
from runtime.gtn_local_product.paths import resolve_paths
from runtime.gtn_local_product.runner import build_codex_command, run_once


class RunnerTests(unittest.TestCase):
    def test_build_codex_command_uses_workspace_write_and_app_run_dir(self) -> None:
        cmd = build_codex_command(Path("/usr/local/bin/codex"), Path("/tmp/runtime"), Path("/tmp/app-run"), Path("/tmp/app-run/last-message.txt"))
        self.assertIn("--sandbox", cmd)
        self.assertIn("workspace-write", cmd)
        self.assertIn("--add-dir", cmd)
        self.assertIn("/tmp/app-run", cmd)

    def test_run_once_records_failed_result_on_unexpected_runner_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (runtime_repo / "output" / "notion-briefing").mkdir(parents=True)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text("{}", encoding="utf-8")

            paths = resolve_paths(root=root, runtime_dir=runtime_repo)
            state = StateData(runtime_repo_path=str(runtime_repo), codex_path="/bin/echo")

            def boom(*args, **kwargs):
                raise OSError("boom")

            with (
                patch("runtime.gtn_local_product.runner.ensure_codex_auth"),
                patch("runtime.gtn_local_product.runner.ensure_search_capability"),
                patch("runtime.gtn_local_product.runner.ensure_notion_config"),
                patch("runtime.gtn_local_product.runner.resolve_codex_executable", return_value=Path("/bin/echo")),
            ):
                rc = run_once(paths, state, runner=boom)

            self.assertNotEqual(rc, 0)
            manifests = sorted(paths.runs_dir.glob("*/result.json"))
            self.assertTrue(manifests)
            payload = json.loads(manifests[-1].read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "failed")


if __name__ == "__main__":
    unittest.main()
