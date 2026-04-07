from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.gtn_local_product import cli
from runtime.gtn_local_product.models import ResultState
from runtime.gtn_local_product.runner import exit_code_for_state


class StatusTests(unittest.TestCase):
    def test_status_reports_basic_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            (root / "runs" / "run-1").mkdir(parents=True)
            (root / "state.json").write_text(json.dumps({
                "runtime_repo_path": "/tmp/runtime",
                "codex_path": "/usr/local/bin/codex",
                "cadence": "1h",
                "enabled": True,
                "launch_agent_path": str(Path.home() / "Library/LaunchAgents/com.goodtoknow.gtn.plist"),
            }), encoding="utf-8")
            (root / "runs" / "run-1" / "result.json").write_text(json.dumps({
                "state": "success",
                "updated_at": "2026-04-07T11:00:00+08:00"
            }), encoding="utf-8")
            buf = io.StringIO()
            with patch.object(cli, "launch_agent_loaded", return_value=True), redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "status"])
            output = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("enabled=True", output)
            self.assertIn("cadence=1h", output)
            self.assertIn("last_result=success", output)

    def test_exit_code_for_failed_state_is_nonzero(self) -> None:
        self.assertEqual(exit_code_for_state(ResultState.SUCCESS), 0)
        self.assertNotEqual(exit_code_for_state(ResultState.FAILED), 0)

    def test_init_rejects_missing_runtime_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit):
                cli.main(["--root", str(root), "init", "--runtime-repo", str(root / "missing"), "--codex-path", "/usr/bin/codex"])

    def test_update_refuses_when_lock_is_active(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True, exist_ok=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/usr/local/bin/codex",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )
            (root / "lock.json").write_text(json.dumps({"run_id": "run-1"}), encoding="utf-8")
            with patch.object(cli, "lock_status", return_value="active"):
                with self.assertRaises(SystemExit):
                    cli.main(["--root", str(root), "update"])

    def test_uninstall_removes_root_and_wrapper(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            root.mkdir(parents=True)
            wrapper = Path(tmp) / "gtn"
            wrapper.write_text("#!/bin/sh\n", encoding="utf-8")
            with (
                patch.object(cli, "resolve_installed_gtn_wrapper", return_value=wrapper),
                patch.object(cli, "unload_launch_agent"),
            ):
                rc = cli.main(["--root", str(root), "uninstall", "--yes"])
            self.assertEqual(rc, 0)
            self.assertFalse(root.exists())
            self.assertFalse(wrapper.exists())


if __name__ == "__main__":
    unittest.main()
