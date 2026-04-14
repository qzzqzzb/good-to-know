from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hard_rule_pipeline import finalize_hard_rule_items, run_hard_rule_subscriptions


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GTN hard-rule subscriptions and write artifacts.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--result-path")
    parser.add_argument("--items-json", help="Optional pre-researched hard-rule items JSON prepared by a Codex web-search pass.")
    parser.add_argument("--worklist-json", help="Optional hard-rule worklist JSON used to record processed/skipped subscriptions.")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(args.result_path).resolve() if args.result_path else None
    if args.items_json:
        items_path = Path(args.items_json).resolve()
        if not items_path.exists():
            raise SystemExit(f"Hard-rule items JSON not found: {items_path}")
        items = json.loads(items_path.read_text(encoding="utf-8"))
        if not isinstance(items, list):
            raise SystemExit("Hard-rule items JSON must be a list")
        processed_subscription_ids: list[str] = []
        skipped_subscription_ids: list[str] = []
        if args.worklist_json:
            worklist_path = Path(args.worklist_json).resolve()
            if worklist_path.exists():
                payload = json.loads(worklist_path.read_text(encoding="utf-8"))
                processed_subscription_ids = [
                    str(item.get("id", "")).strip()
                    for item in payload.get("eligible_subscriptions", [])
                    if isinstance(item, dict) and str(item.get("id", "")).strip()
                ]
                skipped_subscription_ids = [
                    str(item).strip()
                    for item in payload.get("skipped_subscription_ids", [])
                    if str(item).strip()
                ]
        result = finalize_hard_rule_items(
            args.run_id,
            run_dir,
            items,
            result_path=result_path,
            processed_subscription_ids=processed_subscription_ids,
            skipped_subscription_ids=skipped_subscription_ids,
        )
    else:
        result = run_hard_rule_subscriptions(args.run_id, run_dir, result_path=result_path)
    print(f"[hard-rule] state={result.state} reason={result.reason} items={result.item_count}")


if __name__ == "__main__":
    main()
