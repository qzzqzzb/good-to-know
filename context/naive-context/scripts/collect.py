from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Dict, List

from collectors.agent_sessions import collect_agent_session_observations
from collectors.browser_history import collect_browser_history_observations

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"
OUTBOX_PATH = SKILL_DIR / "outbox.md"

Collector = Callable[[dict], List[dict]]

COLLECTORS: Dict[str, Collector] = {
    "agent_sessions": collect_agent_session_observations,
    "browser_history": collect_browser_history_observations,
}


def load_settings() -> dict:
    with SETTINGS_PATH.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def normalize_tags(tags: List[str]) -> str:
    clean_tags = []
    for tag in tags:
        value = str(tag).strip().lower().replace(" ", "_")
        if value and value not in clean_tags:
            clean_tags.append(value)
    return ", ".join(clean_tags)


def render_outbox(observations: List[dict]) -> str:
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    lines = [
        "# Naive Context Outbox",
        "",
        f"Generated: {generated_at}",
        f"Observations: {len(observations)}",
        "",
    ]
    for index, observation in enumerate(observations, start=1):
        entry_id = observation.get("entry_id") or f"context-{index:04d}"
        lines.extend(
            [
                f"## {entry_id}",
                *([f"- dedup_key: {observation['dedup_key']}"] if observation.get("dedup_key") else []),
                f"- time: {observation['time']}",
                f"- source: {observation['source']}",
                "- type: user_signal",
                f"- tags: [{normalize_tags(observation.get('tags', []))}]",
                f"- summary: {observation['summary']}",
                f"- raw: {observation.get('raw', '')}",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def collect_observations(settings: dict) -> List[dict]:
    observations: List[dict] = []
    features = settings.get("features", {})
    for feature_name, feature_settings in features.items():
        if not feature_settings.get("enabled"):
            continue
        collector = COLLECTORS.get(feature_name)
        if collector is None:
            continue
        observations.extend(collector(feature_settings))
    observations.sort(key=lambda item: item.get("time", ""), reverse=True)
    return observations


def main() -> None:
    settings = load_settings()
    observations = collect_observations(settings)
    OUTBOX_PATH.write_text(render_outbox(observations), encoding="utf-8")
    print(f"[naive-context] wrote {len(observations)} observation(s) to {OUTBOX_PATH}")


if __name__ == "__main__":
    main()
