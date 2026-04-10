from __future__ import annotations

import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import ingest_outbox


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Usage: python3 memory/mempalace-memory/scripts/ingest_context.py <context_outbox_path>"
        )
    outbox_path = Path(sys.argv[1]).resolve()
    imported = ingest_outbox(outbox_path, bucket="context")
    print(f"[mempalace-memory] imported {imported} context entr(y/ies) from {outbox_path}")


if __name__ == "__main__":
    main()
