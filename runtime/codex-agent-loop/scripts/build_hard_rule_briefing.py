from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_RUNS_DIR = Path("runs")
ALLOWED_ITEM_FIELDS = (
    "subscription_id",
    "source",
    "topic",
    "title",
    "summary",
    "link",
    "published_at",
    "dedup_key",
    "raw",
)


def normalize_item(item: dict) -> dict:
    return {key: item.get(key, "") for key in ALLOWED_ITEM_FIELDS}


def build_payload(items: list[dict], run_id: str) -> dict:
    normalized_items = [normalize_item(item) for item in items]
    return {
        "run_id": run_id,
        "generated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "track": "hard_rule",
        "items": normalized_items,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# Hard-Rule Briefing",
        "",
        f"- run_id: {payload.get('run_id', '')}",
        f"- generated_at: {payload.get('generated_at', '')}",
        f"- items: {len(payload.get('items', []))}",
        "",
    ]
    for item in payload.get("items", []):
        lines.extend(
            [
                f"## {item.get('title', 'Untitled')}",
                f"- subscription_id: {item.get('subscription_id', '')}",
                f"- source: {item.get('source', '')}",
                f"- topic: {item.get('topic', '')}",
                f"- published_at: {item.get('published_at', '')}",
                f"- link: {item.get('link', '')}",
                "",
                "### Summary",
                str(item.get("summary", "")).strip() or "(missing summary)",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def resolve_run_dir(output_dir: Path, run_id: str | None, explicit_run_dir: Path | None) -> tuple[str, Path]:
    if explicit_run_dir is not None:
        resolved_dir = explicit_run_dir.resolve()
        effective_run_id = run_id or resolved_dir.name
        return effective_run_id, resolved_dir
    effective_run_id = run_id or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds").replace(":", "-")
    return effective_run_id, output_dir.resolve() / effective_run_id


def main() -> None:
    parser = argparse.ArgumentParser(description="Build hard-rule GTN artifacts from normalized item JSON.")
    parser.add_argument("items_json_path", help="Path to normalized hard-rule items JSON.")
    parser.add_argument("--output-dir", default=str(DEFAULT_RUNS_DIR))
    parser.add_argument("--run-id")
    parser.add_argument("--run-dir")
    args = parser.parse_args()

    items_path = Path(args.items_json_path).resolve()
    if not items_path.exists():
        raise SystemExit(f"Hard-rule items not found: {items_path}")
    items = json.loads(items_path.read_text(encoding="utf-8"))
    if not isinstance(items, list):
        raise SystemExit("Hard-rule items input must be a JSON list")

    run_id, run_dir = resolve_run_dir(Path(args.output_dir), args.run_id, Path(args.run_dir) if args.run_dir else None)
    run_dir.mkdir(parents=True, exist_ok=True)
    payload = build_payload(items, run_id)

    json_path = run_dir / "hard-rule-briefing.json"
    md_path = run_dir / "hard-rule-briefing.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    print(f"[hard-rule] wrote briefing json to {json_path}")
    print(f"[hard-rule] wrote briefing markdown to {md_path}")


if __name__ == "__main__":
    main()
