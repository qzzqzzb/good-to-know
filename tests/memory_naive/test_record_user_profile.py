from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tests.memory_mempalace.helpers import load_memory_module


class RecordUserProfileTests(unittest.TestCase):
    def test_record_user_profile_updates_identity_and_stable_record(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            tmp_path = Path(tmp)
            memory_module = load_memory_module(tmp_path, name="mempalace_memory_profile")
            memory_module.record_user_profile("I care about agents and product design.")
            identity = (tmp_path / "identity.md").read_text(encoding="utf-8")
            self.assertIn("agents and product design", identity)

            memory_module.record_user_profile("I care about systems, AI products, and research.")
            updated = (tmp_path / "identity.md").read_text(encoding="utf-8")
            self.assertIn("systems, AI products, and research", updated)
            self.assertNotIn("agents and product design.", updated)


if __name__ == "__main__":
    unittest.main()
