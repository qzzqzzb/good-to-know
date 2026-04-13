# Notion Recommendation Table

This output skill publishes recommendations into a Notion database.

The table should stay light enough to scan quickly.

## Visible properties

- `Title` — title property
- `URL` — URL property
- `Score` — number property (1-10)
- `Summary` — rich text property
- `Tags` — rich text property storing a comma-separated tag string
- `Feedback` — feedback select property with:
  - `No feedback`
  - `Good to know`
  - `Bad recommendation`

## Hidden property

- `Dedup Key` — rich text property used for idempotent sync

Keep `Dedup Key` off the default table view if possible.

## Page body

The page body should contain the longer recommendation reading brief.

Suggested body shape:

```md
## Why This Recommendation

Score: <N>/10

<agent judgment for why this belongs here now>

## Digest

<longer read-for-you summary>
```

## Sync rule

- Match existing rows by `Dedup Key`
- Write `publish-results.json` after publish and apply it through a skill-owned helper so `page_index.json` remains owned by the output skill
- Update visible properties and page body when a matching row exists
- Create a new row only when no matching `Dedup Key` exists
