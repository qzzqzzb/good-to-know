---
name: notion-briefing
description: Publish briefing recommendations into a Notion database table, with digest content stored in each page body. Use when the agent needs to prepare or sync recommendation output to Notion.
---

# Notion Briefing Output

Use this skill when the agent needs to push the current recommendation set to Notion.

## Prerequisite

This skill depends on the Notion MCP being available in the current Codex session and authenticated for the target workspace.

Project-level Codex configuration can include:

```toml
[mcp_servers.notion]
url = "https://mcp.notion.com/mcp"
```

Then authenticate with:

- `codex mcp login notion`

## What this skill owns

- `settings.json` — local destination and schema settings for this output skill
- `page_index.json` — local mapping from recommendation `dedup_key` to Notion page state
- `feedback_outbox.md` — newly detected feedback signals from Notion
- `references/feedback-sync.md` — protocol for fetching and ingesting Notion feedback
- `references/notion-schema.md` — the current Notion database contract
- `scripts/build_notion_payload.py` — maps `briefing.json` into a Notion-oriented payload
- `scripts/apply_publish_results.py` — updates `page_index.json` from publish results
- `scripts/sync_feedback_state.py` — converts fetched Notion page statuses into feedback observations

## Output model

- One recommendation becomes one row in a Notion database.
- The row is the browse/manage layer.
- The page body is the read layer and stores the longer `digest`.

## Visible database fields

- `Title`
- `URL`
- `Score`
- `Summary`
- `Tags`
- `Feedback`

## Hidden technical field

- `Dedup Key`

Use it for idempotent upsert behavior, but do not treat it as user-facing UI.

## How to use

1. Read `output/notion-briefing/settings.json`.
2. Read `runtime/codex-agent-loop/references/briefing-schema.md`.
3. Run `python3 output/notion-briefing/scripts/build_notion_payload.py <briefing_json_path>`.
4. Read the generated `notion-payload.json`.
5. If `database_url` is configured, use Notion MCP to fetch that database and upsert each item by `Dedup Key`.
6. If `database_url` is empty but `parent_page_url` is configured, create the database first using the schema in `references/notion-schema.md`.
7. For each item:
   - write visible properties to the database row
   - store `digest` in the page body
   - use `Dedup Key` to detect existing rows and update instead of duplicating
   - write `runs/<run_id>/publish-results.json` and apply it with `scripts/apply_publish_results.py`
8. Preserve user feedback:
   - if a page already has a non-default `Feedback`, do not overwrite it during publish
   - fetch indexed pages from Notion, compare their current `Feedback` with `page_index.json`, and treat any change away from `No feedback` as a feedback signal
   - write a snapshot JSON file for those pages into `runs/<run_id>/notion-feedback-snapshot.json`
   - run `python3 output/notion-briefing/scripts/sync_feedback_state.py <snapshot_json_path>`
   - ingest `output/notion-briefing/feedback_outbox.md` into the active memory skill with the context-ingest command
   - follow `references/feedback-sync.md` as the exact MCP-assisted protocol

These steps are for Codex to execute as part of the active runtime loop. The normal UX is that the user asks Codex to run the loop and publish, not that the user manually executes each step.

## Notes

- Keep the table light and scannable.
- Keep the longer reading brief in the page body, not as a table column.
- If Notion MCP is unavailable in the current session, this skill should still build `notion-payload.json` as the publish handoff artifact and report the missing MCP server as the blocker.
- `Feedback` is a user feedback channel; publishing should not blindly reset non-default values.
- The intended loop is: fetch Notion feedback first, ingest it into memory, then generate and publish the next wave of recommendations.
