from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

from runtime.gtn_local_product.configuration import apply_tier_to_runtime

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


agent_sessions = load_module(
    ROOT / "context/naive-context/scripts/collectors/agent_sessions.py",
    "context_agent_sessions",
)


class ConfigTierTests(unittest.TestCase):
    def test_scaled_session_observation_cap_varies_by_length_and_tier(self) -> None:
        self.assertEqual(agent_sessions.scaled_session_observation_cap(100, "light"), 1)
        self.assertEqual(agent_sessions.scaled_session_observation_cap(280, "balanced"), 2)
        self.assertEqual(agent_sessions.scaled_session_observation_cap(500, "deep"), 4)
        self.assertEqual(agent_sessions.scaled_session_observation_cap(1200, "light"), 4)
        self.assertEqual(agent_sessions.scaled_session_observation_cap(2500, "deep"), 6)

    def test_apply_tier_to_runtime_writes_observation_tier_and_density(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            runtime_repo = Path(tmp)
            context_settings = runtime_repo / "context" / "naive-context" / "settings.json"
            feishu_settings = runtime_repo / "output" / "feishu-briefing" / "settings.json"
            context_settings.parent.mkdir(parents=True, exist_ok=True)
            feishu_settings.parent.mkdir(parents=True, exist_ok=True)
            context_settings.write_text(
                '{"features":{"agent_sessions":{},"browser_history":{}}}',
                encoding="utf-8",
            )
            feishu_settings.write_text("{}", encoding="utf-8")

            apply_tier_to_runtime(runtime_repo, "deep")

            updated_context = context_settings.read_text(encoding="utf-8")
            updated_feishu = feishu_settings.read_text(encoding="utf-8")
            self.assertIn('"observation_tier": "deep"', updated_context)
            self.assertIn('"max_observations_per_session": 6', updated_context)
            self.assertIn('"max_items": 40', updated_feishu)


if __name__ == "__main__":
    unittest.main()
