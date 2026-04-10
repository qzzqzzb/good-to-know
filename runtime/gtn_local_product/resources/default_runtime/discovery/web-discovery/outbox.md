# Web Discovery Outbox

Use this file to store normalized findings produced by the `web-discovery` skill.

## Template

Copy this block for each finding worth remembering:

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
