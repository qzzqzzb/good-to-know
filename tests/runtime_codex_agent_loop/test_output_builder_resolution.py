from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


run_active_stack = load_module(
    ROOT / "runtime/codex-agent-loop/scripts/run_active_stack.py",
    "run_active_stack_output_builder_resolution",
)


class OutputBuilderResolutionTests(unittest.TestCase):
    def test_prefers_generic_build_payload(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp)
            scripts = skill_path / "scripts"
            scripts.mkdir(parents=True)
            generic = scripts / "build_payload.py"
            legacy = scripts / "build_notion_payload.py"
            generic.write_text("# generic\n", encoding="utf-8")
            legacy.write_text("# legacy\n", encoding="utf-8")

            resolved = run_active_stack.resolve_output_builder(skill_path)

            self.assertEqual(resolved, generic)

    def test_supports_legacy_notion_builder(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            skill_path = Path(tmp)
            scripts = skill_path / "scripts"
            scripts.mkdir(parents=True)
            legacy = scripts / "build_notion_payload.py"
            legacy.write_text("# legacy\n", encoding="utf-8")

            resolved = run_active_stack.resolve_output_builder(skill_path)

            self.assertEqual(resolved, legacy)


if __name__ == "__main__":
    unittest.main()
