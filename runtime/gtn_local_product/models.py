from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class ResultState(str, Enum):
    RUNNING = "running"
    SUCCESS = "success"
    PARTIAL_SUCCESS = "partial_success"
    BLOCKED_MISSING_CODEX_BINARY = "blocked_missing_codex_binary"
    BLOCKED_MISSING_CODEX_AUTH = "blocked_missing_codex_auth"
    BLOCKED_MISSING_SEARCH_CAPABILITY = "blocked_missing_search_capability"
    BLOCKED_MISSING_NOTION_AUTH = "blocked_missing_notion_auth"
    FAILED_PREFLIGHT = "failed_preflight"
    FAILED = "failed"


@dataclass
class LockInfo:
    pid: int
    run_id: str
    runtime_repo_path: str
    started_at: str
    trigger: str


@dataclass
class StateData:
    runtime_repo_path: str = ""
    runtime_bundle_url: str = ""
    codex_path: str = ""
    cadence: str = ""
    enabled: bool = False
    launch_agent_label: str = "com.goodtoknow.gtn"
    launch_agent_path: str = ""
    initialized_at: str = ""


@dataclass
class ManifestData:
    run_id: str
    trigger: str
    state: str
    started_at: str
    finished_at: str | None = None
    runtime_repo_path: str = ""
    repo_run_dir: str = ""
    app_run_dir: str = ""
    result_path: str = ""
    last_message_path: str = ""
    log_path: str = ""
    error: str | None = None
    details: dict[str, Any] = field(default_factory=dict)
