from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from runtime.gtn_local_product.status_data import (
    build_run_summary,
    compute_feedback_distribution,
    runtime_storage_bytes,
    top_profile_keywords,
    update_history_with_summary,
)


class StatusMetricsTests(unittest.TestCase):
    def test_build_run_summary_counts_findings_and_briefing_items(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app_run_dir = tmp_path / "app-run"
            repo_run_dir = tmp_path / "repo-run"
            app_run_dir.mkdir(parents=True)
            repo_run_dir.mkdir(parents=True)
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
            (repo_run_dir / "notion-payload.json").write_text("{}", encoding="utf-8")

            summary = build_run_summary(
                "run-1",
                app_run_dir,
                {"state": "success", "updated_at": "2026-04-10T00:00:00+00:00"},
                repo_run_dir=repo_run_dir,
            )

            self.assertEqual(summary["metrics"]["records_scanned"], 3)
            self.assertEqual(summary["metrics"]["webpages_searched"], 2)
            self.assertEqual(summary["metrics"]["recommendations_produced"], 2)
            self.assertTrue(summary["published"])

    def test_build_run_summary_does_not_count_publish_without_output_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            app_run_dir = tmp_path / "app-run"
            repo_run_dir = tmp_path / "repo-run"
            app_run_dir.mkdir(parents=True)
            repo_run_dir.mkdir(parents=True)
            (repo_run_dir / "memory-findings.json").write_text(
                json.dumps([{"source": "web_search"}]),
                encoding="utf-8",
            )
            (repo_run_dir / "briefing.json").write_text(
                json.dumps({"items": [{"title": "A"}]}),
                encoding="utf-8",
            )

            summary = build_run_summary(
                "run-2",
                app_run_dir,
                {"state": "success", "updated_at": "2026-04-10T00:00:00+00:00"},
                repo_run_dir=repo_run_dir,
            )

            self.assertFalse(summary["published"])

    def test_update_history_with_summary_ignores_duplicate_run_ids(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history.json"
            summary = {
                "run_id": "run-1",
                "published": True,
                "metrics": {"recommendations_produced": 4},
            }

            payload = update_history_with_summary(history_path, summary)
            payload = update_history_with_summary(history_path, summary)

            self.assertEqual(payload["totals"]["push_count"], 1)
            self.assertEqual(payload["totals"]["pushed_recommendations_total"], 4)
            self.assertEqual(payload["aggregated_run_ids"], ["run-1"])

    def test_compute_feedback_distribution_counts_known_states(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_repo = Path(tmp)
            settings_dir = runtime_repo / "output" / "notion-briefing"
            settings_dir.mkdir(parents=True)
            (settings_dir / "settings.json").write_text(
                json.dumps({"default_status": "No feedback"}),
                encoding="utf-8",
            )
            (settings_dir / "page_index.json").write_text(
                json.dumps(
                    {
                        "default_status": "No feedback",
                        "pages": {
                            "a": {"last_seen_status": "No feedback"},
                            "b": {"last_seen_status": "Good to know"},
                            "c": {"last_seen_status": "Bad recommendation"},
                            "d": {"last_seen_status": "Good to know"},
                        },
                    }
                ),
                encoding="utf-8",
            )

            counts = compute_feedback_distribution(runtime_repo)

            self.assertEqual(counts["No feedback"], 1)
            self.assertEqual(counts["Good to know"], 2)
            self.assertEqual(counts["Bad recommendation"], 1)

    def test_top_profile_keywords_uses_profile_and_context_text(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_repo = Path(tmp)
            user_context = runtime_repo / "memory" / "naive-memory" / "user_context.md"
            context_outbox = runtime_repo / "context" / "naive-context" / "outbox.md"
            user_context.parent.mkdir(parents=True)
            context_outbox.parent.mkdir(parents=True)
            user_context.write_text("AI agents product research agents.\n", encoding="utf-8")
            context_outbox.write_text("Systems product agents research.\n", encoding="utf-8")

            keywords = dict(top_profile_keywords(runtime_repo, limit=4))

            self.assertGreaterEqual(keywords.get("agents", 0), 3)
            self.assertGreaterEqual(keywords.get("product", 0), 2)

    def test_runtime_storage_bytes_ignores_symlink_targets(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            runtime_repo = tmp_path / "runtime"
            runtime_repo.mkdir()
            local_file = runtime_repo / "state.json"
            local_file.write_text("12345", encoding="utf-8")
            external = tmp_path / "external.txt"
            external.write_text("x" * 100, encoding="utf-8")
            (runtime_repo / "linked.txt").symlink_to(external)

            self.assertEqual(runtime_storage_bytes(runtime_repo), 5)


if __name__ == "__main__":
    unittest.main()
