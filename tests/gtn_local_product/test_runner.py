from __future__ import annotations

import json
import subprocess
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
        self.assertIn("--skip-git-repo-check", cmd)

    def test_build_codex_command_can_propagate_gtn_home(self) -> None:
        cmd = build_codex_command(
            Path("/usr/local/bin/codex"),
            Path("/tmp/runtime"),
            Path("/tmp/app-run"),
            Path("/tmp/app-run/last-message.txt"),
            gtn_home=Path("/tmp/gtn-home"),
        )
        self.assertEqual(cmd[:2], ["env", "GTN_HOME=/tmp/gtn-home"])

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

    def test_run_once_writes_status_summary_and_history_for_success(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (runtime_repo / "output" / "notion-briefing").mkdir(parents=True)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text("{}", encoding="utf-8")

            paths = resolve_paths(root=root, runtime_dir=runtime_repo)
            state = StateData(runtime_repo_path=str(runtime_repo), codex_path="/bin/echo")

            def fake_runner(command, cwd, stdout_path, stderr_path, prompt_path):
                app_run_dir = Path(command[command.index("--add-dir") + 1])
                prompt_text = prompt_path.read_text(encoding="utf-8")
                repo_run_dir = None
                for line in prompt_text.splitlines():
                    if line.startswith("Repo run dir: "):
                        repo_run_dir = Path(line.split("`")[1])
                        break
                assert repo_run_dir is not None
                repo_run_dir.mkdir(parents=True, exist_ok=True)
                (repo_run_dir / "memory-findings.json").write_text(
                    json.dumps(
                        [
                            {"source": "web_search"},
                            {"source": "web_search"},
                            {"source": "notion_feedback"},
                        ]
                    ),
                    encoding="utf-8",
                )
                (repo_run_dir / "briefing.json").write_text(
                    json.dumps({"items": [{"title": "A"}, {"title": "B"}]}),
                    encoding="utf-8",
                )
                (repo_run_dir / "feishu-payload.json").write_text("{}", encoding="utf-8")
                (app_run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "state": "success",
                            "message": "ok",
                            "updated_at": "2026-04-10T00:00:00+00:00",
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0)

            with (
                patch("runtime.gtn_local_product.runner.ensure_codex_auth"),
                patch("runtime.gtn_local_product.runner.ensure_search_capability"),
                patch("runtime.gtn_local_product.runner.ensure_notion_config"),
                patch("runtime.gtn_local_product.runner.resolve_codex_executable", return_value=Path("/bin/echo")),
            ):
                rc = run_once(paths, state, runner=fake_runner)

            self.assertEqual(rc, 0)
            run_dirs = sorted(paths.runs_dir.glob("*"))
            self.assertTrue(run_dirs)
            summary = json.loads((run_dirs[-1] / "status-summary.json").read_text(encoding="utf-8"))
            history = json.loads(paths.status_history_file.read_text(encoding="utf-8"))
            self.assertEqual(summary["metrics"]["records_scanned"], 3)
            self.assertEqual(summary["metrics"]["webpages_searched"], 2)
            self.assertEqual(summary["metrics"]["recommendations_produced"], 2)
            self.assertEqual(history["totals"]["push_count"], 1)
            self.assertEqual(history["totals"]["pushed_recommendations_total"], 2)

    def test_run_once_releases_lock_when_post_run_summary_update_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (runtime_repo / "output" / "notion-briefing").mkdir(parents=True)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text("{}", encoding="utf-8")

            paths = resolve_paths(root=root, runtime_dir=runtime_repo)
            state = StateData(runtime_repo_path=str(runtime_repo), codex_path="/bin/echo")

            def fake_runner(command, cwd, stdout_path, stderr_path, prompt_path):
                app_run_dir = Path(command[command.index("--add-dir") + 1])
                prompt_text = prompt_path.read_text(encoding="utf-8")
                repo_run_dir = None
                for line in prompt_text.splitlines():
                    if line.startswith("Repo run dir: "):
                        repo_run_dir = Path(line.split("`")[1])
                        break
                assert repo_run_dir is not None
                repo_run_dir.mkdir(parents=True, exist_ok=True)
                (repo_run_dir / "memory-findings.json").write_text("[]", encoding="utf-8")
                (repo_run_dir / "briefing.json").write_text(json.dumps({"items": []}), encoding="utf-8")
                (app_run_dir / "result.json").write_text(
                    json.dumps(
                        {
                            "state": "success",
                            "message": "ok",
                            "updated_at": "2026-04-10T00:00:00+00:00",
                        }
                    ),
                    encoding="utf-8",
                )
                return subprocess.CompletedProcess(command, 0)

            with (
                patch("runtime.gtn_local_product.runner.ensure_codex_auth"),
                patch("runtime.gtn_local_product.runner.ensure_search_capability"),
                patch("runtime.gtn_local_product.runner.ensure_notion_config"),
                patch("runtime.gtn_local_product.runner.resolve_codex_executable", return_value=Path("/bin/echo")),
                patch("runtime.gtn_local_product.runner.update_history_with_summary", side_effect=RuntimeError("history boom")),
            ):
                with self.assertRaises(RuntimeError):
                    run_once(paths, state, runner=fake_runner)

            self.assertFalse(paths.lock_file.exists(), "lock should be released even when summary aggregation fails")


if __name__ == "__main__":
    unittest.main()
