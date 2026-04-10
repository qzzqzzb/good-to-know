from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"
MAIN_SETTINGS_PATH = SKILL_DIR.parent / "feishu-briefing" / "settings.json"
DEFAULT_MAX_ITEMS = 20
MAX_ITEMS_UPPER_BOUND = 50


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def load_settings() -> dict:
    settings = load_json(SETTINGS_PATH)
    if MAIN_SETTINGS_PATH.exists():
        main_settings = load_json(MAIN_SETTINGS_PATH)
        settings["webhook_url"] = settings.get("webhook_url") or main_settings.get("webhook_url", "")
    return settings


def parse_max_items(settings: dict) -> int:
    raw_value = settings.get("max_items", DEFAULT_MAX_ITEMS)
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS
    return max(1, min(parsed, MAX_ITEMS_UPPER_BOUND))


def compact_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "..."


def render_message_text(briefing: dict, settings: dict, selected_items: list[dict]) -> str:
    title = str(settings.get("message_title", "GTN Intended Recommendations")).strip() or "GTN Intended Recommendations"
    keyword = str(settings.get("required_keyword", "")).strip()
    lines = []
    if keyword:
        lines.append(keyword)
    lines.extend(
        [
            f"[GTN] {title}",
            f"Run: {briefing.get('run_id', '')}",
            f"Generated: {briefing.get('generated_at', '')}",
            f"Items: {len(selected_items)}",
            "",
        ]
    )
    for index, item in enumerate(selected_items, start=1):
        lines.append(f"{index}. {compact_text(item.get('title', 'Untitled'), 120)}")
        lines.append(f"   Source: {item.get('source', '')}")
        lines.append(f"   Topic: {item.get('topic', '')}")
        if item.get("summary"):
            lines.append(f"   Summary: {compact_text(item['summary'], 180)}")
        if item.get("link"):
            lines.append(f"   Link: {item['link']}")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def build_payload(briefing: dict, settings: dict) -> dict:
    max_items = parse_max_items(settings)
    selected_items = list(briefing.get("items", []))[:max_items]
    return {
        "run_id": briefing.get("run_id", ""),
        "generated_at": briefing.get("generated_at", ""),
        "destination": {
            "type": "feishu_custom_bot_webhook",
            "webhook_configured": bool(str(settings.get("webhook_url", "")).strip()),
            "message_title": str(settings.get("message_title", "")).strip() or "GTN Intended Recommendations",
            "required_keyword": str(settings.get("required_keyword", "")).strip(),
            "max_items": max_items,
        },
        "source": {
            "briefing_item_count": len(briefing.get("items", [])),
            "rendered_item_count": len(selected_items),
        },
        "message": {
            "msg_type": "text",
            "content": {
                "text": render_message_text(briefing, settings, selected_items),
            },
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Feishu webhook payload from hard-rule-briefing.json.")
    parser.add_argument("briefing_json_path", help="Path to hard-rule-briefing.json")
    parser.add_argument("--output", help="Optional explicit output path")
    args = parser.parse_args()

    briefing_path = Path(args.briefing_json_path).resolve()
    if not briefing_path.exists():
        raise SystemExit(f"Hard-rule briefing JSON not found: {briefing_path}")

    settings = load_settings()
    briefing = load_json(briefing_path)
    payload = build_payload(briefing, settings)
    output_path = Path(args.output).resolve() if args.output else briefing_path.with_name("hard-rule-feishu-payload.json")
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[feishu-hard-rules] wrote Feishu payload to {output_path}")


if __name__ == "__main__":
    main()
