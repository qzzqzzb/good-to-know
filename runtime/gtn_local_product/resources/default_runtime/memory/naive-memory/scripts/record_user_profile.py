from __future__ import annotations

import argparse
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DEFAULT_MEMORY_PATH = SKILL_DIR / "user_context.md"
ENTRY_ID = "manual-profile-primary"
DEDUP_KEY = "manual_profile:primary"
ENTRY_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
DEDUP_PATTERN = re.compile(r"^-\s+dedup_key:\s+(.+)$", re.MULTILINE)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def trim_summary(text: str, limit: int = 160) -> str:
    clean = " ".join(text.split())
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def split_entries(text: str) -> list[tuple[str, str]]:
    matches = list(ENTRY_PATTERN.finditer(text))
    entries: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        entry_id = match.group(1).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            entries.append((entry_id, block))
    return entries


def extract_dedup_key(block: str) -> str | None:
    match = DEDUP_PATTERN.search(block)
    return match.group(1).strip() if match else None


def render_profile_block(description: str) -> str:
    summary = trim_summary(description)
    return "\n".join(
        [
            f"## {ENTRY_ID}",
            f"- dedup_key: {DEDUP_KEY}",
            f"- time: {now_iso()}",
            "- source: manual_profile",
            "- type: user_signal",
            "- tags: [profile, self_description]",
            f"- summary: User profile: {summary}",
            f"- raw: {description.strip()}",
        ]
    ).rstrip() + "\n"


def upsert_profile(memory_path: Path, description: str) -> None:
    base = memory_path.read_text(encoding="utf-8") if memory_path.exists() else "# User Context Memory\n\n"
    entries = split_entries(base)
    kept_blocks = []
    for entry_id, block in entries:
        if entry_id == ENTRY_ID:
            continue
        if extract_dedup_key(block) == DEDUP_KEY:
            continue
        kept_blocks.append(block)

    header = "# User Context Memory\n\n"
    non_header_blocks = [block for block in kept_blocks if not block.startswith("# User Context Memory")]
    body_parts = non_header_blocks + [render_profile_block(description).strip()]
    memory_path.write_text(header + "\n\n".join(body_parts).strip() + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Record a user self-description into naive memory.")
    parser.add_argument("description", help="Free-form user description")
    parser.add_argument("--memory-path", help="Optional override for user_context.md")
    args = parser.parse_args()

    memory_path = Path(args.memory_path).resolve() if args.memory_path else DEFAULT_MEMORY_PATH
    upsert_profile(memory_path, args.description)
    print(f"[naive-memory] recorded user profile in {memory_path}")


if __name__ == "__main__":
    main()
