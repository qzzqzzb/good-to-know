---
name: naive-memory
description: Store and retrieve project memory in Markdown documents. Use when the agent needs to ingest context, append findings, or read historical user context for reasoning.
---

# Naive Memory

Use this skill when the agent needs a simple document-backed memory.

## What this skill owns
- `user_context.md` — normalized user-signal memory
- `external_findings.md` — normalized outside-information memory
- `scripts/ingest_context.py` — imports a context skill outbox into `user_context.md`
- `scripts/ingest_findings.py` — imports a discovery skill outbox into `external_findings.md`
- `scripts/record_user_profile.py` — upserts a user self-description into `user_context.md`

## Record format
Append records in this format:

```md
## <entry_id>
- time: 2026-04-05T18:00:00+08:00
- source: browser_history:chrome
- type: user_signal
- tags: [browser_history, chrome]
- summary: Visited example page
- raw: https://example.com
```

Context records may also include a stable `dedup_key`:

```md
## browser-history-chrome-example-com-page-1234abcd
- dedup_key: browser_history:chrome:https://example.com/page:1775390400
- time: 2026-04-05T20:00:00+08:00
- source: browser_history:chrome
- type: user_signal
- tags: [browser_history, chrome]
- summary: Visited example page
- raw: https://example.com/page?utm_source=test
```

Discovery findings follow the same shape but should also include a stable `dedup_key`.
Findings may also include richer recommendation fields such as `title` and `digest`.
They may also include `why_recommended` to preserve the agent's recommendation rationale.
User feedback gathered from output surfaces can also be stored as `user_signal` records and ingested through `ingest_context.py`.

Example:

```md
## finding-github-anthropics-claude-code
- dedup_key: github:anthropics/claude-code
- time: 2026-04-05T22:55:00+08:00
- source: web_search
- type: finding
- title: Claude Code changelog highlights for agent runtime design
- tags: [claude_code, release_notes, agent_runtime]
- score: 6
- summary: Short skim summary.
- why_recommended: >
  Why the agent thinks this item is worth adding now.
- digest: >
  Longer AI reading brief that captures the important parts of the source
  so the user can decide whether they still need to open it.
- raw: https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md
```

## How to ingest context
1. Ensure a context skill has produced an outbox.
2. Run `python3 memory/naive-memory/scripts/ingest_context.py <context_outbox_path>`.
3. Read `memory/naive-memory/user_context.md` for updated memory.

The context ingest script prefers `dedup_key` for deduplication and falls back to the `## <entry_id>` header when no `dedup_key` is present.

## How to ingest findings
1. Ensure a discovery skill has produced an outbox.
2. Run `python3 memory/naive-memory/scripts/ingest_findings.py <discovery_outbox_path>`.
3. Read `memory/naive-memory/external_findings.md` for updated memory.

The findings ingest script prefers `dedup_key` for deduplication and falls back to the `## <entry_id>` header when no `dedup_key` is present.

## Notes
- This skill defines its own storage and ingest rules.
- Other skills should not assume direct write access without following this skill's rules.
- User self-descriptions can be stored as a stable `manual_profile:primary` user signal and updated in place.
- If you replace this skill, the replacement must ship its own ingest and storage behavior locally.
