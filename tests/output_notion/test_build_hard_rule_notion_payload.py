from __future__ import annotations

import importlib.util
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_module(ROOT / "output/notion-hard-rules/scripts/build_notion_payload.py", "build_hard_rule_notion_payload")


class BuildHardRuleNotionPayloadTests(unittest.TestCase):
    def test_build_page_payload_omits_score_and_status_fields(self) -> None:
        settings = {
            "visible_properties": {
                "title": "Title",
                "url": "URL",
                "source": "Source",
                "topic": "Topic",
                "published_at": "Published At",
                "summary": "Summary",
            },
            "hidden_properties": {"dedup_key": "Dedup Key"},
        }
        item = {
            "dedup_key": "hard-rule:1",
            "title": "Example",
            "link": "https://example.com",
            "source": "arxiv",
            "topic": "agent memory",
            "published_at": "2026-04-10",
            "summary": "Summary",
        }
        page = module.build_page_payload(item, settings)
        self.assertEqual(page["properties"]["Source"], "arxiv")
        self.assertNotIn("Score", page["properties"])
        self.assertNotIn("Status", page["properties"])

    def test_load_settings_does_not_inherit_main_database_url(self) -> None:
        settings_path = module.SETTINGS_PATH
        main_settings_path = module.MAIN_SETTINGS_PATH
        original_settings = settings_path.read_text(encoding="utf-8")
        original_main = main_settings_path.read_text(encoding="utf-8")
        try:
            settings_path.write_text(
                '{"database_name":"GTN Intended Recommendations","database_url":"","parent_page_url":"","visible_properties":{},"hidden_properties":{}}',
                encoding="utf-8",
            )
            main_settings_path.write_text(
                '{"database_url":"https://notion.local/db-main","parent_page_url":"https://notion.local/page-main"}',
                encoding="utf-8",
            )
            settings = module.load_settings()
        finally:
            settings_path.write_text(original_settings, encoding="utf-8")
            main_settings_path.write_text(original_main, encoding="utf-8")

        self.assertEqual(settings["database_url"], "")
        self.assertEqual(settings["parent_page_url"], "https://notion.local/page-main")
