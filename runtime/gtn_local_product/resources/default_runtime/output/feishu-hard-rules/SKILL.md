---
name: feishu-hard-rules
description: Publish GTN hard-rule recommendations as a separate Feishu message. Use when the agent needs to prepare or send hard-rule output to Feishu without mixing it with the main recommendation track.
---

# Feishu Hard Rules

Use this skill for the separate hard-rule recommendation track.

## Files

- `settings.json` — destination and display settings for hard-rule Feishu output
- `scripts/build_payload.py` — maps `hard-rule-briefing.json` into a Feishu-oriented payload artifact
- reuse `output/feishu-briefing/scripts/publish_feishu_webhook.py` when a webhook is configured

## Procedure

1. Read `output/feishu-hard-rules/settings.json`.
2. Run `python3 output/feishu-hard-rules/scripts/build_payload.py <hard_rule_briefing_json_path>`.
3. Read the generated `hard-rule-feishu-payload.json`.
4. If a webhook is configured, run `python3 output/feishu-briefing/scripts/publish_feishu_webhook.py <hard_rule_payload_path>`.
5. If no webhook is configured, keep the payload artifact as the handoff output and report the destination as skipped.

## Notes

- This track intentionally omits score, feedback, and `why_recommended`.
- The hard-rule Feishu message should always stay separate from the main GTN briefing message.
