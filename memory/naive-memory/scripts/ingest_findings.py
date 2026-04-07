from __future__ import annotations

import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
FINDINGS_PATH = SKILL_DIR / "external_findings.md"
ENTRY_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)
DEDUP_PATTERN = re.compile(r"^-\s+dedup_key:\s+(.+)$", re.MULTILINE)


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


def existing_entry_ids(text: str) -> set[str]:
    return {match.group(1).strip() for match in ENTRY_PATTERN.finditer(text)}


def extract_dedup_key(block: str) -> str | None:
    match = DEDUP_PATTERN.search(block)
    if match:
        return match.group(1).strip()
    return None


def existing_dedup_keys(text: str) -> set[str]:
    return {match.group(1).strip() for match in DEDUP_PATTERN.finditer(text)}


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 memory/naive-memory/scripts/ingest_findings.py <discovery_outbox_path>")

    outbox_path = Path(sys.argv[1]).resolve()
    if not outbox_path.exists():
        raise SystemExit(f"Outbox not found: {outbox_path}")

    outbox_text = outbox_path.read_text(encoding="utf-8")
    outbox_entries = split_entries(outbox_text)

    findings_text = FINDINGS_PATH.read_text(encoding="utf-8") if FINDINGS_PATH.exists() else "# External Findings Memory\n\n"
    known_entry_ids = existing_entry_ids(findings_text)
    known_dedup_keys = existing_dedup_keys(findings_text)

    new_blocks = []
    for entry_id, block in outbox_entries:
        dedup_key = extract_dedup_key(block)
        if dedup_key and dedup_key in known_dedup_keys:
            continue
        if entry_id in known_entry_ids:
            continue
        new_blocks.append(block)
        if dedup_key:
            known_dedup_keys.add(dedup_key)
        known_entry_ids.add(entry_id)

    if not new_blocks:
        print("[naive-memory] imported 0 new finding(s)")
        return

    suffix = "\n\n".join(new_blocks).strip() + "\n"
    base = findings_text.rstrip() + "\n\n"
    FINDINGS_PATH.write_text(base + suffix, encoding="utf-8")
    print(f"[naive-memory] imported {len(new_blocks)} new finding(s) from {outbox_path}")


if __name__ == "__main__":
    main()
