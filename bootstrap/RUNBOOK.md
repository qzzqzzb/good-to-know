# Bootstrap Runbook

## Purpose
Bootstrap only selects which skills are active for a run. It does not define how context, memory, discovery, or runtime behavior works. Those rules live inside the active skill folders.

## Active Stack
Read `bootstrap/stack.yaml` first. It points Codex at the current runtime, memory, context, and discovery skills.
If present, it also points to active output skills that publish finished recommendation artifacts.

## Usage Model
The user interacts with the agent, not with individual commands. Codex should use the runtime skill from `bootstrap/stack.yaml` as the main entrypoint, then invoke other active skills as needed.

The intended UX is a single Codex request for the whole loop, for example:

- refresh context
- discover outward
- update memory
- build the briefing artifact
- publish to active outputs such as Notion

Shell commands are internal implementation details for Codex, not the normal user path.

## Native Web Search
The current discovery skill expects Codex native web search to be enabled for the session. Local `codex --help` shows the required flag:

- `codex --search`

Without that flag, the native Responses `web_search` tool is unavailable to the model.

## Swapping Skills
To replace a skill, change only the path in `bootstrap/stack.yaml`. Do not copy behavior into bootstrap.
