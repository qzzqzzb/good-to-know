from __future__ import annotations

import importlib.util
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


module = load_module(ROOT / "memory/naive-memory/scripts/record_user_profile.py", "record_user_profile")


class RecordUserProfileTests(unittest.TestCase):
    def test_upsert_profile_replaces_previous_profile(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            memory_path = Path(tmp) / "user_context.md"
            memory_path.write_text("# User Context Memory\n\n", encoding="utf-8")
            module.upsert_profile(memory_path, "I care about agents and product design.")
            first = memory_path.read_text(encoding="utf-8")
            self.assertIn("manual_profile:primary", first)
            self.assertIn("agents and product design", first)

            module.upsert_profile(memory_path, "I care about systems, AI products, and research.")
            second = memory_path.read_text(encoding="utf-8")
            self.assertIn("systems, AI products, and research", second)
            self.assertNotIn("agents and product design.", second)


if __name__ == "__main__":
    unittest.main()
