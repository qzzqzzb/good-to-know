from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from runtime.gtn_local_product.prompting import render_prompt


class PromptingTests(unittest.TestCase):
    def test_render_prompt_mentions_active_output_payload_artifacts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = render_prompt(root, root / "repo-run", root / "app-run", "run-123")

        self.assertIn("output payload artifacts", prompt)
        self.assertIn("feishu-payload.json", prompt)
        self.assertIn("notion-payload.json", prompt)

    def test_render_prompt_defaults_to_english_recommendation_content(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = render_prompt(root, root / "repo-run", root / "app-run", "run-123")

        self.assertIn("Recommendation content language: `en`", prompt)
        self.assertIn("write recommendation content fields (`title`, `summary`, `why_recommended`, `digest`) in English".lower(), prompt.lower())
        self.assertIn("Do not localize operational text, status text, or downstream output labels/schema.", prompt)

    def test_render_prompt_supports_chinese_recommendation_content_without_localizing_labels(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = render_prompt(root, root / "repo-run", root / "app-run", "run-123", language="zh")

        self.assertIn("Recommendation content language: `zh`", prompt)
        self.assertIn("Chinese-first natural prose", prompt)
        self.assertIn("Keep necessary English product names, proper nouns, and terms", prompt)
        self.assertIn("Do not localize operational text, status text, or downstream output labels/schema.", prompt)

    def test_render_prompt_describes_codex_native_hard_rule_flow(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = render_prompt(root, root / "repo-run", root / "app-run", "run-123")

        self.assertIn("prepare_hard_rule_worklist.py", prompt)
        self.assertIn("hard-rule-items.json", prompt)
        self.assertIn("run_hard_rules.py --run-id", prompt)
        self.assertIn("runtime/codex-agent-loop/references/hard-rule-web-research.md", prompt)

    def test_render_prompt_requires_partial_success_on_auxiliary_publish_failure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            prompt = render_prompt(root, root / "repo-run", root / "app-run", "run-123")

        self.assertIn("do not keep investigating indefinitely", prompt)
        self.assertIn("partial-success result", prompt)
        self.assertIn("`partial_success` when the main local artifacts are complete but an auxiliary destination such as Feishu fails", prompt)


if __name__ == "__main__":
    unittest.main()
