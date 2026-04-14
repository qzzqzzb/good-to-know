# Hard-Rule Web Research

Use Codex native web search and browsing for GTN hard-rule subscriptions.

## Goal

Produce a normalized JSON list for `hard-rule-items.json` using live web research rather than direct Python network fetches.

Each item should contain:

- `subscription_id`
- `source`
- `topic`
- `title`
- `summary`
- `link`
- `published_at`
- `dedup_key`
- `raw`

## Product Hunt guidance

This follows the same posture as the working `whatsup` Product Hunt skill:

- Use live web browsing/search every run.
- Do not guess from memory.
- Prefer canonical absolute Product Hunt URLs.
- If Product Hunt ranking or links look ambiguous, inspect again before recording.
- Keep only items that are actually relevant to the subscription topic.

## arXiv guidance

- Use live web search/browsing to find current arXiv papers relevant to the topic.
- Prefer canonical arXiv abstract URLs (`https://arxiv.org/abs/...`).
- Preserve the published timestamp visible on arXiv whenever possible.
- Only include arXiv papers published within the last 90 days.
- Keep only items that are actually relevant to the subscription topic.

## Output rules

- Preserve one normalized item per discovered candidate.
- Keep `summary` concise and factual.
- Use `dedup_key` values in the form:
  - `hard-rule:producthunt:<canonical-url>`
  - `hard-rule:arxiv:<canonical-url>`
- `raw` should preserve the source trace, usually the same as `link`.
