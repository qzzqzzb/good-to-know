from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
from typing import Any

from .paths import GTNPaths
from .storage import load_json, save_json

HARD_RULES_SCHEMA_VERSION = 1
HARD_RULE_REFRESH_SCHEMA_VERSION = 1
DEFAULT_TOP_N = 5
MIN_TOP_N = 3
MAX_TOP_N = 5
DEFAULT_TRACK_LABEL = "Intended Recommendations"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


@dataclass(frozen=True)
class HardRuleSource:
    source_id: str
    label: str
    description: str


SUPPORTED_HARD_RULE_SOURCES = (
    HardRuleSource(
        source_id="arxiv",
        label="arXiv",
        description="Recent papers for a topic-driven research feed.",
    ),
    HardRuleSource(
        source_id="producthunt",
        label="Product Hunt",
        description="Recent launches for a topic-driven product discovery feed.",
    ),
)
SUPPORTED_SOURCE_IDS = {item.source_id for item in SUPPORTED_HARD_RULE_SOURCES}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def load_subscriptions(paths: GTNPaths) -> list[dict[str, Any]]:
    payload = load_json(paths.hard_rule_subscriptions_file, {"version": HARD_RULES_SCHEMA_VERSION, "subscriptions": []})
    subscriptions = payload.get("subscriptions", [])
    if not isinstance(subscriptions, list):
        return []
    cleaned: list[dict[str, Any]] = []
    for item in subscriptions:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source", "")).strip()
        topic = str(item.get("topic", "")).strip()
        if not source or not topic:
            continue
        cleaned.append(normalize_subscription(item))
    return cleaned


def save_subscriptions(paths: GTNPaths, subscriptions: list[dict[str, Any]]) -> None:
    normalized = [normalize_subscription(item) for item in subscriptions]
    normalized.sort(key=lambda item: (str(item.get("source", "")), str(item.get("topic", "")).lower()))
    save_json(
        paths.hard_rule_subscriptions_file,
        {
            "version": HARD_RULES_SCHEMA_VERSION,
            "track_label": DEFAULT_TRACK_LABEL,
            "subscriptions": normalized,
        },
    )


