from __future__ import annotations

import json
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, TypeVar

T = TypeVar("T")


def load_json(path: Path, default: T) -> T:
    if not path.exists():
        return default
    return json.loads(path.read_text(encoding="utf-8"))



def save_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    serializable = asdict(payload) if is_dataclass(payload) else payload
    path.write_text(json.dumps(serializable, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
