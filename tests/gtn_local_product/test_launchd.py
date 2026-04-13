from __future__ import annotations

import plistlib
import tempfile
import unittest
from pathlib import Path

from runtime.gtn_local_product.launchd import render_launch_agent_plist
from runtime.gtn_local_product.paths import resolve_paths


class LaunchdTests(unittest.TestCase):
    def test_plist_contains_absolute_program_arguments(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            paths = resolve_paths(root=Path(tmp), runtime_dir=Path(tmp) / "runtime" / "GoodToKnow")
            gtn_path = Path(tmp) / "bin" / "gtn"
            gtn_path.parent.mkdir(parents=True, exist_ok=True)
            gtn_path.write_text("#!/bin/sh\n", encoding="utf-8")
            payload = plistlib.loads(render_launch_agent_plist(paths, gtn_path, 3600))
            self.assertEqual(payload["Label"], "com.goodtoknow.gtn")
            self.assertNotIn("StartInterval", payload)
            self.assertEqual(payload["StartCalendarInterval"][0], {"Hour": 0, "Minute": 0})
            self.assertTrue(payload["RunAtLoad"])
            self.assertEqual(Path(payload["ProgramArguments"][0]), gtn_path.resolve())
            self.assertEqual(payload["ProgramArguments"][1:4], ["-m", "runtime.gtn_local_product", "--root"])
            self.assertEqual(payload["ProgramArguments"][4], str(paths.root))
            self.assertEqual(payload["ProgramArguments"][5:], ["run", "--scheduled"])
            self.assertEqual(payload["EnvironmentVariables"]["GTN_HOME"], str(paths.root))


if __name__ == "__main__":
    unittest.main()
