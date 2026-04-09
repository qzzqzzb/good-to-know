from __future__ import annotations

import io
import json
import subprocess
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.gtn_local_product import cli
from runtime.gtn_local_product.models import ResultState
from runtime.gtn_local_product.runner import exit_code_for_state


class StatusTests(unittest.TestCase):
    @staticmethod
    def _git(*args: str, cwd: Path | None = None) -> None:
        subprocess.run(args, cwd=cwd, check=True, capture_output=True, text=True)

    def _seed_runtime_origin(self, tmp: Path) -> tuple[Path, Path]:
        origin = tmp / "origin.git"
        seed = tmp / "seed"
        self._git("git", "init", "--bare", str(origin))
        self._git("git", "clone", str(origin), str(seed))
        self._git("git", "-C", str(seed), "checkout", "-b", "main")
        for rel_path, content in {
            "bootstrap/stack.yaml": "run_output_dir: runs\n",
            "context/naive-context/outbox.md": "# Naive Context Outbox\n",
            "discovery/web-discovery/outbox.md": "# Web Discovery Outbox\n",
            "memory/naive-memory/external_findings.md": "# External Findings\n",
            "memory/naive-memory/user_context.md": "# User Context\n",
            "output/notion-briefing/page_index.json": "{\n  \"pages\": {}\n}\n",
            "output/notion-briefing/settings.json": "{\n  \"parent_page_url\": \"\"\n}\n",
            "README.md": "seed\n",
        }.items():
            path = seed / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")
        self._git("git", "-C", str(seed), "add", ".")
        self._git(
            "git",
            "-C",
            str(seed),
            "-c",
            "user.name=Test",
            "-c",
            "user.email=test@example.com",
            "commit",
            "-m",
            "seed",
        )
        self._git("git", "-C", str(seed), "push", "-u", "origin", "main")
        return origin, seed

    def _clone_runtime_repo(self, tmp: Path, origin: Path) -> Path:
        runtime_repo = tmp / "runtime" / "GoodToKnow"
        self._git("git", "clone", str(origin), str(runtime_repo))
        self._git("git", "-C", str(runtime_repo), "checkout", "main")
        return runtime_repo

    def _write_state(self, root: Path, runtime_repo: Path) -> None:
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

    def test_update_preserves_local_runtime_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            root.mkdir(parents=True, exist_ok=True)
            origin, seed = self._seed_runtime_origin(tmp_path)
            runtime_repo = self._clone_runtime_repo(tmp_path, origin)
            self._write_state(root, runtime_repo)

            tracked_state = runtime_repo / "output" / "notion-briefing" / "settings.json"
            tracked_state.write_text("{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n", encoding="utf-8")

            (seed / "README.md").write_text("updated upstream\n", encoding="utf-8")
            self._git(
                "git",
                "-C",
                str(seed),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-am",
                "upstream",
            )
            self._git("git", "-C", str(seed), "push", "origin", "main")

            real_run = subprocess.run

            def wrapped_run(*args, **kwargs):
                cmd = args[0]
                if cmd[:3] == [cli.sys.executable, "-m", "pip"]:
                    return subprocess.CompletedProcess(cmd, 0)
                return real_run(*args, **kwargs)

            with patch.object(cli.subprocess, "run", side_effect=wrapped_run):
                rc = cli.main(["--root", str(root), "update"])

            self.assertEqual(rc, 0)
            self.assertEqual(
                tracked_state.read_text(encoding="utf-8"),
                "{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n",
            )
            self.assertEqual((runtime_repo / "README.md").read_text(encoding="utf-8"), "updated upstream\n")

    def test_update_falls_back_to_uv_when_pip_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            root.mkdir(parents=True, exist_ok=True)
            origin, seed = self._seed_runtime_origin(tmp_path)
            runtime_repo = self._clone_runtime_repo(tmp_path, origin)
            self._write_state(root, runtime_repo)

            (seed / "README.md").write_text("uv-fallback\n", encoding="utf-8")
            self._git(
                "git",
                "-C",
                str(seed),
                "-c",
                "user.name=Test",
                "-c",
                "user.email=test@example.com",
                "commit",
                "-am",
                "upstream",
            )
            self._git("git", "-C", str(seed), "push", "origin", "main")

            real_run = subprocess.run
            seen_commands: list[list[str]] = []

            def wrapped_run(*args, **kwargs):
                cmd = args[0]
                seen_commands.append(list(cmd))
                if cmd[:3] == [cli.sys.executable, "-m", "pip"]:
                    return subprocess.CompletedProcess(cmd, 1, "", "No module named pip")
                if cmd[:2] == ["/fake/uv", "pip"]:
                    return subprocess.CompletedProcess(cmd, 0, "", "")
                return real_run(*args, **kwargs)

            with (
                patch.object(cli.shutil, "which", side_effect=lambda name: "/fake/uv" if name == "uv" else None),
                patch.object(cli.subprocess, "run", side_effect=wrapped_run),
            ):
                rc = cli.main(["--root", str(root), "update"])

            self.assertEqual(rc, 0)
            self.assertEqual((runtime_repo / "README.md").read_text(encoding="utf-8"), "uv-fallback\n")
            self.assertIn(
                [
                    "/fake/uv",
                    "pip",
                    "install",
                    "--python",
                    cli.sys.executable,
                    "--editable",
                    str(runtime_repo.resolve()),
                ],
                seen_commands,
            )

    def test_update_rejects_non_runtime_state_changes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            root.mkdir(parents=True, exist_ok=True)
            origin, _seed = self._seed_runtime_origin(tmp_path)
            runtime_repo = self._clone_runtime_repo(tmp_path, origin)
            self._write_state(root, runtime_repo)

            (runtime_repo / "README.md").write_text("local edit\n", encoding="utf-8")

            with self.assertRaises(SystemExit) as error:
                cli.main(["--root", str(root), "update"])

            self.assertIn("non-runtime state files", str(error.exception))
            self.assertEqual((runtime_repo / "README.md").read_text(encoding="utf-8"), "local edit\n")

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
