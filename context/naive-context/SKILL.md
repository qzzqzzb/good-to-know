---
name: naive-context
description: Collect user context for this project from local signals, currently browser history. Use when the agent needs fresh user-context observations before writing or reasoning over memory.
---

# Naive Context

Use this skill when the agent needs to refresh local user-context observations.

## What this skill owns
- `settings.json` — local feature toggles for this skill only
- `outbox.md` — normalized observations produced by this skill
- `scripts/collect.py` — runs enabled collectors
- `scripts/collectors/agent_sessions.py` — reads recent Codex / Claude session history
- `scripts/collectors/browser_history.py` — reads recent local browser history

## Current collector
- `agent_sessions` — reads recent Codex / Claude session transcripts and prefers code-edit episodes over whole-session summaries, so one long session can yield multiple observations when the work clearly splits across different implementation chunks
- `browser_history` — reads recent Chrome / Edge / Brave / Firefox history and converts visits into normalized `user_signal` observations

## Identity rules
- Each observation carries a stable `dedup_key`
- Browser history identity is based on browser name + canonicalized URL + visit timestamp
- `entry_id` is derived from that stable identity rather than per-run ordering

## How to use
1. Read `context/naive-context/settings.json`.
2. Run `python3 context/naive-context/scripts/collect.py`.
3. Read `context/naive-context/outbox.md`.
4. Hand that outbox to the active memory skill for ingest.

## Notes
- This skill does not write memory directly.
- All feature toggles stay inside this skill.
- Agent session context is still intentionally lossy: it keeps compact observations per work episode or session summary rather than importing full transcripts into memory.
- If you replace this skill, keep collection rules and config inside the replacement folder.
