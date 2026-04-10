---
name: feishu-briefing
description: Publish GTN briefing recommendations into a Feishu group through a custom bot webhook. Use when the agent needs to prepare or send the current briefing to Feishu.
---

# Feishu Briefing Output

Use this skill when the agent needs to push the current recommendation set to a Feishu group.

## Prerequisite

This skill targets a Feishu custom bot webhook in a group chat.

The operator creates the bot in the target group, copies the webhook URL, and stores it in `settings.json`.

## What this skill owns

- `settings.json` — local destination and formatting settings for this output skill
- `scripts/build_payload.py` — maps `briefing.json` into a Feishu-oriented payload artifact
- `scripts/publish_feishu_webhook.py` — posts the generated message to the Feishu webhook and writes a structured result file
- `references/feishu-message-shape.md` — notes on the current message format and constraints

## Output model

- One GTN run becomes one Feishu group message.
- The message is a chat-readable digest, not a row-oriented database representation.
- The source of truth stays `briefing.json`.

## How to use

1. Read `output/feishu-briefing/settings.json`.
2. Read `runtime/codex-agent-loop/references/briefing-schema.md`.
3. Run `python3 output/feishu-briefing/scripts/build_payload.py <briefing_json_path>`.
4. Read the generated `feishu-payload.json`.
5. If `webhook_url` is configured, run `python3 output/feishu-briefing/scripts/publish_feishu_webhook.py <feishu_payload_path>`.
6. If `webhook_url` is empty, keep `feishu-payload.json` as the publish handoff artifact and report the destination as skipped.
7. Write the publish result artifact under `runs/<run_id>/feishu-publish-result.json`.

## Notes

- This v1 output is push-only. Do not add reply handling, card callbacks, or feedback ingestion.
- Format for quick group reading.
- Keep Feishu failures isolated from other output destinations.
- If the operator enables Feishu keyword protection for the bot, prepend the configured keyword in the message body.
