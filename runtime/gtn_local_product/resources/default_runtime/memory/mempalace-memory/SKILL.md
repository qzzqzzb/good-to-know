---
name: mempalace-memory
description: Store and retrieve GoodToKnow memory using a MemPalace-inspired local palace backed by ChromaDB. Use when the agent needs ingest, wake-up memory, findings export, or memory status.
---

# MemPalace Memory

This skill replaces `naive-memory` with a MemPalace-inspired local memory module.

## What this skill owns
- `identity.md` — always-loaded identity text for wake-up generation
- `scripts/ingest_context.py` — imports context outboxes into the local palace
- `scripts/ingest_findings.py` — imports discovery outboxes into the local palace
- `scripts/read_wakeup.py` — renders session-start wake-up text
- `scripts/read_recall.py` — renders L2-style wing/room filtered recall text
- `scripts/search_memory.py` — runs L3-style semantic search text
- `scripts/export_findings.py` — exports stored findings as JSON for briefing generation
- `scripts/status.py` — reports active storage paths and entry counts
- `scripts/record_user_profile.py` — seeds identity + profile memory during installation
- `.data/palace/` — repo-local ChromaDB storage directory

## Runtime contract
The active runtime shells these scripts directly. Phase 1 does not import memory-module internals from runtime code.

## Notes
- Start from an empty palace; no markdown migration is required.
- Wake-up text always includes `identity.md`, then the top stored memories.
- Recall and search now delegate directly to the pip-installed `mempalace` memory stack.
- Findings export is JSON, not markdown.
