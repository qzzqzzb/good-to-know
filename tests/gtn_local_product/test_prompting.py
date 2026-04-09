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


if __name__ == "__main__":
    unittest.main()
