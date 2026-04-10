from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_score(item: dict) -> int:
    try:
        score = int(str(item.get("score", 5)).strip())
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, score))


def build_tags(item: dict) -> list[str]:
    tags = []
    for tag in item.get("tags", []):
        cleaned = str(tag).strip()
        if cleaned and cleaned not in tags:
            tags.append(cleaned)
    return tags


def render_page_body(item: dict) -> str:
    score = parse_score(item)
    why_recommended = str(item.get("why_recommended", "")).strip()
    digest = str(item.get("digest", "")).strip()
    if not digest:
        digest = str(item.get("summary", "")).strip()
    lines = [
        "## Why This Recommendation",
        "",
        f"Score: {score}/10",
        "",
        why_recommended or "(missing why_recommended)",
        "",
        "## Digest",
        "",
        digest or "(missing digest)",
    ]
    return "\n".join(lines).rstrip() + "\n"


def build_page_payload(item: dict, settings: dict) -> dict:
    visible = settings["visible_properties"]
    hidden = settings["hidden_properties"]
    url = str(item.get("raw", "")).strip()

    return {
        "dedup_key": item.get("dedup_key", ""),
        "match": {
            "property": hidden["dedup_key"],
            "equals": item.get("dedup_key", ""),
        },
        "status_policy": {
            "default_if_new": settings.get("default_status", "No feedback"),
            "preserve_if_existing_non_default": True,
        },
        "properties": {
            visible["title"]: item.get("title", ""),
            visible["url"]: url,
            visible["score"]: parse_score(item),
            visible["summary"]: item.get("summary", ""),
            visible["tags"]: build_tags(item),
            visible["status"]: settings.get("default_status", "No feedback"),
            hidden["dedup_key"]: item.get("dedup_key", ""),
        },
        "page_body_markdown": render_page_body(item),
    }


def build_payload(briefing: dict, settings: dict) -> dict:
    items = briefing.get("items", [])
    pages = [build_page_payload(item, settings) for item in items]

    return {
        "run_id": briefing.get("run_id", ""),
        "generated_at": briefing.get("generated_at", ""),
        "database": {
            "name": settings.get("database_name", "GoodToKnow Recommendations"),
            "database_url": settings.get("database_url", ""),
            "parent_page_url": settings.get("parent_page_url", ""),
            "visible_properties": settings.get("visible_properties", {}),
            "hidden_properties": settings.get("hidden_properties", {}),
        },
        "pages": pages,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Notion publish payload from briefing.json.")
    parser.add_argument("briefing_json_path", help="Path to briefing.json")
    parser.add_argument(
        "--output",
        help="Optional explicit output path. Defaults to notion-payload.json next to the input briefing.json",
    )
    args = parser.parse_args()

    briefing_path = Path(args.briefing_json_path).resolve()
    if not briefing_path.exists():
        raise SystemExit(f"Briefing JSON not found: {briefing_path}")

    settings = load_json(SETTINGS_PATH)
    briefing = load_json(briefing_path)
    payload = build_payload(briefing, settings)

    output_path = Path(args.output).resolve() if args.output else briefing_path.with_name("notion-payload.json")
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[notion-briefing] wrote Notion payload to {output_path}")


if __name__ == "__main__":
    main()
