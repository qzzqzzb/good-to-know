from __future__ import annotations

import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from runtime.gtn_local_product.hard_rule_config import (
    build_subscriptions_from_sources,
    load_refresh_state,
    load_subscriptions,
    parse_topic_overrides,
    save_refresh_state,
    should_refresh_hard_rules,
)
from runtime.gtn_local_product.paths import resolve_paths


class HardRuleConfigTests(unittest.TestCase):
    def test_build_subscriptions_normalizes_one_record_per_source(self) -> None:
        subscriptions = build_subscriptions_from_sources(
            ["arxiv", "producthunt"],
            "agent memory",
            {"producthunt": "agent tools"},
        )
        self.assertEqual(len(subscriptions), 2)
        self.assertEqual({item["source"] for item in subscriptions}, {"arxiv", "producthunt"})
        topics = {item["source"]: item["topic"] for item in subscriptions}
        self.assertEqual(topics["arxiv"], "agent memory")
        self.assertEqual(topics["producthunt"], "agent tools")

    def test_parse_topic_overrides_requires_source_equals_topic(self) -> None:
        overrides = parse_topic_overrides(["arxiv=agent memory"])
        self.assertEqual(overrides, {"arxiv": "agent memory"})
        with self.assertRaises(SystemExit):
            parse_topic_overrides(["arxiv"])

    def test_refresh_state_round_trips_and_daily_gate_skips_fresh_runs(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths(root=Path(tmp))
            save_refresh_state(
                paths,
                {
                    "subscriptions": {
                        "arxiv:agent-memory": {
                            "last_refreshed_at": "2026-04-10T00:00:00+00:00",
                        }
                    }
                },
            )
            payload = load_refresh_state(paths)
            self.assertIn("arxiv:agent-memory", payload["subscriptions"])

        current_time = datetime(2026, 4, 10, 12, 0, tzinfo=timezone.utc)
        self.assertFalse(should_refresh_hard_rules("2026-04-10T00:00:00+00:00", now=current_time))
        self.assertTrue(
            should_refresh_hard_rules(
                "2026-04-09T00:00:00+00:00",
                now=current_time + timedelta(hours=1),
            )
        )

    def test_load_subscriptions_ignores_invalid_records(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths(root=Path(tmp))
            paths.hard_rule_subscriptions_file.parent.mkdir(parents=True, exist_ok=True)
            paths.hard_rule_subscriptions_file.write_text(
                '{"version": 1, "subscriptions": [{"source": "arxiv", "topic": "memory"}, {"source": "", "topic": "bad"}]}',
                encoding="utf-8",
            )
            subscriptions = load_subscriptions(paths)
            self.assertEqual(len(subscriptions), 1)
            self.assertEqual(subscriptions[0]["source"], "arxiv")
