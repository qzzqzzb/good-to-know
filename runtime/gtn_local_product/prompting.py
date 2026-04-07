from __future__ import annotations

from pathlib import Path


def render_prompt(runtime_repo: Path, repo_run_dir: Path, app_run_dir: Path, run_id: str) -> str:
    result_path = app_run_dir / "result.json"
    return f"""You are running GoodToKnow unattended as a local scheduled product run.

Working repo: `{runtime_repo}`
Product run id: `{run_id}`
Repo run dir: `{repo_run_dir}`
App-state run dir: `{app_run_dir}`

Follow the active runtime selected by `bootstrap/stack.yaml` and treat the runtime and output skills as the source of truth.

Important runtime seam:
- Preserve the provided run identity by keeping all repo artifacts under `{repo_run_dir}`.
- When invoking deterministic local helpers, pass the exact run identity with:
  `python3 runtime/codex-agent-loop/scripts/run_active_stack.py --stage <stage> --run-id "{run_id}" --run-dir "{repo_run_dir}"`
- Do not let helper scripts invent a different run id for this scheduled product run.

Required outcomes:
1. Run the deterministic pre-discovery phase first.
2. Follow the active discovery skills from `bootstrap/stack.yaml` and use Codex web search when required by those skills.
3. If the active output skill supports feedback collection, fetch feedback first, then sync/ingest it using that skill's own protocol.
4. Run the deterministic post-discovery phase so `briefing.json`, `briefing.md`, and `notion-payload.json` end up under `{repo_run_dir}`.
5. If the active output skill publishes to an external destination, preserve user feedback fields and write any skill-owned publish-result artifact that the output skill expects.
6. If you can determine a machine-readable completion state, write a compact structured result file at `{result_path}`; otherwise leave that file for the outer product runner.

Do not ask the user follow-up questions. Operate within the existing skill contracts and repo boundaries.
"""
