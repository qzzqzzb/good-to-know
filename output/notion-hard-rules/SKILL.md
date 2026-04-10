---
name: notion-hard-rules
description: Publish GTN hard-rule recommendations into a separate Notion database surface. Use when the agent needs to prepare or sync hard-rule output to Notion without mixing it with the main recommendation track.
---

# Notion Hard Rules

Use this skill for the separate hard-rule recommendation track.

## Files

- `settings.json` — destination and display settings for the hard-rule Notion surface
- `scripts/build_notion_payload.py` — maps `hard-rule-briefing.json` into a Notion-oriented payload

## Procedure

1. Read `output/notion-hard-rules/settings.json`.
2. Run `python3 output/notion-hard-rules/scripts/build_notion_payload.py <hard_rule_briefing_json_path>`.
3. Read the generated `hard-rule-notion-payload.json`.
4. If Notion publishing is available in the current session, publish/update the separate hard-rule Notion surface using this payload.
5. Do not mix hard-rule rows into the main recommendation payload/database contract.

## Notes

- This track intentionally omits score, feedback, and `why_recommended`.
- Phase 1 assumes a separate Notion surface for hard-rule recommendations rather than trying to programmatically manage a new view inside the existing recommendation database.
