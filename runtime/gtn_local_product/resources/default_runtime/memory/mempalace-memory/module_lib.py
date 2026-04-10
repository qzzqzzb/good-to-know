from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

ENTRY_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)

SKILL_DIR = Path(__file__).resolve().parent
DATA_DIR = Path(os.environ.get("GTN_MEMPALACE_DATA_DIR", SKILL_DIR / ".data")).resolve()
PALACE_DIR = Path(os.environ.get("GTN_MEMPALACE_PALACE_DIR", DATA_DIR / "palace")).resolve()
IDENTITY_PATH = Path(os.environ.get("GTN_MEMPALACE_IDENTITY_PATH", SKILL_DIR / "identity.md")).resolve()
CONFIG_PATH = Path(os.environ.get("GTN_MEMPALACE_CONFIG_PATH", DATA_DIR / "config.json")).resolve()


def ensure_paths() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    PALACE_DIR.mkdir(parents=True, exist_ok=True)
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(
            json.dumps(
                {
                    "palace_path": str(PALACE_DIR),
                    "collection_name": "mempalace_drawers",
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if not IDENTITY_PATH.exists():
        IDENTITY_PATH.write_text(
            "You are GoodToKnow, a local recommendation and memory assistant.\n"
            "No user profile has been recorded yet.\n",
            encoding="utf-8",
        )


def set_mempalace_env() -> None:
    os.environ["MEMPALACE_PALACE_PATH"] = str(PALACE_DIR)
    os.environ["MEMPAL_PALACE_PATH"] = str(PALACE_DIR)


def upstream_config():
    ensure_paths()
    set_mempalace_env()
    try:
        from mempalace.config import MempalaceConfig
    except ImportError as exc:
        raise RuntimeError(
            "mempalace is not installed. Install project dependencies so "
            "memory/mempalace-memory can use the pip-installed MemPalace package."
        ) from exc

    return MempalaceConfig(config_dir=str(CONFIG_PATH.parent))


def get_collection(create: bool = True):
    if not create:
        raise RuntimeError("mempalace-memory expects collection access through the pip-installed mempalace package")
    config = upstream_config()
    try:
        from mempalace.miner import get_collection as upstream_get_collection
    except ImportError as exc:
        raise RuntimeError(
            "mempalace is not installed. Install project dependencies so "
            "memory/mempalace-memory can use the pip-installed MemPalace package."
        ) from exc
    return upstream_get_collection(str(config.palace_path))


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


def parse_tags(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip() for part in inner.split(",") if part.strip()]
    return [value] if value else []


def parse_block(entry_id: str, block: str) -> dict[str, object]:
    lines = block.splitlines()
    data: dict[str, object] = {"entry_id": entry_id, "block": block}
    current_key: str | None = None
    current_mode: str | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal current_key, current_mode, buffer
        if current_key is None:
            return
        data[current_key] = "\n".join(buffer).strip()
        current_key = None
        current_mode = None
        buffer = []

    for line in lines[1:]:
        if line.startswith("- "):
            flush_buffer()
            content = line[2:]
            if ":" not in content:
                continue
            key, raw_value = content.split(":", 1)
            key = key.strip()
            value = raw_value.strip()
            if value in {">", "|"}:
                current_key = key
                current_mode = value
                buffer = []
                continue
            if key == "tags":
                data[key] = parse_tags(value)
            else:
                data[key] = value
            continue

        if current_key is not None and (line.startswith("  ") or not line.strip()):
            if current_mode == ">":
                stripped = line.strip()
                if stripped:
                    buffer.append(stripped)
            else:
                buffer.append(line[2:] if line.startswith("  ") else "")

    flush_buffer()
    return data


def load_outbox_records(outbox_path: Path) -> list[dict[str, object]]:
    text = outbox_path.read_text(encoding="utf-8")
    return [parse_block(entry_id, block) for entry_id, block in split_entries(text)]


def make_record_id(record: dict[str, object]) -> str:
    stable = str(record.get("dedup_key") or record.get("entry_id") or record.get("raw") or "")
    digest = hashlib.md5(stable.encode("utf-8"), usedforsecurity=False).hexdigest()
    return f"drawer_{digest}"


def iso_now() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_iso(value: object) -> float:
    text = str(value or "").strip()
    if not text:
        return 0.0
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return 0.0


def document_text(record: dict[str, object]) -> str:
    parts = [
        str(record.get("title", "")).strip(),
        str(record.get("summary", "")).strip(),
        str(record.get("why_recommended", "")).strip(),
        str(record.get("digest", "")).strip(),
        str(record.get("raw", "")).strip(),
    ]
    body = "\n".join(part for part in parts if part)
    return body or str(record.get("block", "")).strip() or str(record.get("entry_id", ""))


def coerce_score(raw_value: object, default: float = 3.0) -> float:
    try:
        return float(str(raw_value).strip())
    except (TypeError, ValueError):
        return default


def derive_room(record: dict[str, object], bucket: str) -> str:
    tags = record.get("tags") or []
    if isinstance(tags, list) and tags:
        return str(tags[0]).replace(" ", "_")
    return str(record.get("type") or bucket or "general").replace(" ", "_")


def metadata_for(record: dict[str, object], bucket: str) -> dict[str, str | float | int]:
    tags = record.get("tags") or []
    if not isinstance(tags, list):
        tags = parse_tags(str(tags))
    return {
        "entry_id": str(record.get("entry_id", "")),
        "dedup_key": str(record.get("dedup_key", "")),
        "bucket": bucket,
        "type": str(record.get("type") or ("finding" if bucket == "findings" else "user_signal")),
        "source": str(record.get("source", bucket)),
        "time": str(record.get("time", iso_now())),
        "title": str(record.get("title", "")),
        "summary": str(record.get("summary", "")),
        "why_recommended": str(record.get("why_recommended", "")),
        "digest": str(record.get("digest", "")),
        "raw": str(record.get("raw", "")),
        "tags": ",".join(str(tag) for tag in tags if str(tag).strip()),
        "score": coerce_score(record.get("score"), default=0.0),
        "weight": coerce_score(record.get("score"), default=3.0),
        "wing": str(record.get("wing") or "gtn"),
        "room": derive_room(record, bucket),
        "source_file": str(record.get("source", bucket)),
        "added_by": "goodtoknow",
        "filed_at": iso_now(),
    }


def ingest_outbox(outbox_path: Path, bucket: str) -> int:
    if not outbox_path.exists():
        raise SystemExit(f"Outbox not found: {outbox_path}")
    set_mempalace_env()
    records = load_outbox_records(outbox_path)
    if not records:
        return 0

    collection = get_collection(create=True)
    collection.upsert(
        ids=[make_record_id(record) for record in records],
        documents=[document_text(record) for record in records],
        metadatas=[metadata_for(record, bucket) for record in records],
    )
    return len(records)


def read_identity() -> str:
    ensure_paths()
    return IDENTITY_PATH.read_text(encoding="utf-8").strip()


def list_records(bucket: str | None = None) -> list[dict[str, object]]:
    set_mempalace_env()
    collection = get_collection(create=True)
    kwargs: dict[str, object] = {"include": ["documents", "metadatas"]}
    if bucket:
        kwargs["where"] = {"bucket": bucket}
    result = collection.get(**kwargs)
    docs = result.get("documents", [])
    metas = result.get("metadatas", [])
    records: list[dict[str, object]] = []
    for doc, meta in zip(docs, metas):
        record = dict(meta or {})
        record["document"] = doc
        record["tags"] = parse_tags(f"[{record.get('tags', '')}]") if record.get("tags") else []
        records.append(record)
    records.sort(
        key=lambda item: (float(item.get("score", 0.0)), parse_iso(item.get("time"))),
        reverse=True,
    )
    return records


def upstream_memory_stack():
    config = upstream_config()
    try:
        from mempalace.layers import MemoryStack
    except ImportError as exc:
        raise RuntimeError(
            "mempalace is not installed. Install project dependencies so "
            "memory/mempalace-memory can use the pip-installed MemPalace package."
        ) from exc

    return MemoryStack(palace_path=str(config.palace_path), identity_path=str(IDENTITY_PATH))


def build_wakeup_text(wing: str | None = None) -> str:
    get_collection(create=True)
    if not list_records():
        identity = read_identity()
        return (
            f"{identity}\n\n"
            "## L1 — No memories yet.\n"
            "No stored memories yet. Start using GoodToKnow so this palace can accumulate useful context.\n"
        )
    stack = upstream_memory_stack()
    text = stack.wake_up(wing=wing)
    if "## L1 — No palace found. Run: mempalace mine <dir>" in text:
        return text.replace(
            "## L1 — No palace found. Run: mempalace mine <dir>",
            "## L1 — No memories yet.",
        )
    if "## L1 — No memories yet." in text:
        return text.replace(
            "## L1 — No memories yet.",
            "## L1 — No memories yet.\nNo stored memories yet. Start using GoodToKnow so this palace can accumulate useful context.",
        )
    return text


def build_recall_text(wing: str | None = None, room: str | None = None, n_results: int = 10) -> str:
    stack = upstream_memory_stack()
    return stack.recall(wing=wing, room=room, n_results=n_results)


def build_search_text(
    query: str, wing: str | None = None, room: str | None = None, n_results: int = 5
) -> str:
    stack = upstream_memory_stack()
    return stack.search(query=query, wing=wing, room=room, n_results=n_results)


def export_findings_payload() -> list[dict[str, object]]:
    payload: list[dict[str, object]] = []
    for record in list_records(bucket="findings"):
        payload.append(
            {
                "entry_id": str(record.get("entry_id", "")),
                "dedup_key": str(record.get("dedup_key", "")),
                "time": str(record.get("time", "")),
                "source": str(record.get("source", "")),
                "title": str(record.get("title") or record.get("summary") or record.get("entry_id") or ""),
                "tags": record.get("tags", []),
                "score": int(round(float(record.get("score", 0.0)))) if record.get("score") not in (None, "") else 0,
                "summary": str(record.get("summary", "")),
                "why_recommended": str(record.get("why_recommended", "")),
                "digest": str(record.get("digest", "")),
                "raw": str(record.get("raw", "")),
            }
        )
    return payload


def status_payload() -> dict[str, object]:
    get_collection(create=True)
    stack = upstream_memory_stack()
    config = upstream_config()
    payload = stack.status()
    payload.update(
        {
            "skill_dir": str(SKILL_DIR),
            "data_dir": str(DATA_DIR),
            "palace_dir": str(config.palace_path),
            "identity_path": str(IDENTITY_PATH),
            "config_path": str(CONFIG_PATH),
            "collection_name": config.collection_name,
            "counts_by_bucket": {},
        }
    )
    for record in list_records():
        bucket = str(record.get("bucket", "unknown"))
        payload["counts_by_bucket"][bucket] = payload["counts_by_bucket"].get(bucket, 0) + 1
    payload["total_entries"] = sum(payload["counts_by_bucket"].values())
    return payload


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def record_user_profile(description: str) -> None:
    ensure_paths()
    cleaned = description.strip()
    IDENTITY_PATH.write_text(cleaned + "\n", encoding="utf-8")
    profile_record = {
        "entry_id": "manual-profile-primary",
        "dedup_key": "manual_profile:primary",
        "time": iso_now(),
        "source": "manual_profile",
        "type": "user_signal",
        "title": "User profile",
        "tags": ["manual_profile"],
        "summary": cleaned.splitlines()[0] if cleaned else "User profile",
        "digest": cleaned,
        "raw": cleaned,
        "wing": "gtn",
        "room": "identity",
    }
    set_mempalace_env()
    collection = get_collection(create=True)
    collection.upsert(
        ids=[make_record_id(profile_record)],
        documents=[document_text(profile_record)],
        metadatas=[metadata_for(profile_record, "context")],
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Debug helpers for mempalace-memory")
    parser.add_argument("command", choices=("status", "wakeup", "export-findings"))
    args = parser.parse_args()
    if args.command == "status":
        print(json.dumps(status_payload(), ensure_ascii=False, indent=2))
    elif args.command == "wakeup":
        print(build_wakeup_text())
    else:
        print(json.dumps(export_findings_payload(), ensure_ascii=False, indent=2))
