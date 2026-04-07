from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from .cadence import parse_cadence
from .paths import DEFAULT_LAUNCH_AGENT_LABEL, GTNPaths


DEFAULT_STATE: dict[str, Any] = {
    "enabled": False,
    "cadence": None,
    "codex_path": None,
    "launch_agent_label": DEFAULT_LAUNCH_AGENT_LABEL,
    "launch_agent_path": None,
    "updated_at": None,
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def load_state(paths: GTNPaths) -> dict[str, Any]:
    state = load_json(paths.state_file, DEFAULT_STATE)
    state.setdefault("launch_agent_label", DEFAULT_LAUNCH_AGENT_LABEL)
    state.setdefault("launch_agent_path", str(paths.launch_agent_path))
    return state


def save_state(paths: GTNPaths, state: dict[str, Any]) -> None:
    state["updated_at"] = now_iso()
    state.setdefault("launch_agent_label", DEFAULT_LAUNCH_AGENT_LABEL)
    state.setdefault("launch_agent_path", str(paths.launch_agent_path))
    save_json(paths.state_file, state)


def next_run_estimate(state: dict[str, Any], last_run_time: str | None) -> str | None:
    cadence = state.get("cadence")
    if not cadence:
        return None
    _, seconds = parse_cadence(cadence)
    anchor = last_run_time or state.get("updated_at")
    if not anchor:
        return None
    started = datetime.fromisoformat(str(anchor).replace("Z", "+00:00"))
    return (started + timedelta(seconds=seconds)).isoformat(timespec="seconds")



def is_lock_stale(lock: dict[str, Any], now: datetime | None = None, stale_after_seconds: int = 300) -> bool:
    current = now or datetime.now(timezone.utc).astimezone()
    pid = int(lock.get("pid", -1))
    started_at_raw = str(lock.get("started_at", "")).strip()
    if pid <= 0 or not started_at_raw:
        return False
    try:
        started = datetime.fromisoformat(started_at_raw.replace("Z", "+00:00"))
    except ValueError:
        return False
    try:
        import os
        os.kill(pid, 0)
        return False
    except OSError:
        return (current - started).total_seconds() > stale_after_seconds
