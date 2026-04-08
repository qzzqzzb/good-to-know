from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
MEMORY_MODULE_PATH = ROOT / "memory/mempalace-memory/module_lib.py"


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def configure_memory_env(tmp_path: Path) -> dict[str, str]:
    data_dir = tmp_path / "module-data"
    palace_dir = data_dir / "palace"
    identity_path = tmp_path / "identity.md"
    config_path = data_dir / "config.json"
    env = {
        "GTN_MEMPALACE_DATA_DIR": str(data_dir),
        "GTN_MEMPALACE_PALACE_DIR": str(palace_dir),
        "GTN_MEMPALACE_IDENTITY_PATH": str(identity_path),
        "GTN_MEMPALACE_CONFIG_PATH": str(config_path),
        "ANONYMIZED_TELEMETRY": "FALSE",
    }
    os.environ.update(env)
    return env


def load_memory_module(tmp_path: Path, name: str = "mempalace_memory_module"):
    configure_memory_env(tmp_path)
    return load_module(MEMORY_MODULE_PATH, name)
