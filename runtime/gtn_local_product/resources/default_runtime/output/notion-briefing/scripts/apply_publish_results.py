from __future__ import annotations

import argparse
import json
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
INDEX_PATH = SKILL_DIR / "page_index.json"


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def save_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

def apply_publish_results(results: dict, index: dict) -> dict:
    pages = index.setdefault("pages", {})
    checked_at = results.get("checked_at", "")
    default_status = index.get("default_status", "No feedback")

    for page in results.get("pages", []):
        dedup_key = str(page.get("dedup_key", "")).strip()
        if not dedup_key:
            continue
        existing = pages.get(dedup_key, {})
        pages[dedup_key] = {
            "page_id": page.get("page_id", existing.get("page_id", "")),
            "url": page.get("url", existing.get("url", "")),
            "title": page.get("title", existing.get("title", "")),
            "last_seen_status": page.get("status_seen", existing.get("last_seen_status", default_status)),
            "last_checked_at": checked_at or existing.get("last_checked_at", ""),
            "matched_existing": bool(page.get("matched_existing", False)),
            "publish_outcome": page.get("publish_outcome", existing.get("publish_outcome", "")),
        }

    return index

def main() -> None:
    parser = argparse.ArgumentParser(description="Apply Notion publish results back into page_index.json")
    parser.add_argument("publish_results_json_path")
    parser.add_argument("--index-path", help="Optional alternate page_index.json path for testing or custom flows")
    args = parser.parse_args()

    results_path = Path(args.publish_results_json_path).resolve()
    if not results_path.exists():
        raise SystemExit(f"Publish results not found: {results_path}")

    results = load_json(results_path)
    index_path = Path(args.index_path).resolve() if args.index_path else INDEX_PATH
    index = load_json(index_path) if index_path.exists() else {"pages": {}, "default_status": "No feedback"}
    save_json(index_path, apply_publish_results(results, index))
    print(f"[notion-briefing] applied publish results from {results_path}")


if __name__ == "__main__":
    main()
