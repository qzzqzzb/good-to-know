from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import build_search_text, write_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deep search for mempalace-memory")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--output", help="Optional file path to write the search result")
    parser.add_argument("--wing", default=None, help="Optional wing filter")
    parser.add_argument("--room", default=None, help="Optional room filter")
    parser.add_argument("--limit", type=int, default=5, help="Maximum results to include")
    args = parser.parse_args()

    text = build_search_text(query=args.query, wing=args.wing, room=args.room, n_results=args.limit)
    if args.output:
        write_text(Path(args.output).resolve(), text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
