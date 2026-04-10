<div align="center">

# GoodToKnow

**A local-first discovery agent that uses your current work context to surface a short briefing of what you should know now, and co-evolves with you over time.**

[中文说明](README.zh-CN.md)

[![macOS](https://img.shields.io/badge/platform-macOS-black)](#quick-start)
[![Local First](https://img.shields.io/badge/local--first-yes-2f855a)](#what-is-goodtoknow)
[![Codex Runtime](https://img.shields.io/badge/runtime-Codex-412991)](#how-it-works)
[![Notion Output](https://img.shields.io/badge/output-Notion-111111)](#configuration)

<img src="assets/GTN.png" alt="GoodToKnow preview" width="860" />

</div>

## In 10 Seconds

GoodToKnow is for people who keep feeling, "I probably missed something useful adjacent to what I'm doing right now."

It runs locally, reads signals from your current work, uses Codex with web search to look outward, and produces a small ranked briefing instead of another infinite feed.

Think of it as a quiet research scout for your real work.

## Installation

### Recommended: install from PyPI

GoodToKnow is now distributed as the published `goodtoknow-gtn` package on PyPI. The supported end-user flow is:

```bash
uv pip install goodtoknow-gtn
gtn setup
```

`gtn setup` now handles the first-time GTN bootstrap flow directly in the CLI:

- initializes the GTN runtime under `~/.gtn`
- prompts for optional Notion output setup
- prompts for an optional initial user profile

If your environment does not expose the `gtn` command after `pip install`, invoke it via the Python environment directly or add that environment's script directory to your `PATH`.

### From source

If you want to test local changes or develop GoodToKnow from the repository:

```bash
git clone https://github.com/qzzqzzb/good-to-know.git
cd good-to-know
uv build
uv pip install --upgrade --force-reinstall dist/goodtoknow_gtn-*.whl
gtn setup
```

Or inside a dedicated local virtual environment:

```bash
uv venv .venv
source .venv/bin/activate
uv pip install --upgrade --force-reinstall dist/goodtoknow_gtn-*.whl
gtn setup
```

## What is GoodToKnow

GoodToKnow is for people who suspect they are missing useful things — tools, papers, updates, ideas, or opportunities adjacent to what they are already doing — but do not want another noisy feed.

It runs quietly in the background, uses your local context to look outward, and surfaces a small number of things that are actually worth your attention.

It collects local signals such as browser history and agent work episodes, which helps filter what gets surfaced.

<p align="center">
  <img src="assets/concept.jpg" alt="GoodToKnow concept diagram" width="860" />
</p>

Why people might want it:

- **Quiet by default**  
  It is meant to run in the background without asking you to constantly manage it.

- **Local-first privacy**  
  Your personal context stays on your machine, so the system can learn from your activity without shipping private data away by default.

- **Better recommendations over time**  
  As you use it, provide feedback, and let it observe more of your context, it can gradually recommend things that fit you better.

- **A briefing, not a feed**  
  The goal is not to show you everything. The goal is to help you notice the few things you probably should know now.

- **Connected to real work**  
  Instead of generic discovery, it tries to tie recommendations to what you are actually building, reading, and thinking about.

## Quick Start

### Prerequisites

You currently need:

- macOS
- `uv`
- `codex`
- a working local Codex login/auth setup

Optional but recommended:

- Notion MCP/auth if you want Notion output

### Run

Run one immediate cycle:

```bash
gtn run
```

See current scheduler/runtime state:

```bash
gtn status
```

Schedule recurring runs:

```bash
gtn freq 1h
```

Stop future scheduled runs:

```bash
gtn stop
```

Upgrade GTN through PyPI:

```bash
uv pip install --python ~/.gtn/.venv/bin/python --upgrade goodtoknow-gtn
```

If you want to remove the GTN package itself:

```bash
uv pip uninstall goodtoknow-gtn
```

## How It Works

GoodToKnow currently runs as a layered local system:

1. `context`
   - collects local signals such as browser history and agent work episodes
2. `memory`
   - stores normalized user context, findings, and feedback signals in a local memory runtime
3. `discovery`
   - uses Codex with web search to look outward based on current memory
4. `runtime`
   - orchestrates the loop
5. `output`
   - publishes recommendations to external surfaces such as Notion

The active stack is selected by `bootstrap/stack.yaml`.

The current default stack uses:

- `context/naive-context`
- `memory/mempalace-memory`
- `discovery/web-discovery`
- `runtime/codex-agent-loop`
- `output/notion-briefing`

## What User Context GTN Currently Scans

Today, the default context stack is intentionally narrow and local-first. GTN does not try to ingest "everything on your machine." It currently scans a small set of local signals that are useful for guessing what you are working on right now.

### 1. Recent browser history

GTN currently reads recent local history from these browsers when their history databases exist on disk:

- Chrome
- Edge
- Brave
- Firefox

What it extracts from browser history:

- the page URL
- the page title when available
- the last-visit timestamp
- the browser source (`chrome`, `edge`, `brave`, or `firefox`)

What it does to normalize browser history before memory ingest:

- ignores internal browser pages such as `chrome://`, `edge://`, `brave://`, `about:`, and `file://`
- keeps only normal `http` / `https` pages
- removes common tracking query parameters such as `utm_*`, `fbclid`, `gclid`, and similar ad/referral markers
- deduplicates by browser + normalized URL, keeping the most recent visit
- converts the result into compact `user_signal` observations rather than copying raw database rows into memory

Default browser-history collection window:

- look back: last 72 hours
- max retained observations per collection pass: 20

Important limitation:

- GTN currently uses browser history as a "what you touched recently" signal
- it does **not** fetch full page content from your browser history database

### 2. Recent coding-agent session activity

GTN also reads recent local session logs from coding agents, currently:

- Codex session logs under `~/.codex/sessions`
- Claude session logs under `~/.claude/projects` and `~/.claude_bak/projects`

The goal is not to store full transcripts in memory. Instead, GTN extracts compact observations about concrete work episodes.

For Codex sessions, GTN currently looks for:

- high-signal user prompts
- `apply_patch` edits
- write-like `exec_command` operations such as file writes, file moves, redirects, `mkdir`, `touch`, and similar shell actions

For Claude sessions, GTN currently looks for:

- high-signal user prompts
- file-writing tools such as `Write`, `Edit`, and `MultiEdit`
- write-like `Bash` commands

How GTN turns agent history into context:

- it prefers edit episodes over whole-session summaries
- one long session can become multiple observations if the work clearly split across multiple implementation chunks
- each observation tries to preserve:
  - which agent produced it (`codex` or `claude`)
  - which workspace / cwd it happened in
  - which files or targets were touched when they can be inferred
  - a short anchor summary based on the triggering user request

Default agent-session collection window:

- look back: last 168 hours
- max retained observations per collection pass: 16
- max observations per session: 3
- Codex subagent sessions: excluded by default
- non-edit sessions: included as compact summaries when no concrete edit episode is found

Important limitation:

- GTN's current agent-session ingest is intentionally lossy
- it stores compact episode summaries, not full transcript replay inside memory

### 3. Where this context goes

The default context skill writes normalized observations into:

- `context/naive-context/outbox.md`

Those observations are then ingested into the active memory layer, where they can influence:

- which adjacent topics GTN searches outward for
- which findings seem more relevant right now
- how the final briefing is prioritized

### 4. What GTN does **not** currently scan by default

In the current default stack, GTN is **not** trying to broadly sweep your machine for arbitrary personal data. For example, this repo's default context skill does not currently ingest:

- email
- chat logs
- arbitrary local documents
- clipboard history
- terminal scrollback in general
- full browser page contents

That may evolve later, but the current default implementation is much narrower: recent browser history plus recent coding-agent work history.

## Configuration

### Notion Output

The Notion output skill is configured in:

```text
~/.gtn/runtime/GoodToKnow/output/notion-briefing/settings.json
```

The main fields are:

- `parent_page_url`
- `database_url`
- `visible_properties`
- `default_status`

Typical flow:

1. Create an empty page in Notion
2. Give that page URL to the installer
3. Let GoodToKnow create or manage the recommendation database under that page

### User Profile

During install, GTN can ask for a short self-description.

This should include things like:

- interests
- the main work you do on this machine
- recurring topics you care about

That description is written into local memory and used as a recommendation hint.

### Scheduler Cadence

Current supported cadence values are:

- `15m`
- `30m`
- `1h`
- `6h`
- `12h`
- `1d`

Example:

```bash
gtn freq 1h
```

## Current Scope

This project is still experimental.

What exists now:

- a local GTN CLI shell
- a Codex-driven runtime loop
- local context and memory
- recommendation scoring
- Notion publishing
- feedback capture from Notion

What is still evolving:

- recommendation quality
- memory retrieval
- unattended run reliability
- installer polish
- broader output surfaces

## Repository Layout

The repository is organized around swappable skill folders:

```text
bootstrap/
context/
memory/
discovery/
runtime/
output/
```

Each skill owns:

- its own `SKILL.md`
- scripts
- local config
- local data shape

The bootstrap layer only selects the active stack. Internal behavior stays inside the chosen skills.

## Notes

- GoodToKnow is currently macOS-first.
- The current local product shell assumes Codex is already installed and authenticated.
