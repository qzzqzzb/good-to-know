from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import build_wakeup_text, write_text


def main() -> None:
    parser = argparse.ArgumentParser(description="Render wake-up text for mempalace-memory")
    parser.add_argument("--output", help="Optional file path to write the wake-up text")
    parser.add_argument("--wing", help="Optional wing filter", default=None)
    args = parser.parse_args()

    text = build_wakeup_text(wing=args.wing)
    if args.output:
        write_text(Path(args.output).resolve(), text)
    else:
        print(text, end="")


if __name__ == "__main__":
    main()
