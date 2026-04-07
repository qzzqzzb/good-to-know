from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
INDEX_PATH = SKILL_DIR / "page_index.json"
OUTBOX_PATH = SKILL_DIR / "feedback_outbox.md"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    parts = [part for part in cleaned.split("-") if part]
    return "-".join(parts) or "item"


def render_outbox(records: list[dict], generated_at: str) -> str:
    lines = [
        "# Notion Feedback Outbox",
        "",
        f"Generated: {generated_at}",
        f"Observations: {len(records)}",
        "",
    ]

    for record in records:
        tags = ", ".join(record.get("tags", []))
        lines.extend(
            [
                f"## {record['entry_id']}",
                f"- dedup_key: {record['dedup_key']}",
                f"- time: {record['time']}",
                f"- source: {record['source']}",
                "- type: user_signal",
                f"- tags: [{tags}]",
                f"- summary: {record['summary']}",
                f"- raw: {record['raw']}",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def make_feedback_record(page: dict, checked_at: str) -> dict:
    status = str(page.get("status", "")).strip()
    page_id = str(page.get("page_id", "")).strip()
    dedup_key = f"notion_feedback:{page_id}:{slugify(status)}"
    entry_id = f"notion-feedback-{slugify(page_id)}-{slugify(status)}"
    title = str(page.get("title", "Untitled")).strip()
    return {
        "entry_id": entry_id,
        "dedup_key": dedup_key,
        "time": checked_at,
        "source": "notion_feedback",
        "tags": ["feedback", "notion", slugify(status)],
        "summary": f'User marked "{title}" as {status}.',
        "raw": page.get("url", ""),
    }


def sync_feedback(snapshot: dict, index: dict) -> tuple[dict, list[dict]]:
    default_status = str(index.get("default_status", "No feedback")).strip()
    pages_index = index.setdefault("pages", {})
    new_records: list[dict] = []
    checked_at = snapshot.get("checked_at") or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

    for page in snapshot.get("pages", []):
        dedup_key = str(page.get("dedup_key", "")).strip()
        if not dedup_key:
            continue

        current_status = str(page.get("status", default_status)).strip() or default_status
        existing = pages_index.get(dedup_key, {})
        previous_status = str(existing.get("last_seen_status", default_status)).strip() or default_status

        pages_index[dedup_key] = {
            "page_id": page.get("page_id", existing.get("page_id", "")),
            "url": page.get("url", existing.get("url", "")),
            "title": page.get("title", existing.get("title", "")),
            "last_seen_status": current_status,
            "last_checked_at": checked_at,
        }

        if current_status != previous_status and current_status != default_status:
            new_records.append(make_feedback_record(page, checked_at))

    return index, new_records


def main() -> None:
    parser = argparse.ArgumentParser(description="Sync Notion feedback state into a local outbox.")
    parser.add_argument("snapshot_json_path", help="Path to a JSON snapshot of Notion page statuses")
    args = parser.parse_args()

    snapshot_path = Path(args.snapshot_json_path).resolve()
    if not snapshot_path.exists():
        raise SystemExit(f"Snapshot not found: {snapshot_path}")

    snapshot = load_json(snapshot_path)
    index = load_json(INDEX_PATH) if INDEX_PATH.exists() else {"pages": {}, "default_status": "No feedback"}
    updated_index, new_records = sync_feedback(snapshot, index)

    save_json(INDEX_PATH, updated_index)
    generated_at = snapshot.get("checked_at") or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    OUTBOX_PATH.write_text(render_outbox(new_records, generated_at), encoding="utf-8")

    print(f"[notion-briefing] synced feedback state for {len(snapshot.get('pages', []))} page(s)")
    print(f"[notion-briefing] wrote {len(new_records)} new feedback observation(s) to {OUTBOX_PATH}")


if __name__ == "__main__":
    main()