def load_refresh_state(paths: GTNPaths) -> dict[str, Any]:
    payload = load_json(paths.hard_rule_refresh_state_file, {"version": HARD_RULE_REFRESH_SCHEMA_VERSION, "subscriptions": {}})
    subscriptions = payload.get("subscriptions", {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}
    return {
        "version": HARD_RULE_REFRESH_SCHEMA_VERSION,
        "subscriptions": subscriptions,
    }


def save_refresh_state(paths: GTNPaths, payload: dict[str, Any]) -> None:
    subscriptions = payload.get("subscriptions", {})
    if not isinstance(subscriptions, dict):
        subscriptions = {}
    save_json(
        paths.hard_rule_refresh_state_file,
        {
            "version": HARD_RULE_REFRESH_SCHEMA_VERSION,
            "subscriptions": subscriptions,
        },
    )


def validate_source_id(source_id: str) -> str:
    source = source_id.strip().lower()
    if source not in SUPPORTED_SOURCE_IDS:
        allowed = ", ".join(sorted(SUPPORTED_SOURCE_IDS))
        raise SystemExit(f"Unsupported hard-rule source '{source_id}'. Allowed values: {allowed}")
    return source


def subscription_id(source: str, topic: str) -> str:
    slug = _SLUG_RE.sub("-", topic.strip().lower()).strip("-")
    slug = slug[:48] or "topic"
    return f"{source}:{slug}"


def normalize_subscription(item: dict[str, Any]) -> dict[str, Any]:
    source = validate_source_id(str(item.get("source", "")))
    topic = str(item.get("topic", "")).strip()
    if not topic:
        raise SystemExit("Hard-rule subscriptions require a non-empty topic.")
    top_n = normalize_top_n(item.get("top_n", DEFAULT_TOP_N))
    created_at = str(item.get("created_at", "")).strip() or now_iso()
    updated_at = str(item.get("updated_at", "")).strip() or created_at
    return {
        "id": str(item.get("id", "")).strip() or subscription_id(source, topic),
        "source": source,
        "topic": topic,
        "top_n": top_n,
        "created_at": created_at,
        "updated_at": updated_at,
    }


def normalize_top_n(raw_value: Any) -> int:
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        parsed = DEFAULT_TOP_N
    return max(MIN_TOP_N, min(parsed, MAX_TOP_N))


def create_subscription(source: str, topic: str, top_n: int | None = None) -> dict[str, Any]:
    timestamp = now_iso()
    return normalize_subscription(
        {
            "source": source,
            "topic": topic,
            "top_n": DEFAULT_TOP_N if top_n is None else top_n,
            "created_at": timestamp,
            "updated_at": timestamp,
        }
    )


def upsert_subscriptions(paths: GTNPaths, new_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    subscriptions = load_subscriptions(paths)
    existing_keys = {(item["source"], item["topic"].lower()): item for item in subscriptions}
    for item in new_items:
        normalized = normalize_subscription(item)
        key = (normalized["source"], normalized["topic"].lower())
        existing = existing_keys.get(key)
        if existing:
            existing.update(
                {
                    "topic": normalized["topic"],
                    "top_n": normalized["top_n"],
                    "updated_at": now_iso(),
                }
            )
            continue
        subscriptions.append(normalized)
        existing_keys[key] = normalized
    save_subscriptions(paths, subscriptions)
    return load_subscriptions(paths)


def delete_subscription(paths: GTNPaths, subscription_key: str) -> dict[str, Any] | None:
    target = subscription_key.strip()
    subscriptions = load_subscriptions(paths)
    kept: list[dict[str, Any]] = []
    removed: dict[str, Any] | None = None
    for item in subscriptions:
        if removed is None and (item["id"] == target or f'{item["source"]}:{item["topic"]}' == target):
            removed = item
            continue
        kept.append(item)
    if removed is None:
        return None
    save_subscriptions(paths, kept)
    refresh_state = load_refresh_state(paths)
    refresh_entries = refresh_state.get("subscriptions", {})
    if isinstance(refresh_entries, dict):
        refresh_entries.pop(str(removed.get("id", "")), None)
        save_refresh_state(paths, refresh_state)
    return removed


def parse_topic_overrides(raw_values: list[str] | None) -> dict[str, str]:
    overrides: dict[str, str] = {}
    for raw_value in raw_values or []:
        text = raw_value.strip()
        if "=" not in text:
            raise SystemExit(f"Hard-rule topic override must use source=topic format: {raw_value}")
        source, topic = text.split("=", 1)
        source_id = validate_source_id(source)
        cleaned_topic = topic.strip()
        if not cleaned_topic:
            raise SystemExit(f"Hard-rule topic override requires a non-empty topic: {raw_value}")
        overrides[source_id] = cleaned_topic
    return overrides


def build_subscriptions_from_sources(sources: list[str], overall_topic: str, overrides: dict[str, str] | None = None) -> list[dict[str, Any]]:
    cleaned_sources = [validate_source_id(item) for item in sources]
    if not cleaned_sources:
        return []
    topic = overall_topic.strip()
    if not topic:
        raise SystemExit("Hard-rule setup requires a topic when sources are selected.")
    override_map = overrides or {}
    subscriptions: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in cleaned_sources:
        effective_topic = override_map.get(source, topic).strip()
        key = (source, effective_topic.lower())
        if key in seen:
            continue
        subscriptions.append(create_subscription(source, effective_topic))
        seen.add(key)
    return subscriptions


def supported_sources_lines() -> list[str]:
    lines: list[str] = []
    for index, item in enumerate(SUPPORTED_HARD_RULE_SOURCES, start=1):
        lines.append(f"{index}. {item.label} [{item.source_id}] - {item.description}")
    return lines


def prompt_source_selection(input_text: str) -> list[str]:
    picks = [part.strip() for part in input_text.split(",") if part.strip()]
    selected: list[str] = []
    for pick in picks:
        if pick.isdigit():
            index = int(pick) - 1
            if 0 <= index < len(SUPPORTED_HARD_RULE_SOURCES):
                selected.append(SUPPORTED_HARD_RULE_SOURCES[index].source_id)
                continue
        selected.append(validate_source_id(pick))
    deduped: list[str] = []
    for item in selected:
        if item not in deduped:
            deduped.append(item)
    return deduped


def should_refresh_hard_rules(last_refreshed_at: str | None, now: datetime | None = None) -> bool:
    if not last_refreshed_at:
        return True
    try:
        last_seen = datetime.fromisoformat(last_refreshed_at.replace("Z", "+00:00"))
    except ValueError:
        return True
    current_time = now or datetime.now(timezone.utc).astimezone()
    return current_time - last_seen >= timedelta(days=1)
