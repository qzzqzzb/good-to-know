# Notion Feedback Sync

This output skill treats the Notion `Feedback` property as a user feedback channel.

## Goal

Before publishing a new wave of recommendations, fetch the current `Feedback` values
of already indexed recommendation pages and convert any changes into local
`user_signal` observations.

## Required runtime behavior

Because Notion state is fetched through MCP, this step is agent-executed rather than
purely shell-driven.

For each indexed recommendation page in `page_index.json`:

1. Fetch the page from Notion.
2. Read:
   - `page_id`
   - `url`
   - `Title`
   - `Feedback`
   - `Dedup Key`
3. Build `runs/<run_id>/notion-feedback-snapshot.json`
4. Run:

```bash
python3 output/notion-briefing/scripts/sync_feedback_state.py runs/<run_id>/notion-feedback-snapshot.json
```

5. Ingest `output/notion-briefing/feedback_outbox.md` into the active memory skill with:

```bash
python3 memory/naive-memory/scripts/ingest_context.py output/notion-briefing/feedback_outbox.md
```

## Snapshot shape

```json
{
  "checked_at": "2026-04-07T11:20:00+08:00",
  "pages": [
    {
      "page_id": "page-uuid",
      "dedup_key": "arxiv:2603.18743",
      "title": "Memento-Skills reframes skills themselves as persistent agent memory",
      "status": "Good to know",
      "url": "https://www.notion.so/..."
    }
  ]
}
```

## Important behavior

- Default `Feedback` is `No feedback`
- Only changes away from `No feedback` should emit a new feedback observation
- Publishing should preserve non-default `Feedback` values rather than resetting them
- `page_index.json` should be updated only by skill-owned helpers such as `sync_feedback_state.py` and `apply_publish_results.py`
