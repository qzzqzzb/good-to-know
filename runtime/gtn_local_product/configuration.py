from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import StateData

DEFAULT_TIER = "balanced"
DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "zh")
TIER_PRESETS: dict[str, dict[str, int]] = {
    "light": {
        "agent_sessions.lookback_hours": 72,
        "agent_sessions.max_entries": 20,
        "agent_sessions.max_observations_per_session": 6,
        "browser_history.lookback_hours": 24,
        "browser_history.max_entries": 20,
        "feishu.max_items": 10,
    },
    "balanced": {
        "agent_sessions.lookback_hours": 168,
        "agent_sessions.max_entries": 50,
        "agent_sessions.max_observations_per_session": 6,
        "browser_history.lookback_hours": 72,
        "browser_history.max_entries": 50,
        "feishu.max_items": 20,
    },
    "deep": {
        "agent_sessions.lookback_hours": 336,
        "agent_sessions.max_entries": 80,
        "agent_sessions.max_observations_per_session": 6,
        "browser_history.lookback_hours": 168,
        "browser_history.max_entries": 80,
        "feishu.max_items": 40,
    },
}

CONFIG_KEYS = ("tier", "language", "notion-page-url", "feishu-webhook-url")


def load_json(path: Path, default: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return dict(default)
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def normalize_tier(value: str | None) -> str:
    tier = (value or "").strip().lower() or DEFAULT_TIER
    if tier not in TIER_PRESETS:
        allowed = ", ".join(TIER_PRESETS)
        raise SystemExit(f"Unsupported tier '{value}'. Allowed values: {allowed}")
    return tier


def state_tier(state: StateData) -> str:
    return normalize_tier(getattr(state, "tier", DEFAULT_TIER))


def normalize_language(value: str | None) -> str:
    language = (value or "").strip().lower() or DEFAULT_LANGUAGE
    if language not in SUPPORTED_LANGUAGES:
        allowed = ", ".join(SUPPORTED_LANGUAGES)
        raise SystemExit(f"Unsupported language '{value}'. Allowed values: {allowed}")
    return language


def state_language(state: StateData) -> str:
    return normalize_language(getattr(state, "language", DEFAULT_LANGUAGE))


def context_settings_path(runtime_repo: Path) -> Path:
    return runtime_repo / "context" / "naive-context" / "settings.json"


def feishu_settings_path(runtime_repo: Path) -> Path:
    return runtime_repo / "output" / "feishu-briefing" / "settings.json"


def notion_settings_path(runtime_repo: Path) -> Path:
    return runtime_repo / "output" / "notion-briefing" / "settings.json"


def apply_tier_to_runtime(runtime_repo: Path, tier: str) -> None:
    resolved = normalize_tier(tier)
    preset = TIER_PRESETS[resolved]

    context_settings = load_json(context_settings_path(runtime_repo), {"features": {}})
    features = context_settings.setdefault("features", {})
    agent_sessions = features.setdefault("agent_sessions", {})
    browser_history = features.setdefault("browser_history", {})
    agent_sessions["lookback_hours"] = preset["agent_sessions.lookback_hours"]
    agent_sessions["max_entries"] = preset["agent_sessions.max_entries"]
    agent_sessions["max_observations_per_session"] = preset["agent_sessions.max_observations_per_session"]
    agent_sessions["observation_tier"] = resolved
    browser_history["lookback_hours"] = preset["browser_history.lookback_hours"]
    browser_history["max_entries"] = preset["browser_history.max_entries"]
    save_json(context_settings_path(runtime_repo), context_settings)

    feishu_settings = load_json(feishu_settings_path(runtime_repo), {})
    feishu_settings["max_items"] = preset["feishu.max_items"]
    save_json(feishu_settings_path(runtime_repo), feishu_settings)


def set_notion_page_url(runtime_repo: Path, page_url: str) -> None:
    settings = load_json(notion_settings_path(runtime_repo), {})
    settings["parent_page_url"] = page_url
    settings["database_url"] = ""
    save_json(notion_settings_path(runtime_repo), settings)


def set_feishu_webhook_url(runtime_repo: Path, webhook_url: str) -> None:
    settings = load_json(feishu_settings_path(runtime_repo), {})
    settings["webhook_url"] = webhook_url
    save_json(feishu_settings_path(runtime_repo), settings)


def get_config_value(runtime_repo: Path, state: StateData, key: str) -> str:
    if key == "tier":
        return state_tier(state)
    if key == "language":
        return state_language(state)
    if key == "notion-page-url":
        settings = load_json(notion_settings_path(runtime_repo), {})
        return str(settings.get("parent_page_url", "")).strip()
    if key == "feishu-webhook-url":
        settings = load_json(feishu_settings_path(runtime_repo), {})
        return str(settings.get("webhook_url", "")).strip()
    raise SystemExit(f"Unsupported config key '{key}'")
