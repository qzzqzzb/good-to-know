# Briefing Output Schema

This runtime produces a recommendation artifact that is richer than raw findings.

Use it as the handoff point for downstream outputs such as Notion.

## Item shape

Each recommendation item should contain at least:

```json
{
  "entry_id": "finding-github-anthropics-claude-code",
  "dedup_key": "github:anthropics/claude-code",
  "time": "2026-04-05T22:55:00+08:00",
  "source": "web_search",
  "title": "Claude Code changelog highlights for agent runtime design",
  "tags": ["claude_code", "release_notes", "agent_runtime"],
  "score": 8,
  "summary": "Short skim summary.",
  "why_recommended": "Why the agent thinks this item deserves attention now.",
  "digest": "Longer read-for-you brief that can replace opening the source for a first pass.",
  "raw": "https://github.com/anthropics/claude-code/blob/main/CHANGELOG.md"
}
```

## Field intent

- `summary` — the skim layer; keep it to roughly 1-2 sentences.
- `score` — the ranking layer; use an integer from 1 to 10.
- `why_recommended` — the recommendation-judgment layer; explain why the agent surfaced this now.
- `digest` — the reading-replacement layer; compress the source into one compact paragraph with the key takeaways and why they matter.
- `title` — human-readable title suitable for a briefing or Notion page/database row.
- `raw` — source URL or short source trace.

## Notion mapping

For the current output design:

- table fields: `Title`, `URL`, `Score`, `Summary`, `Tags`, `Feedback`
- hidden technical field: `Dedup Key`
- page body: `score` + `why_recommended` + `digest`

## Output files

The runtime briefing builder writes:

- `briefing.json` — machine-friendly output for downstream publishing
- `briefing.md` — human-readable briefing for quick review

## Current rule

If a finding has no `digest`, the runtime may fall back to `summary`, but the target state is for every promoted recommendation to have both.
