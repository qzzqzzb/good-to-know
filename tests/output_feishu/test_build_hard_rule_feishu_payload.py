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


module = load_module(ROOT / "output/feishu-hard-rules/scripts/build_payload.py", "build_hard_rule_feishu_payload")


class BuildHardRuleFeishuPayloadTests(unittest.TestCase):
    def test_build_payload_formats_without_score_or_why(self) -> None:
        settings = {
            "webhook_url": "",
            "message_title": "Intended Recommendations",
            "required_keyword": "[GTN]",
            "max_items": 2,
        }
        briefing = {
            "run_id": "run-123",
            "generated_at": "2026-04-10T00:00:00+00:00",
            "items": [
                {
                    "title": "First item",
                    "source": "arxiv",
                    "topic": "agent memory",
                    "summary": "A short summary.",
                    "link": "https://example.com/1",
                }
            ],
        }
        payload = module.build_payload(briefing, settings)
        text = payload["message"]["content"]["text"]
        self.assertIn("First item", text)
        self.assertIn("Source: arxiv", text)
        self.assertIn("Topic: agent memory", text)
        self.assertNotIn("/10", text)
        self.assertNotIn("Why now:", text)
