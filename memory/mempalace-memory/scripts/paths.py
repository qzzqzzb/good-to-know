from __future__ import annotations

import json
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
if str(SKILL_DIR) not in sys.path:
    sys.path.insert(0, str(SKILL_DIR))

from module_lib import ensure_paths


def main() -> None:
    paths = ensure_paths()
    print(
        json.dumps(
            {
                "skill_dir": str(paths.skill_dir),
                "data_dir": str(paths.data_dir),
                "palace_dir": str(paths.palace_dir),
                "identity_path": str(paths.identity_path),
                "config_path": str(paths.config_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()
