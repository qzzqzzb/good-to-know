from __future__ import annotations

import io
import json
import shutil
import subprocess
import tarfile
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.gtn_local_product import cli
from runtime.gtn_local_product.models import ResultState
from runtime.gtn_local_product.runner import exit_code_for_state


class StatusTests(unittest.TestCase):
    def test_schedule_python_executable_prefers_sibling_python_next_to_entrypoint(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            bin_dir = Path(tmp) / "bin"
            bin_dir.mkdir(parents=True, exist_ok=True)
            gtn_path = bin_dir / "gtn"
            python_path = bin_dir / "python"
            gtn_path.write_text("#!/bin/sh\n", encoding="utf-8")
            python_path.write_text("#!/bin/sh\n", encoding="utf-8")

            with patch.object(cli.sys, "argv", [str(gtn_path)]):
                self.assertEqual(cli.schedule_python_executable(), python_path)

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
            "output/feishu-briefing/settings.json": "{\n  \"webhook_url\": \"\"\n}\n",
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

    def _seed_runtime_tree(self, base: Path, readme_text: str = "seed\n") -> None:
        for rel_path, content in {
            "bootstrap/stack.yaml": "run_output_dir: runs\n",
            "context/naive-context/outbox.md": "# Naive Context Outbox\n",
            "discovery/web-discovery/outbox.md": "# Web Discovery Outbox\n",
            "memory/naive-memory/external_findings.md": "# External Findings\n",
            "memory/naive-memory/user_context.md": "# User Context\n",
            "output/feishu-briefing/settings.json": "{\n  \"webhook_url\": \"\"\n}\n",
            "output/notion-briefing/page_index.json": "{\n  \"pages\": {}\n}\n",
            "output/notion-briefing/settings.json": "{\n  \"parent_page_url\": \"\"\n}\n",
            "README.md": readme_text,
        }.items():
            path = base / rel_path
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content, encoding="utf-8")

    def _make_runtime_bundle(self, tmp: Path, readme_text: str = "seed\n") -> Path:
        source_root = tmp / "bundle-root" / "good-to-know-main"
        self._seed_runtime_tree(source_root, readme_text=readme_text)
        bundle_path = tmp / "runtime-bundle.tar.gz"
        with tarfile.open(bundle_path, "w:gz") as archive:
            archive.add(source_root, arcname="good-to-know-main")
        return bundle_path

    def test_status_renders_dashboard_modules_and_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            root.mkdir(parents=True, exist_ok=True)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text(
                json.dumps(
                    {
                        "database_name": "GoodToKnow Recommendations",
                        "database_url": "",
                        "parent_page_url": "https://notion.local/page",
                        "visible_properties": {"status": "Feedback"},
                        "default_status": "No feedback",
                    }
                ),
                encoding="utf-8",
            )
            (runtime_repo / "output" / "feishu-briefing" / "settings.json").write_text(
                json.dumps({"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook"}),
                encoding="utf-8",
            )
            (runtime_repo / "output" / "notion-briefing" / "page_index.json").write_text(
                json.dumps(
                    {
                        "default_status": "No feedback",
                        "pages": {
                            "a": {"last_seen_status": "No feedback"},
                            "b": {"last_seen_status": "Good to know"},
                            "c": {"last_seen_status": "Bad recommendation"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            (runtime_repo / "memory" / "naive-memory" / "user_context.md").write_text(
                "# User Context Memory\n\nAI agents and product design systems research.\n",
                encoding="utf-8",
            )
            (runtime_repo / "context" / "naive-context" / "outbox.md").write_text(
                "# Naive Context Outbox\n\nAgents agents product systems.\n",
                encoding="utf-8",
            )

            (root / "runs" / "run-1").mkdir(parents=True)
            repo_run_dir = runtime_repo / "runs" / "run-1"
            repo_run_dir.mkdir(parents=True, exist_ok=True)
            (repo_run_dir / "memory-findings.json").write_text(
                json.dumps(
                    [
                        {"source": "web_search", "summary": "one"},
                        {"source": "web_search", "summary": "two"},
                        {"source": "notion_feedback", "summary": "three"},
                    ]
                ),
                encoding="utf-8",
            )
            (repo_run_dir / "briefing.json").write_text(
                json.dumps({"items": [{"title": "A"}, {"title": "B"}]}),
                encoding="utf-8",
            )
            (repo_run_dir / "feishu-payload.json").write_text("{}", encoding="utf-8")
            (root / "state.json").write_text(json.dumps({
                "runtime_repo_path": str(runtime_repo),
                "codex_path": "/usr/local/bin/codex",
                "cadence": "1h",
                "enabled": True,
                "launch_agent_path": str(Path.home() / "Library/LaunchAgents/com.goodtoknow.gtn.plist"),
                "initialized_at": "2026-04-07T10:00:00+08:00",
            }), encoding="utf-8")
            (root / "runs" / "run-1" / "result.json").write_text(json.dumps({
                "state": "success",
                "updated_at": "2026-04-07T11:00:00+08:00"
            }), encoding="utf-8")
            (root / "runs" / "run-1" / "manifest.json").write_text(
                json.dumps({"repo_run_dir": str(repo_run_dir)}),
                encoding="utf-8",
            )
            (root / "status").mkdir(parents=True, exist_ok=True)
            (root / "status" / "history.json").write_text(
                json.dumps(
                    {
                        "version": 1,
                        "schema_started_at": "2026-04-07T11:00:00+08:00",
                        "updated_at": "2026-04-07T11:00:00+08:00",
                        "aggregated_run_ids": ["run-1"],
                        "totals": {"push_count": 1, "pushed_recommendations_total": 2},
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with (
                patch.object(cli, "launch_agent_loaded", return_value=True),
                patch("runtime.gtn_local_product.status_dashboard.launch_agent_loaded", return_value=True),
                patch("runtime.gtn_local_product.status_dashboard.installed_version_info", return_value=("0.2.1", "installed")),
                patch("runtime.gtn_local_product.status_dashboard.fetch_latest_pypi_version", return_value=("0.2.2", None)),
                redirect_stdout(buf),
            ):
                rc = cli.main(["--root", str(root), "status"])
            output = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("GoodToKnow Dashboard", output)
            self.assertIn("Last Run Status", output)
            self.assertIn("All History", output)
            self.assertIn("System Status", output)
            self.assertIn("User Profile", output)
            self.assertRegex(output, r"Records scanned\s+3")
            self.assertIn("Webpages", output)
            self.assertIn("searched", output)
            self.assertRegex(output, r"searched\s+.*2|Webpages\s+.*2")
            self.assertRegex(output, r"Recommendations\s+2")
            self.assertRegex(output, r"Push count\s+1")
            self.assertRegex(output, r"Good to know\s+.*1")
            self.assertIn("notion.local", output)
            self.assertIn("open.feishu", output)
            self.assertIn("configured", output)
            self.assertNotIn("test-hook", output)
            self.assertRegex(output.lower(), r"agents?\s+3")
            self.assertRegex(output, r"Version\s+0\.2\.1")
            self.assertIn("0.2.2 (update", output)
            self.assertIn("available)", output)
            self.assertRegex(output, r"Anchor\s+08:00")

    def test_status_shows_no_run_yet_when_no_run_exists(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/usr/local/bin/codex",
                        "cadence": "1h",
                        "enabled": False,
                        "launch_agent_path": str(Path.home() / "Library/LaunchAgents/com.goodtoknow.gtn.plist"),
                        "initialized_at": "2026-04-07T10:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with (
                patch("runtime.gtn_local_product.status_dashboard.installed_version_info", return_value=("0.2.1", "installed")),
                patch("runtime.gtn_local_product.status_dashboard.fetch_latest_pypi_version", return_value=("0.2.1", None)),
                redirect_stdout(buf),
            ):
                rc = cli.main(["--root", str(root), "status"])
            output = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertIn("No run yet", output)
            self.assertRegex(output, r"Anchor\s+08:00")

    def test_status_marks_repo_version_source_when_package_metadata_is_missing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/usr/local/bin/codex",
                        "cadence": "1h",
                        "enabled": False,
                        "launch_agent_path": str(Path.home() / "Library/LaunchAgents/com.goodtoknow.gtn.plist"),
                        "initialized_at": "2026-04-07T10:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with (
                patch("runtime.gtn_local_product.status_dashboard.installed_version_info", return_value=("0.2.1", "repo")),
                patch("runtime.gtn_local_product.status_dashboard.fetch_latest_pypi_version", return_value=("0.2.1", None)),
                redirect_stdout(buf),
            ):
                rc = cli.main(["--root", str(root), "status"])
            output = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertRegex(output, r"Version\s+0\.2\.1 \(repo\)")
            self.assertRegex(output, r"Latest\s+0\.2\.1 \(matches repo\)")

    def test_status_survives_latest_version_check_failures(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/usr/local/bin/codex",
                        "cadence": "1h",
                        "enabled": False,
                        "launch_agent_path": str(Path.home() / "Library/LaunchAgents/com.goodtoknow.gtn.plist"),
                        "initialized_at": "2026-04-07T10:00:00+08:00",
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with (
                patch("runtime.gtn_local_product.status_dashboard.installed_version_info", return_value=("0.2.1", "installed")),
                patch("runtime.gtn_local_product.status_dashboard.fetch_latest_pypi_version", return_value=(None, "ssl error")),
                redirect_stdout(buf),
            ):
                rc = cli.main(["--root", str(root), "status"])
            output = buf.getvalue()
            self.assertEqual(rc, 0)
            self.assertRegex(output, r"Version\s+0\.2\.1")
            self.assertRegex(output, r"Latest\s+\(check failed\)")

    def test_run_prints_summary_when_runner_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (runtime_repo / "output" / "notion-briefing").mkdir(parents=True)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text("{}", encoding="utf-8")
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/bin/echo",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )

            def boom(*args, **kwargs):
                raise OSError("boom")

            buf = io.StringIO()
            with (
                patch("runtime.gtn_local_product.cli.run_once", return_value=16),
                patch.object(cli, "latest_app_run") as latest_app_run,
                redirect_stdout(buf),
            ):
                run_dir = root / "runs" / "run-1"
                run_dir.mkdir(parents=True)
                (run_dir / "result.json").write_text(
                    json.dumps({"state": "failed", "message": "boom", "details": {}}),
                    encoding="utf-8",
                )
                latest_app_run.return_value = run_dir
                rc = cli.main(["--root", str(root), "run"])

            self.assertEqual(rc, 16)
            output = buf.getvalue()
            self.assertIn("Run Failed", output)
            self.assertIn("boom", output)

    def test_run_prints_partial_success_phase_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            (runtime_repo / "bootstrap").mkdir(parents=True)
            (runtime_repo / "bootstrap" / "stack.yaml").write_text("run_output_dir: runs\n", encoding="utf-8")
            (runtime_repo / "output" / "notion-briefing").mkdir(parents=True)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text("{}", encoding="utf-8")
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/bin/echo",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )
            run_dir = root / "runs" / "run-1"
            run_dir.mkdir(parents=True)
            (run_dir / "result.json").write_text(
                json.dumps(
                    {
                        "state": "partial_success",
                        "message": "Notion succeeded; Feishu failed",
                        "details": {
                            "discovery_findings": 4,
                            "notion": {"state": "success", "pages_created": 4},
                            "feishu": {"state": "failed", "reason": "dns"},
                        },
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with patch("runtime.gtn_local_product.cli.run_once", return_value=10), patch.object(cli, "latest_app_run", return_value=run_dir), redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "run"])

            self.assertEqual(rc, 10)
            output = buf.getvalue()
            self.assertIn("Run Partial Success", output)
            self.assertIn("Discovery", output)
            self.assertIn("Notion", output)
            self.assertIn("Feishu", output)

    def test_exit_code_for_failed_state_is_nonzero(self) -> None:
        self.assertEqual(exit_code_for_state(ResultState.SUCCESS), 0)
        self.assertNotEqual(exit_code_for_state(ResultState.FAILED), 0)

    def test_init_rejects_missing_runtime_repo(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            with self.assertRaises(SystemExit):
                cli.main(["--root", str(root), "init", "--runtime-repo", str(root / "missing"), "--codex-path", "/usr/bin/codex"])

    def test_init_can_hydrate_runtime_from_bundle_url(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            bundle_path = self._make_runtime_bundle(tmp_path)

            with (
                patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")),
                patch.object(cli.subprocess, "run", return_value=subprocess.CompletedProcess([], 0)),
            ):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "init",
                        "--runtime-bundle-url",
                        bundle_path.as_uri(),
                        "--codex-path",
                        "/bin/echo",
                    ]
                )

            self.assertEqual(rc, 0)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self.assertTrue((runtime_repo / "bootstrap" / "stack.yaml").exists())
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["runtime_bundle_url"], bundle_path.as_uri())

    def test_init_can_hydrate_runtime_from_packaged_resources(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"

            with patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "init",
                        "--codex-path",
                        "/bin/echo",
                    ]
                )

            self.assertEqual(rc, 0)
            packaged_runtime = root / "runtime" / "GoodToKnow"
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["runtime_repo_path"], str(packaged_runtime.resolve()))
            self.assertEqual(state["runtime_bundle_url"], "")
            self.assertTrue((packaged_runtime / "bootstrap" / "stack.yaml").is_symlink())
            self.assertFalse((packaged_runtime / "output" / "notion-briefing" / "settings.json").is_symlink())

    def test_init_can_apply_onboarding_flags_without_install_script(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"

            with (
                patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")),
                patch.object(cli, "record_initial_user_profile") as record_profile,
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli.main(
                        [
                            "--root",
                            str(root),
                            "setup",
                            "--codex-path",
                            "/bin/echo",
                            "--tier",
                            "deep",
                            "--notion-page-url",
                            "https://notion.local/page",
                            "--feishu-webhook-url",
                            "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook",
                            "--user-profile",
                            "I care about agents and product systems.",
                            "--no-prompt",
                        ]
                    )

            self.assertEqual(rc, 0)
            output = buf.getvalue()
            packaged_runtime = root / "runtime" / "GoodToKnow"
            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            notion_settings = json.loads(
                (packaged_runtime / "output" / "notion-briefing" / "settings.json").read_text(encoding="utf-8")
            )
            feishu_settings = json.loads(
                (packaged_runtime / "output" / "feishu-briefing" / "settings.json").read_text(encoding="utf-8")
            )
            context_settings = json.loads(
                (packaged_runtime / "context" / "naive-context" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["tier"], "deep")
            self.assertEqual(notion_settings["parent_page_url"], "https://notion.local/page")
            self.assertEqual(feishu_settings["webhook_url"], "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook")
            self.assertEqual(feishu_settings["max_items"], 40)
            self.assertEqual(context_settings["features"]["agent_sessions"]["lookback_hours"], 336)
            self.assertIn("GTN Setup", output)
            self.assertIn("Setup Summary", output)
            self.assertIn("deep", output)
            self.assertIn("https://notion.local/page", output)
            self.assertIn("https://open.feishu.cn/... (configured)", output)
            self.assertNotIn("test-hook", output)
            record_profile.assert_called_once()
            args, _ = record_profile.call_args
            self.assertEqual(Path(args[0]).resolve(), packaged_runtime.resolve())
            self.assertEqual(args[1], "I care about agents and product systems.")

    def test_setup_does_not_fail_when_profile_recording_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"

            with (
                patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")),
                patch.object(cli, "record_initial_user_profile", side_effect=RuntimeError("profile backend unavailable")),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli.main(
                        [
                            "--root",
                            str(root),
                            "setup",
                            "--codex-path",
                            "/bin/echo",
                            "--user-profile",
                            "I care about agents and product systems.",
                            "--no-prompt",
                        ]
                    )

            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("Not recorded", output)

    def test_setup_interactive_enter_keeps_existing_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            runtime_repo = tmp_path / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (runtime_repo / "output" / "notion-briefing" / "settings.json").write_text(
                json.dumps({"parent_page_url": "https://notion.local/current"}),
                encoding="utf-8",
            )
            (runtime_repo / "output" / "feishu-briefing" / "settings.json").write_text(
                json.dumps({"webhook_url": "https://open.feishu.cn/open-apis/bot/v2/hook/current-hook"}),
                encoding="utf-8",
            )
            identity_path = runtime_repo / "memory" / "mempalace-memory" / "identity.md"
            identity_path.parent.mkdir(parents=True, exist_ok=True)
            identity_path.write_text("I care about agent systems.\n", encoding="utf-8")

            with (
                patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")),
                patch.object(cli.sys.stdin, "isatty", return_value=True),
                patch.object(cli, "record_initial_user_profile") as record_profile,
                patch("builtins.input", side_effect=["", "", "", "n"]),
            ):
                buf = io.StringIO()
                with redirect_stdout(buf):
                    rc = cli.main(
                        [
                            "--root",
                            str(root),
                            "setup",
                            "--runtime-repo",
                            str(runtime_repo),
                            "--codex-path",
                            "/bin/echo",
                        ]
                    )

            self.assertEqual(rc, 0)
            output = buf.getvalue()
            notion_settings = json.loads(
                (runtime_repo / "output" / "notion-briefing" / "settings.json").read_text(encoding="utf-8")
            )
            feishu_settings = json.loads(
                (runtime_repo / "output" / "feishu-briefing" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(notion_settings["parent_page_url"], "https://notion.local/current")
            self.assertEqual(feishu_settings["webhook_url"], "https://open.feishu.cn/open-apis/bot/v2/hook/current-hook")
            record_profile.assert_not_called()
            self.assertIn("🚀 Notion URL setup", output)
            self.assertIn("Current value: https://notion.local/current", output)
            self.assertIn("enter to keep and skip", output)
            self.assertIn("🚀 Feishu webhook setup", output)
            self.assertIn("🚀 Profile setup", output)

    def test_config_get_and_set_support_tier_language_and_urls(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "codex_path": "/usr/local/bin/codex",
                        "tier": "balanced",
                        "language": "en",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "config", "set", "tier", "light"])
            self.assertEqual(rc, 0)
            self.assertIn("tier=light", buf.getvalue())

            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            context_settings = json.loads(
                (runtime_repo / "context" / "naive-context" / "settings.json").read_text(encoding="utf-8")
            )
            feishu_settings = json.loads(
                (runtime_repo / "output" / "feishu-briefing" / "settings.json").read_text(encoding="utf-8")
            )
            self.assertEqual(state["tier"], "light")
            self.assertEqual(context_settings["features"]["browser_history"]["lookback_hours"], 24)
            self.assertEqual(feishu_settings["max_items"], 10)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "config", "set", "language", "zh"])
            self.assertEqual(rc, 0)
            self.assertIn("language=zh", buf.getvalue())

            state = json.loads((root / "state.json").read_text(encoding="utf-8"))
            self.assertEqual(state["language"], "zh")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "config", "set", "notion-page-url", "https://notion.local/page"])
            self.assertEqual(rc, 0)
            self.assertIn("notion-page-url=https://notion.local/page", buf.getvalue())

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "config",
                        "set",
                        "feishu-webhook-url",
                        "https://open.feishu.cn/open-apis/bot/v2/hook/test-hook",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("configured", buf.getvalue())
            self.assertNotIn("test-hook", buf.getvalue())

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "config", "get", "tier"])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.getvalue().strip(), "light")

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "config", "get", "language"])
            self.assertEqual(rc, 0)
            self.assertEqual(buf.getvalue().strip(), "zh")

    def test_config_set_language_rejects_unsupported_values(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo)
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

            with self.assertRaises(SystemExit) as exc:
                cli.main(["--root", str(root), "config", "set", "language", "fr"])

            self.assertIn("Unsupported language", str(exc.exception))

    def test_packaged_runtime_copies_mutable_files_but_links_immutable_assets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            package_root = tmp_path / "package-root"
            source_root = package_root / "resources" / "default_runtime"
            self._seed_runtime_tree(source_root)
            runtime_repo = tmp_path / "runtime"

            with patch.object(cli.pkg_resources, "files", return_value=package_root):
                hydrated = cli.hydrate_packaged_runtime(runtime_repo)

            self.assertEqual(hydrated, runtime_repo.resolve())
            self.assertFalse((runtime_repo / "output/notion-briefing/settings.json").is_symlink())
            self.assertTrue((runtime_repo / "bootstrap/stack.yaml").is_symlink())
            self.assertTrue((runtime_repo / "README.md").is_symlink())

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
            feishu_state = runtime_repo / "output" / "feishu-briefing" / "settings.json"
            feishu_state.write_text("{\n  \"webhook_url\": \"https://open.feishu.cn/open-apis/bot/v2/hook/test\"\n}\n", encoding="utf-8")

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
            self.assertEqual(
                feishu_state.read_text(encoding="utf-8"),
                "{\n  \"webhook_url\": \"https://open.feishu.cn/open-apis/bot/v2/hook/test\"\n}\n",
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

    def test_update_refreshes_bundle_runtime_and_preserves_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            root.mkdir(parents=True, exist_ok=True)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo, readme_text="old bundle\n")
            tracked_state = runtime_repo / "output" / "notion-briefing" / "settings.json"
            tracked_state.write_text("{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n", encoding="utf-8")
            bundle_path = self._make_runtime_bundle(tmp_path, readme_text="new bundle\n")
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "runtime_bundle_url": bundle_path.as_uri(),
                        "codex_path": "/bin/echo",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )

            real_run = subprocess.run

            def wrapped_run(*args, **kwargs):
                cmd = args[0]
                if cmd[:3] == [cli.sys.executable, "-m", "pip"]:
                    return subprocess.CompletedProcess(cmd, 0)
                return real_run(*args, **kwargs)

            with patch.object(cli.subprocess, "run", side_effect=wrapped_run):
                rc = cli.main(["--root", str(root), "update"])

            self.assertEqual(rc, 0)
            self.assertEqual((runtime_repo / "README.md").read_text(encoding="utf-8"), "new bundle\n")
            self.assertEqual(
                tracked_state.read_text(encoding="utf-8"),
                "{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n",
            )

    def test_update_refreshes_packaged_runtime_and_preserves_state_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            root = tmp_path / ".gtn"
            root.mkdir(parents=True, exist_ok=True)
            runtime_repo = root / "runtime" / "GoodToKnow"
            self._seed_runtime_tree(runtime_repo, readme_text="old packaged\n")
            tracked_state = runtime_repo / "output" / "notion-briefing" / "settings.json"
            tracked_state.write_text("{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n", encoding="utf-8")
            (root / "state.json").write_text(
                json.dumps(
                    {
                        "runtime_repo_path": str(runtime_repo),
                        "runtime_bundle_url": "",
                        "codex_path": "/bin/echo",
                        "launch_agent_path": str(root / "com.goodtoknow.gtn.plist"),
                    }
                ),
                encoding="utf-8",
            )
            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "update"])

            self.assertEqual(rc, 0)
            self.assertIn("package-manager-native upgrades", buf.getvalue())
            self.assertIn("goodtoknow-gtn", buf.getvalue())
            self.assertEqual((runtime_repo / "README.md").read_text(encoding="utf-8"), "old packaged\n")
            self.assertEqual(
                tracked_state.read_text(encoding="utf-8"),
                "{\n  \"parent_page_url\": \"https://notion.local/page\"\n}\n",
            )

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
