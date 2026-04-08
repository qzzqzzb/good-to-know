---
name: web-discovery
description: Discover outside information with Codex native web search and browsing. Use when the agent needs fresh external findings grounded in current memory.
---

# Web Discovery

Use this skill when the agent needs to search outward from current memory.

## Prerequisite
This skill depends on Codex native live web search being enabled for the current session.

Local Codex CLI help shows the required flag:

- `codex --search`

That flag enables the native Responses `web_search` tool for the model. If the session was not started with `--search`, this skill cannot perform web discovery and should stop instead of pretending to search.

## What this skill owns
- `outbox.md` — normalized findings produced by this skill
- `references/query-planning.md` — query planning and search-budget protocol
- `scripts/make_finding_id.py` — generates stable `entry_id` and `dedup_key` values from a URL

## How to use
1. Read the active memory skill first.
2. Read recent entries from the currently active memory skill’s exported or readable context surface.
3. Read `discovery/web-discovery/references/query-planning.md` and derive a small set of search directions from recent context.
4. Use Codex native web search and browsing to search, open pages, and inspect promising results.
5. For each result worth remembering, run `python3 discovery/web-discovery/scripts/make_finding_id.py <url>`.
6. Use the template in `discovery/web-discovery/outbox.md` and write normalized findings there.
7. Hand that outbox to the active memory skill for ingest.

## Finding format
Write each finding as:

```md
## <entry_id>
- dedup_key: <stable_key>
- time: 2026-04-05T20:30:00+08:00
- source: web_search
- type: finding
- title: Clear title for the recommendation
- tags: [agents, memory]
- score: 8
- summary: Short 1-2 sentence description of the finding.
- why_recommended: >
  Short explanation of why the agent thinks this item deserves attention now.
- digest: >
  Longer AI reading brief that stands in for opening the source.
  It should say what the source contains, the main takeaways,
  and why the content matters, using a compact paragraph.
- raw: URL or short source trace.
```

## Identity rules
- Prefer source-specific stable IDs when possible, such as arXiv IDs, DOI identifiers, GitHub repo slugs, GitHub issue or pull numbers, and Hacker News item IDs.
- Otherwise use a canonicalized URL with tracking parameters and fragments removed.
- Use `dedup_key` as the stable identity for memory deduplication.
- Use `entry_id` as the stable Markdown header derived from `dedup_key`.

## Notes
- This skill uses Codex built-ins instead of custom web scripts.
- Search depth is agent-controlled; there is no external hard cap in this first version.
- This skill discovers; it does not own the memory write rules.
- `summary` is the skim layer; `digest` is the "read it for me" layer.
- `score` is the ranking layer; use a 10-point integer scale where 10 means "strongly deserves attention now".
- `score` is required for every finding. If the agent is unsure, it should still assign a best-effort score rather than omit it.
- `why_recommended` is the judgment layer; it should explain why this is worth adding now, not just what the source says.
- If replaced later, keep all discovery-specific instructions inside the replacement folder.
