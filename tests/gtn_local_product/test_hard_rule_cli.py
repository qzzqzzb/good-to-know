from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from runtime.gtn_local_product import cli


class HardRuleCliTests(unittest.TestCase):
    def test_setup_flags_can_create_hard_rule_subscriptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            buf = io.StringIO()
            with (
                patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")),
                redirect_stdout(buf),
            ):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "setup",
                        "--codex-path",
                        "/bin/echo",
                        "--hard-rule-source",
                        "arxiv",
                        "--hard-rule-source",
                        "producthunt",
                        "--hard-rule-topic",
                        "agent memory",
                        "--hard-rule-topic-override",
                        "producthunt=agent tools",
                        "--no-prompt",
                    ]
                )

            self.assertEqual(rc, 0)
            payload = json.loads((root / "hard-rules" / "subscriptions.json").read_text(encoding="utf-8"))
            subscriptions = payload["subscriptions"]
            self.assertEqual(len(subscriptions), 2)
            self.assertEqual({item["source"] for item in subscriptions}, {"arxiv", "producthunt"})
            topics = {item["source"]: item["topic"] for item in subscriptions}
            self.assertEqual(topics["arxiv"], "agent memory")
            self.assertEqual(topics["producthunt"], "agent tools")
            self.assertIn("Hard rules", buf.getvalue())
            self.assertIn("2 subscription(s) configured", buf.getvalue())

    def test_setup_rejects_hard_rule_sources_without_topic(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            with patch.object(cli, "resolve_codex_executable", return_value=Path("/bin/echo")):
                with self.assertRaises(SystemExit) as error:
                    cli.main(
                        [
                            "--root",
                            str(root),
                            "setup",
                            "--codex-path",
                            "/bin/echo",
                            "--hard-rule-source",
                            "arxiv",
                            "--no-prompt",
                        ]
                    )
            self.assertIn("requires a topic", str(error.exception))

    def test_hard_rules_cli_can_list_add_and_delete_subscriptions(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(
                    [
                        "--root",
                        str(root),
                        "hard-rules",
                        "add",
                        "--source",
                        "arxiv",
                        "--topic",
                        "agent memory",
                    ]
                )
            self.assertEqual(rc, 0)
            self.assertIn("Added hard-rule subscription", buf.getvalue())

            payload = json.loads((root / "hard-rules" / "subscriptions.json").read_text(encoding="utf-8"))
            subscription_id = payload["subscriptions"][0]["id"]

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "hard-rules", "list"])
            self.assertEqual(rc, 0)
            output = buf.getvalue()
            self.assertIn("Hard-Rule Subscriptions", output)
            self.assertIn("agent memory", output)
            self.assertIn(subscription_id, output)

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "hard-rules", "delete", subscription_id])
            self.assertEqual(rc, 0)
            self.assertIn(subscription_id, buf.getvalue())

            buf = io.StringIO()
            with redirect_stdout(buf):
                rc = cli.main(["--root", str(root), "hard-rules", "list"])
            self.assertEqual(rc, 0)
            self.assertIn("No hard-rule subscriptions configured", buf.getvalue())
