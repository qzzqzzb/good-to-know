from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hard_rule_pipeline import build_hard_rule_worklist, now_iso


def main() -> None:
    parser = argparse.ArgumentParser(description="Prepare the GTN hard-rule subscription worklist for Codex-native web research.")
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--output")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    output_path = Path(args.output).resolve() if args.output else run_dir / "hard-rule-worklist.json"
    worklist = build_hard_rule_worklist()
    payload = {
        "generated_at": now_iso(),
        "eligible_subscriptions": worklist.eligible_subscriptions,
        "skipped_subscription_ids": worklist.skipped_subscription_ids,
    }
    output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[hard-rule] wrote worklist to {output_path}")


if __name__ == "__main__":
    main()
