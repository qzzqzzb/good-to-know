from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"
MAIN_SETTINGS_PATH = SKILL_DIR.parent / "notion-briefing" / "settings.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> dict:
    settings = load_json(SETTINGS_PATH)
    if MAIN_SETTINGS_PATH.exists():
        main_settings = load_json(MAIN_SETTINGS_PATH)
        # Phase 1 hard-rule outputs must stay separate from the main recommendation database.
        # Reusing the parent page is acceptable because a separate database can be created there.
        settings["parent_page_url"] = settings.get("parent_page_url") or main_settings.get("parent_page_url", "")
    return settings


def build_page_payload(item: dict, settings: dict) -> dict:
    visible = settings["visible_properties"]
    hidden = settings["hidden_properties"]
    url = str(item.get("link") or item.get("raw") or "").strip()
    body_lines = [
        "## Summary",
        "",
        str(item.get("summary", "")).strip() or "(missing summary)",
        "",
        "## Metadata",
        "",
        f"Source: {item.get('source', '')}",
        f"Topic: {item.get('topic', '')}",
    ]
    if item.get("published_at"):
        body_lines.append(f"Published At: {item['published_at']}")
    return {
        "dedup_key": item.get("dedup_key", ""),
        "match": {
            "property": hidden["dedup_key"],
            "equals": item.get("dedup_key", ""),
        },
        "properties": {
            visible["title"]: item.get("title", ""),
            visible["url"]: url,
            visible["source"]: item.get("source", ""),
            visible["topic"]: item.get("topic", ""),
            visible["published_at"]: item.get("published_at", ""),
            visible["summary"]: item.get("summary", ""),
            hidden["dedup_key"]: item.get("dedup_key", ""),
        },
        "page_body_markdown": "\n".join(body_lines).rstrip() + "\n",
    }


def build_payload(briefing: dict, settings: dict) -> dict:
    items = briefing.get("items", [])
    pages = [build_page_payload(item, settings) for item in items]
    return {
        "run_id": briefing.get("run_id", ""),
        "generated_at": briefing.get("generated_at", ""),
        "database": {
            "name": settings.get("database_name", "GTN Intended Recommendations"),
            "database_url": settings.get("database_url", ""),
            "parent_page_url": settings.get("parent_page_url", ""),
            "visible_properties": settings.get("visible_properties", {}),
            "hidden_properties": settings.get("hidden_properties", {}),
        },
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Notion publish payload from hard-rule-briefing.json.")
    parser.add_argument("briefing_json_path", help="Path to hard-rule-briefing.json")
    parser.add_argument("--output", help="Optional explicit output path")
    args = parser.parse_args()

    briefing_path = Path(args.briefing_json_path).resolve()
    if not briefing_path.exists():
        raise SystemExit(f"Hard-rule briefing JSON not found: {briefing_path}")

    settings = load_settings()
    briefing = load_json(briefing_path)
    payload = build_payload(briefing, settings)
    output_path = Path(args.output).resolve() if args.output else briefing_path.with_name("hard-rule-notion-payload.json")
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[notion-hard-rules] wrote Notion payload to {output_path}")


if __name__ == "__main__":
    main()
