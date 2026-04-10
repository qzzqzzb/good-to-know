from __future__ import annotations

import argparse
from pathlib import Path
import sys

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from hard_rule_pipeline import run_hard_rule_subscriptions


def main() -> None:
    parser = argparse.ArgumentParser(description="Run GTN hard-rule subscriptions and write artifacts.")
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--run-dir", required=True)
    parser.add_argument("--result-path")
    args = parser.parse_args()

    run_dir = Path(args.run_dir).resolve()
    run_dir.mkdir(parents=True, exist_ok=True)
    result_path = Path(args.result_path).resolve() if args.result_path else None
    result = run_hard_rule_subscriptions(args.run_id, run_dir, result_path=result_path)
    print(f"[hard-rule] state={result.state} reason={result.reason} items={result.item_count}")


if __name__ == "__main__":
    main()
