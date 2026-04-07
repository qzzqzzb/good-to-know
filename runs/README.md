# Run Artifacts

Store one directory per run in this directory.

Suggested directory format:

- `2026-04-06T21-30-00+08-00/`

Suggested contents:

- active stack
- `briefing.json`
- `briefing.md`
- `notion-payload.json` if a Notion output skill is active
- `notion-feedback-snapshot.json` if feedback was fetched from Notion during the run
- `publish-results.json` if publish outcomes were captured for output-state writeback
- `result.json` if a runtime helper wrote a structured local result artifact
- brief execution notes if needed
- links back to relevant memory entries
