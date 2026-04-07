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
        self.assertEqual(page["properties"]["Tags"], ["agents", "memory"])


if __name__ == "__main__":
    unittest.main()
