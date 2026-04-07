# Query Planning Protocol

Use this protocol after reading recent memory and before calling native web search.

## 1. Read a small working set
Start with recent user-context memory and recent external findings. Prefer the newest entries first.

For a first pass, read enough memory to answer:
- What has the user looked at repeatedly?
- What topics appear recent rather than historical?
- What themes already have many findings, and what themes look underexplored?

## 2. Extract candidate themes
Turn recent memory into 3-6 short themes. Good themes are concrete enough to search directly, for example:
- `agent memory design`
- `Codex runtime tooling`
- `browser-based personal signals`

Avoid giant mixed themes such as `AI tools and productivity and startups`.

## 3. Rank themes for search
Prefer themes with some combination of:
- recent activity
- repeated activity
- likely external change or novelty
- possible action value
- low existing coverage in memory

Do not search every possible theme blindly. Start from the strongest themes first, then expand only if the search results suggest a promising adjacent direction.

## 4. Generate search angles
For each chosen theme, generate up to 3 search angles:
- **Direct**: the topic itself
- **Adjacent**: nearby tools, competitors, workflows, or design patterns
- **Freshness**: new launches, new papers, recent discussion, or latest updates

Example for `agent memory design`:
- direct: `agent memory design patterns`
- adjacent: `personal agent memory architecture local first`
- freshness: `agent memory system new paper OR launch`

## 5. Let the agent control search depth
Do not impose an external hard cap on searches, themes, or opened pages. Let the agent continue exploring until it judges that it has enough useful information for the current run.

The stopping condition should come from agent judgment, not from a fixed numeric budget. In practice, the agent should continue while new results are materially improving understanding, and stop when additional search mostly produces repetition, weak relevance, or low-value detail.

## 6. Decide what is worth remembering
Keep a result only if at least one is true:
- it is clearly relevant to recent user context
- it adds something new versus existing memory
- it could change what the user should pay attention to
- it points to a concrete tool, paper, opportunity, or implementation pattern

Reject results that are generic, repetitive, low-information, or only weakly related.

## 7. Assign stable identity
Before writing a finding, generate a stable identity from its URL.

Use:
- `python3 discovery/web-discovery/scripts/make_finding_id.py <url>`

Prefer source-specific IDs when available. Fall back to a canonicalized URL when no better source-specific identity exists.

## 8. Write findings
When writing findings to `outbox.md`, keep each one compact and useful:
- `title` should be readable enough to show directly in a briefing or Notion row
- `score` should be a required 10-point integer judgment of how strongly this deserves attention now
- `summary` should be the skim layer: what was found and why it matters in 1-2 sentences
- `why_recommended` should be the judgment layer: what recent user context or portfolio gap makes this recommendation worth surfacing now
- `digest` should be the read-for-you layer: a compact paragraph that can save the user from opening the source on the first pass
- `raw` should include the URL or a short source trace
- `tags` should make later retrieval easier
- include both `entry_id` and `dedup_key`

If nothing new is worth storing, leave the outbox unchanged or write nothing new.
