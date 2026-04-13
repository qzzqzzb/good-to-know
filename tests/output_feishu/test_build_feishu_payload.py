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


module = load_module(ROOT / "output/feishu-briefing/scripts/build_payload.py", "build_feishu_payload")


class BuildFeishuPayloadTests(unittest.TestCase):
    def test_build_payload_formats_group_readable_text(self) -> None:
        settings = {
            "webhook_url": "",
            "message_title": "Daily Digest",
            "required_keyword": "[GTN]",
            "max_items": 2,
        }
        briefing = {
            "run_id": "run-123",
            "generated_at": "2026-04-09T16:00:00+08:00",
            "memory_wakeup": "Wake up",
            "items": [
                {
                    "title": "First item",
                    "score": 9,
                    "summary": "A short summary.",
                    "why_recommended": "It matters now.",
                    "digest": "A longer digest.",
                    "raw": "https://example.com/1",
                },
                {
                    "title": "Second item",
                    "score": 7,
                    "summary": "Second summary.",
                    "why_recommended": "Still useful.",
                    "digest": "",
                    "raw": "https://example.com/2",
                },
                {
                    "title": "Third item",
                    "score": 6,
                    "summary": "Ignored by max_items.",
                    "why_recommended": "Not shown.",
                    "digest": "",
                    "raw": "https://example.com/3",
                },
            ],
            "warnings": {"missing_score_entry_ids": []},
        }

        payload = module.build_payload(briefing, settings)

        self.assertEqual(payload["destination"]["type"], "feishu_custom_bot_webhook")
        self.assertFalse(payload["destination"]["webhook_configured"])
        text = payload["message"]["content"]["text"]
        self.assertIn("[GTN]", text)
        self.assertIn("Daily Digest", text)
        self.assertIn("1. First item (9/10)", text)
        self.assertIn("Why now: It matters now.", text)
        self.assertIn("Digest: A longer digest.", text)
        self.assertIn("2. Second item (7/10)", text)
        self.assertNotIn("3. Third item", text)

    def test_render_message_text_truncates_to_safe_length(self) -> None:
        briefing = {
            "run_id": "run-123",
            "generated_at": "2026-04-09T16:00:00+08:00",
            "items": [
                {
                    "title": "超长条目",
                    "score": 8,
                    "summary": "摘要" * 3_000,
                    "why_recommended": "原因" * 3_000,
                    "digest": "内容" * 8_000,
                    "raw": "https://example.com",
                }
                for _ in range(50)
            ],
            "warnings": {"missing_score_entry_ids": []},
        }

        payload = module.build_payload(briefing, {"max_items": 100, "message_title": "Digest"})
        body_size = module.message_body_size(payload["message"])

        self.assertLessEqual(body_size, module.MAX_REQUEST_BODY_BYTES)
        self.assertLess(payload["source"]["rendered_item_count"], 21)
        self.assertTrue(payload["message"]["content"]["text"].endswith("\n"))

    def test_build_payload_keeps_english_labels_when_content_is_chinese(self) -> None:
        settings = {
            "webhook_url": "",
            "message_title": "GoodToKnow Briefing",
            "required_keyword": "",
            "max_items": 1,
        }
        briefing = {
            "run_id": "run-zh",
            "generated_at": "2026-04-13T09:00:00+08:00",
            "items": [
                {
                    "title": "示例推荐",
                    "score": 8,
                    "summary": "这是一段中文 summary。",
                    "why_recommended": "因为你最近在看 agent 和 product system 相关内容。",
                    "digest": "更长一点的中文 digest。",
                    "raw": "https://example.com/zh",
                }
            ],
            "warnings": {"missing_score_entry_ids": []},
        }

        payload = module.build_payload(briefing, settings)
        text = payload["message"]["content"]["text"]

        self.assertIn("Summary: 这是一段中文 summary。", text)
        self.assertIn("Why now: 因为你最近在看 agent 和 product system 相关内容。", text)
        self.assertIn("Digest: 更长一点的中文 digest。", text)


if __name__ == "__main__":
    unittest.main()
