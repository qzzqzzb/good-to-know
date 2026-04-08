from __future__ import annotations

import argparse
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import record_user_profile


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a user self-description into mempalace-memory.")
    parser.add_argument("description")
    args = parser.parse_args()
    record_user_profile(args.description)
    print(f"[mempalace-memory] recorded user profile in {SKILL_DIR / 'identity.md'}")


if __name__ == "__main__":
    main()
