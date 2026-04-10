from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

APP_DIR_ENV = "GTN_HOME"
DEFAULT_LAUNCH_AGENT_LABEL = "com.goodtoknow.gtn"
DEFAULT_RUNTIME_SUBDIR = "runtime/GoodToKnow"


@dataclass(frozen=True)
class GTNPaths:
    root: Path
    state_file: Path
    lock_file: Path
    logs_dir: Path
    runs_dir: Path
    status_dir: Path
    status_history_file: Path
    hard_rules_dir: Path
    hard_rule_subscriptions_file: Path
    hard_rule_refresh_state_file: Path
    runtime_dir: Path
    launch_agents_dir: Path
    launch_agent_path: Path

def default_root() -> Path:
    override = os.environ.get(APP_DIR_ENV)
    if override:
        return Path(override).expanduser().resolve()
    return Path.home() / ".gtn"

def resolve_paths(root: Path | None = None, runtime_dir: Path | None = None) -> GTNPaths:
    root_path = (root or default_root()).expanduser().resolve()
    runtime_path = runtime_dir.expanduser().resolve() if runtime_dir else root_path / DEFAULT_RUNTIME_SUBDIR
    launch_agents_dir = Path.home() / "Library" / "LaunchAgents"
    return GTNPaths(
        root=root_path,
        state_file=root_path / "state.json",
        lock_file=root_path / "lock.json",
        logs_dir=root_path / "logs",
        runs_dir=root_path / "runs",
        status_dir=root_path / "status",
        status_history_file=root_path / "status" / "history.json",
        hard_rules_dir=root_path / "hard-rules",
        hard_rule_subscriptions_file=root_path / "hard-rules" / "subscriptions.json",
        hard_rule_refresh_state_file=root_path / "hard-rules" / "refresh-state.json",
        runtime_dir=runtime_path,
        launch_agents_dir=launch_agents_dir,
        launch_agent_path=launch_agents_dir / f"{DEFAULT_LAUNCH_AGENT_LABEL}.plist",
    )

def ensure_directories(paths: GTNPaths) -> None:
    paths.root.mkdir(parents=True, exist_ok=True)
    paths.logs_dir.mkdir(parents=True, exist_ok=True)
    paths.runs_dir.mkdir(parents=True, exist_ok=True)
    paths.status_dir.mkdir(parents=True, exist_ok=True)
    paths.hard_rules_dir.mkdir(parents=True, exist_ok=True)
    paths.launch_agents_dir.mkdir(parents=True, exist_ok=True)
