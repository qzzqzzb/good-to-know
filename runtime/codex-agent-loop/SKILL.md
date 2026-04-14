---
name: codex-agent-loop
description: Entry skill for this project. Use when operating the repository as an agent-first system: read the active stack, invoke active skills, update memory, and produce the current result set.
---

# Codex Agent Loop

This is the main entry skill for the project.

## Runtime posture
- Treat Codex as the main entrypoint.
- Treat active skills as tools Codex can invoke.
- Prefer short, repeatable passes over one giant search-and-reason run.
- The user should be able to trigger the whole loop with one request to Codex; do not hand the user a checklist of shell commands unless they explicitly ask for debug steps.

## How to run the loop
1. Read `bootstrap/stack.yaml`.
2. Read the active memory skill.
3. For each active context skill:
   - read its `SKILL.md`
   - execute its local procedure
   - pass its outbox to the active memory skill with the memory skill’s context-ingest command
4. For each active discovery skill:
   - read its `SKILL.md`
   - confirm the current Codex session was started with native web search enabled
   - read any referenced discovery protocol needed for query planning
   - execute its local procedure with Codex built-in web search and browsing
   - pass its outbox to the active memory skill with the memory skill’s findings-ingest command
5. For each active output skill that can collect user feedback:
   - read its `SKILL.md`
   - fetch the latest feedback state from that destination
   - sync it into the output skill's `feedback_outbox.md`
   - pass that outbox to the active memory skill with the memory skill’s context-ingest command
6. Read updated memory.
7. Reason over memory and produce the current result set.
8. Build a richer briefing artifact where each recommendation has both a short `summary` and a longer `digest`.
9. For each active output skill:
   - read its `SKILL.md`
   - transform the current briefing artifact into the output skill's publish format
   - publish or prepare the handoff for that destination
   - if an external product shell allocated the run identity first, keep repo artifacts under that exact `run_id` / run directory
10. Save run artifacts into `runs/`.

## Deterministic helpers

Use these helper commands inside Codex when it speeds up the loop:

- `python3 runtime/codex-agent-loop/scripts/run_active_stack.py --stage pre-discovery`
- `python3 runtime/codex-agent-loop/scripts/run_active_stack.py --stage post-discovery`

The first refreshes context and ingests it into memory.
The second ingests discovery outboxes, ingests any prepared feedback outboxes, builds `briefing.json` / `briefing.md`, and builds the main-track output payloads such as `notion-payload.json` or `feishu-payload.json`.

Hard-rule recommendations are now a Codex-native web-research track:

- `python3 runtime/codex-agent-loop/scripts/prepare_hard_rule_worklist.py --run-dir <run-dir>`
- Codex web-research writes `<run-dir>/hard-rule-items.json`
- `python3 runtime/codex-agent-loop/scripts/run_hard_rules.py --run-id <run-id> --run-dir <run-dir> --items-json <run-dir>/hard-rule-items.json --worklist-json <run-dir>/hard-rule-worklist.json`

Use `runtime/codex-agent-loop/references/hard-rule-web-research.md` as the local reference for this track.

If discovery outboxes are already ready, Codex may use:

- `python3 runtime/codex-agent-loop/scripts/run_active_stack.py --stage local-only`

These are internal helper commands for Codex. The user-facing interaction stays one request.

## Query-generation rule
When discovery is active, Codex should not search from scratch. It should:
1. read recent memory
2. extract a few concrete themes
3. choose only the strongest themes for this run
4. generate direct, adjacent, and freshness-oriented queries
5. continue searching until the marginal value drops enough that the run feels complete
6. remember only findings that add something meaningfully new

Use the active discovery skill's local protocol as the source of truth for the exact query-planning steps.

## Notes
- The user does not manually run module commands; Codex uses this skill as the main entrypoint.
- Native web discovery requires starting Codex with `--search`.
- Use `runtime/codex-agent-loop/references/briefing-schema.md` as the output contract for recommendation artifacts.
- Use `python3 runtime/codex-agent-loop/scripts/build_briefing.py <memory-findings.json>` to turn exported findings into `briefing.json` and `briefing.md`.
- Use `python3 runtime/codex-agent-loop/scripts/run_active_stack.py` to bundle the deterministic local parts of the stack into one Codex-owned step.
- Runtime helpers should accept explicit `--run-id` / `--run-dir` when a product shell allocates run identity first.
- Bootstrap selects active skills but does not define their internal behavior.
