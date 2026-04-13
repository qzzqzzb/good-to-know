from __future__ import annotations

import importlib.util
import json
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_module(ROOT / "output/notion-briefing/scripts/build_notion_payload.py", "build_notion_payload")


class BuildNotionPayloadTests(unittest.TestCase):
    def test_score_becomes_property_not_tag(self) -> None:
        settings = {
            "visible_properties": {
                "title": "Title",
                "url": "URL",
                "score": "Score",
                "summary": "Summary",
                "tags": "Tags",
                "status": "Status",
            },
            "hidden_properties": {"dedup_key": "Dedup Key"},
            "default_status": "No feedback",
        }
        item = {
            "dedup_key": "abc",
            "title": "Example",
            "raw": "https://example.com",
            "score": 8,
            "summary": "Summary",
            "why_recommended": "Why",
            "digest": "Digest",
            "tags": ["agents", "memory"],
        }
        page = module.build_page_payload(item, settings)
        self.assertEqual(page["properties"]["Score"], 8)
        self.assertEqual(page["properties"]["Tags"], "agents, memory")

    def test_build_payload_includes_parent_object_and_publish_hints(self) -> None:
        settings = {
            "database_name": "GoodToKnow Recommendations",
            "database_url": "",
            "parent_page_url": "https://www.notion.so/GoodToKnow-33a9117faab880e4b51dc393ef817151",
            "visible_properties": {
                "title": "Title",
                "url": "URL",
                "score": "Score",
                "summary": "Summary",
                "tags": "Tags",
                "status": "Status",
            },
            "hidden_properties": {"dedup_key": "Dedup Key"},
            "default_status": "No feedback",
        }
        payload = module.build_payload({"run_id": "run-1", "generated_at": "2026-04-11T00:00:00+00:00", "items": []}, settings)
        self.assertEqual(
            payload["database"]["parent"],
            {"type": "page_id", "page_id": "33a9117f-aab8-80e4-b51d-c393ef817151"},
        )
        self.assertEqual(payload["publish_hints"]["tags_property_encoding"], "comma_separated_string")

    def test_build_payload_skips_rows_already_indexed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            index_path = tmp_path / "page_index.json"
            index_path.write_text(
                json.dumps(
                    {
                        "pages": {
                            "abc": {
                                "page_id": "page-1",
                                "url": "https://www.notion.so/page-1",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            original_index_path = module.INDEX_PATH
            module.INDEX_PATH = index_path
            try:
                payload = module.build_payload(
                    {
                        "run_id": "run-1",
                        "generated_at": "2026-04-11T00:00:00+00:00",
                        "items": [
                            {
                                "dedup_key": "abc",
                                "title": "Existing",
                                "raw": "https://example.com/1",
                                "score": 8,
                                "summary": "Summary",
                                "why_recommended": "Why",
                                "digest": "Digest",
                                "tags": ["agents"],
                            },
                            {
                                "dedup_key": "new",
                                "title": "New",
                                "raw": "https://example.com/2",
                                "score": 7,
                                "summary": "Summary",
                                "why_recommended": "Why",
                                "digest": "Digest",
                                "tags": ["memory"],
                            },
                        ],
                    },
                    {
                        "database_name": "GoodToKnow Recommendations",
                        "database_url": "",
                        "parent_page_url": "",
                        "visible_properties": {
                            "title": "Title",
                            "url": "URL",
                            "score": "Score",
                            "summary": "Summary",
                            "tags": "Tags",
                            "status": "Status",
                        },
                        "hidden_properties": {"dedup_key": "Dedup Key"},
                        "default_status": "No feedback",
                    },
                )
            finally:
                module.INDEX_PATH = original_index_path

        self.assertEqual(len(payload["pages"]), 1)
        self.assertEqual(payload["pages"][0]["dedup_key"], "new")
        self.assertEqual(payload["publish_hints"]["existing_row_policy"], "skip_update_for_indexed_rows")
        self.assertEqual(payload["publish_hints"]["skipped_existing_dedup_keys"], ["abc"])

    def test_render_page_body_normalizes_wrapped_text_and_includes_tags(self) -> None:
        item = {
            "score": 8,
            "summary": "Summary text",
            "why_recommended": "This line wraps\n\nin odd ways\nfor no reason.",
            "digest": "Digest also\nhas broken\nline wrapping.",
            "tags": ["agents", "memory"],
        }
        body = module.render_page_body(item)
        self.assertIn("This line wraps in odd ways for no reason.", body)
        self.assertIn("Digest also has broken line wrapping.", body)
        self.assertIn("## Tags", body)
        self.assertIn("agents, memory", body)


if __name__ == "__main__":
    unittest.main()
