from __future__ import annotations

import importlib.util
import json
import os
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
    "run_active_stack_hard_rules",
)
hard_rule_pipeline = load_module(
    ROOT / "runtime/codex-agent-loop/scripts/hard_rule_pipeline.py",
    "hard_rule_pipeline",
)
run_hard_rules_cli = load_module(
    ROOT / "runtime/codex-agent-loop/scripts/run_hard_rules.py",
    "run_hard_rules_cli",
)


class HardRuleArtifactTests(unittest.TestCase):
    def test_filter_hard_rule_items_drops_old_arxiv_entries(self) -> None:
        now = hard_rule_pipeline.datetime(2026, 4, 14, 12, 0, tzinfo=hard_rule_pipeline.timezone.utc)
        items = [
            {
                "subscription_id": "arxiv:recent",
                "source": "arxiv",
                "topic": "agent memory",
                "title": "Recent paper",
                "summary": "Recent summary",
                "link": "https://arxiv.org/abs/2604.12345",
                "published_at": "2026-04-01T00:00:00Z",
                "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/2604.12345",
                "raw": "https://arxiv.org/abs/2604.12345",
            },
            {
                "subscription_id": "arxiv:old",
                "source": "arxiv",
                "topic": "agent memory",
                "title": "Old paper",
                "summary": "Old summary",
                "link": "https://arxiv.org/abs/2509.12345",
                "published_at": "2025-09-29T00:00:00Z",
                "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/2509.12345",
                "raw": "https://arxiv.org/abs/2509.12345",
            },
            {
                "subscription_id": "producthunt:current",
                "source": "producthunt",
                "topic": "agent memory",
                "title": "Current launch",
                "summary": "Launch summary",
                "link": "https://www.producthunt.com/products/current-launch",
                "published_at": "2026-04-14",
                "dedup_key": "hard-rule:producthunt:https://www.producthunt.com/products/current-launch",
                "raw": "https://www.producthunt.com/products/current-launch",
            },
        ]

        filtered = hard_rule_pipeline.filter_hard_rule_items(items, now=now)

        self.assertEqual([item["title"] for item in filtered], ["Recent paper", "Current launch"])

    def test_build_hard_rule_worklist_respects_refresh_state(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            subscriptions_path = root / "hard-rules" / "subscriptions.json"
            refresh_state_path = root / "hard-rules" / "refresh-state.json"
            subscriptions_path.parent.mkdir(parents=True, exist_ok=True)
            subscriptions_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subscriptions": [
                            {
                                "id": "arxiv:agent-memory",
                                "source": "arxiv",
                                "topic": "agent memory",
                                "top_n": 5,
                                "created_at": "2026-04-10T00:00:00+00:00",
                                "updated_at": "2026-04-10T00:00:00+00:00",
                            },
                            {
                                "id": "producthunt:agent-memory",
                                "source": "producthunt",
                                "topic": "agent memory",
                                "top_n": 5,
                                "created_at": "2026-04-10T00:00:00+00:00",
                                "updated_at": "2026-04-10T00:00:00+00:00",
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )
            refresh_state_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subscriptions": {
                            "producthunt:agent-memory": {"last_refreshed_at": hard_rule_pipeline.now_iso()}
                        },
                    }
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"GTN_HOME": str(root)}):
                worklist = hard_rule_pipeline.build_hard_rule_worklist()

            self.assertEqual([item["id"] for item in worklist.eligible_subscriptions], ["arxiv:agent-memory"])
            self.assertEqual(worklist.skipped_subscription_ids, ["producthunt:agent-memory"])

    def test_run_hard_rule_subscriptions_writes_separate_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            run_dir = Path(tmp) / "run-123"
            run_dir.mkdir(parents=True, exist_ok=True)
            subscriptions_path = root / "hard-rules" / "subscriptions.json"
            subscriptions_path.parent.mkdir(parents=True, exist_ok=True)
            subscriptions_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subscriptions": [
                            {
                                "id": "arxiv:agent-memory",
                                "source": "arxiv",
                                "topic": "agent memory",
                                "top_n": 5,
                                "created_at": "2026-04-10T00:00:00+00:00",
                                "updated_at": "2026-04-10T00:00:00+00:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            with (
                patch.dict(os.environ, {"GTN_HOME": str(root)}),
                patch.object(
                    hard_rule_pipeline,
                    "fetch_subscription_items",
                    return_value=[
                        {
                            "subscription_id": "arxiv:agent-memory",
                            "source": "arxiv",
                            "topic": "agent memory",
                            "title": "Paper",
                            "summary": "Paper summary",
                            "link": "https://arxiv.org/abs/1234.5678",
                            "published_at": "2026-04-10T00:00:00Z",
                            "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/1234.5678",
                            "raw": "https://arxiv.org/abs/1234.5678",
                        }
                    ],
                ),
            ):
                result = hard_rule_pipeline.run_hard_rule_subscriptions("run-123", run_dir, run_dir / "hard-rule-result.json")

            self.assertEqual(result.state, "success")
            self.assertTrue((run_dir / "hard-rule-briefing.json").exists())
            self.assertTrue((run_dir / "hard-rule-briefing.md").exists())
            payload = json.loads((run_dir / "hard-rule-briefing.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["track"], "hard_rule")
            self.assertEqual(payload["items"][0]["title"], "Paper")

    def test_finalize_hard_rule_items_applies_arxiv_recency_filter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            run_dir = Path(tmp) / "run-filtered"
            run_dir.mkdir(parents=True, exist_ok=True)

            items = [
                {
                    "subscription_id": "arxiv:recent",
                    "source": "arxiv",
                    "topic": "agent memory",
                    "title": "Recent paper",
                    "summary": "Recent summary",
                    "link": "https://arxiv.org/abs/2604.12345",
                    "published_at": "2026-04-01T00:00:00Z",
                    "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/2604.12345",
                    "raw": "https://arxiv.org/abs/2604.12345",
                },
                {
                    "subscription_id": "arxiv:old",
                    "source": "arxiv",
                    "topic": "agent memory",
                    "title": "Old paper",
                    "summary": "Old summary",
                    "link": "https://arxiv.org/abs/2509.12345",
                    "published_at": "2025-09-29T00:00:00Z",
                    "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/2509.12345",
                    "raw": "https://arxiv.org/abs/2509.12345",
                },
            ]

            with patch.dict(os.environ, {"GTN_HOME": str(root)}):
                result = hard_rule_pipeline.finalize_hard_rule_items(
                    "run-filtered",
                    run_dir,
                    items,
                    result_path=run_dir / "hard-rule-result.json",
                    processed_subscription_ids=["arxiv:recent", "arxiv:old"],
                    skipped_subscription_ids=[],
                    now=hard_rule_pipeline.datetime(2026, 4, 14, 12, 0, tzinfo=hard_rule_pipeline.timezone.utc),
                )

            self.assertEqual(result.item_count, 1)
            payload = json.loads((run_dir / "hard-rule-briefing.json").read_text(encoding="utf-8"))
            self.assertEqual([item["title"] for item in payload["items"]], ["Recent paper"])

    def test_hard_rule_briefing_strips_forbidden_fields(self) -> None:
        payload = hard_rule_pipeline.build_payload(
            [
                {
                    "subscription_id": "arxiv:agent-memory",
                    "source": "arxiv",
                    "topic": "agent memory",
                    "title": "Paper",
                    "summary": "Paper summary",
                    "link": "https://arxiv.org/abs/1234.5678",
                    "published_at": "2026-04-10T00:00:00Z",
                    "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/1234.5678",
                    "score": 9,
                    "why_recommended": "forbidden",
                    "feedback": "forbidden",
                }
            ],
            "run-123",
        )
        item = payload["items"][0]
        self.assertNotIn("score", item)
        self.assertNotIn("why_recommended", item)
        self.assertNotIn("feedback", item)

    def test_build_hard_rule_outputs_generates_separate_payloads(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-456"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "hard-rule-briefing.json").write_text(
                json.dumps(
                    {
                        "run_id": "run-456",
                        "generated_at": "2026-04-10T00:00:00+00:00",
                        "track": "hard_rule",
                        "items": [
                            {
                                "subscription_id": "producthunt:agents",
                                "source": "producthunt",
                                "topic": "agent tools",
                                "title": "Agent App",
                                "summary": "A new launch",
                                "link": "https://www.producthunt.com/products/agent-app",
                                "published_at": "",
                                "dedup_key": "hard-rule:producthunt:agent-app",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            mocked = hard_rule_pipeline.HardRuleRunResult(
                state="success",
                reason="refreshed",
                item_count=1,
                processed_subscription_ids=["producthunt:agents"],
                skipped_subscription_ids=[],
                artifact_paths=[str(run_dir / "hard-rule-briefing.json"), str(run_dir / "hard-rule-briefing.md")],
            )
            with patch.object(hard_rule_pipeline, "run_hard_rule_subscriptions", return_value=mocked):
                run_active_stack.build_hard_rule_outputs(
                    {"output_skills": ["output/notion-hard-rules", "output/feishu-hard-rules"]},
                    "run-456",
                    run_dir,
                )

            self.assertTrue((run_dir / "hard-rule-notion-payload.json").exists())
            self.assertTrue((run_dir / "hard-rule-feishu-payload.json").exists())

    def test_build_hard_rule_outputs_contains_failures_without_breaking_main_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-789"
            run_dir.mkdir(parents=True, exist_ok=True)
            with patch.object(hard_rule_pipeline, "run_hard_rule_subscriptions", side_effect=RuntimeError("network boom")):
                result = run_active_stack.build_hard_rule_outputs(
                    {"output_skills": ["output/notion-hard-rules"]},
                    "run-789",
                    run_dir,
                )

            self.assertEqual(result["state"], "failed")
            payload = json.loads((run_dir / "hard-rule-result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "failed")
            self.assertIn("network boom", payload["reason"])

    def test_build_hard_rule_outputs_contains_builder_failures_without_breaking_main_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = Path(tmp) / "run-790"
            run_dir.mkdir(parents=True, exist_ok=True)
            (run_dir / "hard-rule-briefing.json").write_text(
                json.dumps({"run_id": "run-790", "generated_at": "2026-04-10T00:00:00+00:00", "track": "hard_rule", "items": []}),
                encoding="utf-8",
            )
            mocked = hard_rule_pipeline.HardRuleRunResult(
                state="success",
                reason="refreshed",
                item_count=0,
                processed_subscription_ids=[],
                skipped_subscription_ids=[],
                artifact_paths=[str(run_dir / "hard-rule-briefing.json")],
            )
            with (
                patch.object(hard_rule_pipeline, "run_hard_rule_subscriptions", return_value=mocked),
                patch.object(run_active_stack, "run_python", side_effect=RuntimeError("builder boom")),
            ):
                result = run_active_stack.build_hard_rule_outputs(
                    {"output_skills": ["output/notion-hard-rules"]},
                    "run-790",
                    run_dir,
                )

            self.assertEqual(result["state"], "failed")
            payload = json.loads((run_dir / "hard-rule-result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "failed")
            self.assertIn("builder boom", payload["reason"])

    def test_refresh_state_is_not_persisted_when_artifact_write_fails(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            run_dir = Path(tmp) / "run-124"
            run_dir.mkdir(parents=True, exist_ok=True)
            subscriptions_path = root / "hard-rules" / "subscriptions.json"
            subscriptions_path.parent.mkdir(parents=True, exist_ok=True)
            subscriptions_path.write_text(
                json.dumps(
                    {
                        "version": 1,
                        "subscriptions": [
                            {
                                "id": "arxiv:agent-memory",
                                "source": "arxiv",
                                "topic": "agent memory",
                                "top_n": 5,
                                "created_at": "2026-04-10T00:00:00+00:00",
                                "updated_at": "2026-04-10T00:00:00+00:00",
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )
            original_write_text = Path.write_text

            def failing_write_text(path_obj, text, *args, **kwargs):
                if path_obj.name == "hard-rule-briefing.json":
                    raise OSError("disk full")
                return original_write_text(path_obj, text, *args, **kwargs)

            with (
                patch.dict(os.environ, {"GTN_HOME": str(root)}),
                patch.object(
                    hard_rule_pipeline,
                    "fetch_subscription_items",
                    return_value=[
                        {
                            "subscription_id": "arxiv:agent-memory",
                            "source": "arxiv",
                            "topic": "agent memory",
                            "title": "Paper",
                            "summary": "Paper summary",
                            "link": "https://arxiv.org/abs/1234.5678",
                            "published_at": "2026-04-10T00:00:00Z",
                            "dedup_key": "hard-rule:arxiv:https://arxiv.org/abs/1234.5678",
                            "raw": "https://arxiv.org/abs/1234.5678",
                        }
                    ],
                ),
                patch.object(Path, "write_text", new=failing_write_text),
            ):
                with self.assertRaises(OSError):
                    hard_rule_pipeline.run_hard_rule_subscriptions("run-124", run_dir, run_dir / "hard-rule-result.json")

            refresh_state_path = root / "hard-rules" / "refresh-state.json"
            self.assertFalse(refresh_state_path.exists())

    def test_run_hard_rules_cli_can_finalize_prepared_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / ".gtn"
            run_dir = Path(tmp) / "run-prepared"
            run_dir.mkdir(parents=True, exist_ok=True)
            worklist_path = run_dir / "hard-rule-worklist.json"
            items_path = run_dir / "hard-rule-items.json"
            worklist_path.write_text(
                json.dumps(
                    {
                        "eligible_subscriptions": [
                            {
                                "id": "producthunt:agent-memory",
                                "source": "producthunt",
                                "topic": "agent memory",
                                "top_n": 5,
                            }
                        ],
                        "skipped_subscription_ids": [],
                    }
                ),
                encoding="utf-8",
            )
            items_path.write_text(
                json.dumps(
                    [
                        {
                            "subscription_id": "producthunt:agent-memory",
                            "source": "producthunt",
                            "topic": "agent memory",
                            "title": "Agent App",
                            "summary": "A new launch",
                            "link": "https://www.producthunt.com/products/agent-app",
                            "published_at": "",
                            "dedup_key": "hard-rule:producthunt:agent-app",
                            "raw": "https://www.producthunt.com/products/agent-app",
                        }
                    ]
                ),
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"GTN_HOME": str(root)}):
                old_argv = sys.argv[:]
                try:
                    sys.argv = [
                        "run_hard_rules.py",
                        "--run-id",
                        "run-prepared",
                        "--run-dir",
                        str(run_dir),
                        "--items-json",
                        str(items_path),
                        "--worklist-json",
                        str(worklist_path),
                        "--result-path",
                        str(run_dir / "hard-rule-result.json"),
                    ]
                    run_hard_rules_cli.main()
                finally:
                    sys.argv = old_argv

            payload = json.loads((run_dir / "hard-rule-result.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["state"], "success")
            self.assertEqual(payload["processed_subscription_ids"], ["producthunt:agent-memory"])
            self.assertTrue((run_dir / "hard-rule-briefing.json").exists())
            refresh = json.loads((root / "hard-rules" / "refresh-state.json").read_text(encoding="utf-8"))
            self.assertIn("producthunt:agent-memory", refresh["subscriptions"])
