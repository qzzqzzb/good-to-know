<div align="center">

# GoodToKnow

**A local-first discovery agent that uses your current work context to surface a short briefing of what you should know now, and co-evolves with you over time.**

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

## Install In One Line

```bash
curl -fsSL https://raw.githubusercontent.com/qzzqzzb/good-to-know/main/scripts/install_gtn.sh | bash
```

This installs a local `gtn` command and sets up a user-scoped runtime under `~/.gtn`.

## What is GoodToKnow

GoodToKnow is for people who suspect they are missing useful things — tools, papers, updates, ideas, or opportunities adjacent to what they are already doing — but do not want another noisy feed.

It runs quietly in the background, uses your local context to look outward, and surfaces a small number of things that are actually worth your attention.

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
- `git`
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

Update the installed runtime:

```bash
gtn update
```

Remove the local product installation:

```bash
gtn uninstall
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
