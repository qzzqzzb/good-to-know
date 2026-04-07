import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ApplyPublishResultsTests(unittest.TestCase):
    def test_apply_publish_results_updates_index(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            index = tmp_path / "page_index.json"
            index.write_text('{"default_status":"No feedback","pages":{}}', encoding="utf-8")
            payload = tmp_path / "publish-results.json"
            payload.write_text(
                json.dumps(
                    {
                        "pages": [
                            {
                                "dedup_key": "abc",
                                "page_id": "page-1",
                                "url": "https://www.notion.so/page-1",
                                "title": "Example",
                                "status_seen": "No feedback",
                                "matched_existing": True,
                                "publish_outcome": "updated",
                            }
                        ]
                    }
                ),
                encoding="utf-8",
            )
            subprocess.run(
                [
                    sys.executable,
                    "output/notion-briefing/scripts/apply_publish_results.py",
                    str(payload),
                    "--index-path",
                    str(index),
                ],
                check=True,
            )
            updated = json.loads(index.read_text(encoding="utf-8"))
            self.assertIn("abc", updated["pages"])
            self.assertEqual(updated["pages"]["abc"]["page_id"], "page-1")


if __name__ == "__main__":
    unittest.main()
