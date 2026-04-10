from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"
DEFAULT_MAX_ITEMS = 5
MAX_ITEMS_UPPER_BOUND = 20
MAX_REQUEST_BODY_BYTES = 20_000


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def parse_score(item: dict) -> int:
    try:
        score = int(str(item.get("score", 5)).strip())
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, score))


def compact_text(value: object, limit: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return text[: max(0, limit - 1)].rstrip() + "…"


def parse_max_items(settings: dict) -> int:
    raw_value = settings.get("max_items", DEFAULT_MAX_ITEMS)
    try:
        parsed = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return DEFAULT_MAX_ITEMS
    return max(1, min(parsed, MAX_ITEMS_UPPER_BOUND))


def build_item_lines(item: dict, index: int) -> list[str]:
    title = compact_text(item.get("title", "Untitled"), 120)
    summary = compact_text(item.get("summary", ""), 180)
    why = compact_text(item.get("why_recommended", ""), 180)
    digest = compact_text(item.get("digest") or item.get("summary", ""), 220)
    url = str(item.get("raw", "")).strip()
    score = parse_score(item)

    lines = [f"{index}. {title} ({score}/10)"]
    if summary:
        lines.append(f"   Summary: {summary}")
    if why:
        lines.append(f"   Why now: {why}")
    if digest and digest != summary:
        lines.append(f"   Digest: {digest}")
    if url:
        lines.append(f"   Link: {url}")
    return lines


def render_message_text(briefing: dict, settings: dict, selected_items: list[dict]) -> str:
    total_items = len(briefing.get("items", []))
    title = str(settings.get("message_title", "GoodToKnow Briefing")).strip() or "GoodToKnow Briefing"
    keyword = str(settings.get("required_keyword", "")).strip()

    lines = []
    if keyword:
        lines.append(keyword)
    lines.extend(
        [
            f"[GTN] {title}",
            f"Run: {briefing.get('run_id', '')}",
            f"Generated: {briefing.get('generated_at', '')}",
            f"Items: {len(selected_items)} of {total_items}",
            "",
        ]
    )

    for index, item in enumerate(selected_items, start=1):
        lines.extend(build_item_lines(item, index))
        lines.append("")

    warnings = briefing.get("warnings", {})
    missing_scores = warnings.get("missing_score_entry_ids", [])
    if missing_scores:
        lines.append(f"Warnings: missing scores for {len(missing_scores)} item(s)")

    return "\n".join(lines).strip() + "\n"


def message_body_size(message: dict) -> int:
    return len(json.dumps(message, ensure_ascii=False).encode("utf-8"))


def fit_text_to_budget(message: dict, text: str) -> str:
    if message_body_size(message) <= MAX_REQUEST_BODY_BYTES:
        return text

    suffix = "…\n"
    if not text:
        return text

    low = 0
    high = len(text)
    best = suffix if message_body_size({"msg_type": message["msg_type"], "content": {"text": suffix}}) <= MAX_REQUEST_BODY_BYTES else ""

    while low <= high:
        mid = (low + high) // 2
        candidate = text[:mid].rstrip()
        if candidate:
            candidate += suffix
        else:
            candidate = suffix
        candidate_message = {"msg_type": message["msg_type"], "content": {"text": candidate}}
        if message_body_size(candidate_message) <= MAX_REQUEST_BODY_BYTES:
            best = candidate
            low = mid + 1
        else:
            high = mid - 1

    return best or suffix


def build_payload(briefing: dict, settings: dict) -> dict:
    max_items = parse_max_items(settings)
    selected_items = list(briefing.get("items", []))[:max_items]

    while True:
        message_text = render_message_text(briefing, settings, selected_items)
        message = {
            "msg_type": "text",
            "content": {
                "text": message_text,
            },
        }
        if message_body_size(message) <= MAX_REQUEST_BODY_BYTES:
            break
        if len(selected_items) <= 1:
            message["content"]["text"] = fit_text_to_budget(message, message_text)
            break
        selected_items = selected_items[:-1]

    return {
        "run_id": briefing.get("run_id", ""),
        "generated_at": briefing.get("generated_at", ""),
        "destination": {
            "type": "feishu_custom_bot_webhook",
            "webhook_configured": bool(str(settings.get("webhook_url", "")).strip()),
            "message_title": str(settings.get("message_title", "")).strip() or "GoodToKnow Briefing",
            "required_keyword": str(settings.get("required_keyword", "")).strip(),
            "max_items": max_items,
        },
        "source": {
            "briefing_item_count": len(briefing.get("items", [])),
            "rendered_item_count": len(selected_items),
            "memory_wakeup": briefing.get("memory_wakeup", ""),
        },
        "message": message,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a Feishu webhook payload from briefing.json.")
    parser.add_argument("briefing_json_path", help="Path to briefing.json")
    parser.add_argument(
        "--output",
        help="Optional explicit output path. Defaults to feishu-payload.json next to the input briefing.json",
    )
    args = parser.parse_args()

    briefing_path = Path(args.briefing_json_path).resolve()
    if not briefing_path.exists():
        raise SystemExit(f"Briefing JSON not found: {briefing_path}")

    settings = load_json(SETTINGS_PATH)
    briefing = load_json(briefing_path)
    payload = build_payload(briefing, settings)

    output_path = Path(args.output).resolve() if args.output else briefing_path.with_name("feishu-payload.json")
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[feishu-briefing] wrote Feishu payload to {output_path}")


if __name__ == "__main__":
    main()
