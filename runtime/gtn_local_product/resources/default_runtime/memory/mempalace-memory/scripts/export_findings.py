from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import export_findings_payload, write_json


def main() -> None:
    parser = argparse.ArgumentParser(description="Export mempalace-memory findings as JSON")
    parser.add_argument("--output", help="Optional file path to write exported findings")
    args = parser.parse_args()

    payload = export_findings_payload()
    if args.output:
        write_json(Path(args.output).resolve(), payload)
    else:
        print(json.dumps(payload, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
