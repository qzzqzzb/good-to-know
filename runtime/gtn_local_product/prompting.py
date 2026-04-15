from __future__ import annotations

from pathlib import Path


def render_prompt(runtime_repo: Path, repo_run_dir: Path, app_run_dir: Path, run_id: str, language: str = "en") -> str:
    result_path = app_run_dir / "result.json"
    normalized_language = (language or "en").strip().lower() or "en"
    if normalized_language == "zh":
        language_instruction = (
            "Recommendation content language: `zh`\n"
            "- Write recommendation content fields (`title`, `summary`, `why_recommended`, `digest`) in Chinese-first natural prose.\n"
            "- Keep necessary English product names, proper nouns, and terms when that reads more naturally.\n"
            "- Do not localize operational text, status text, or downstream output labels/schema."
        )
    else:
        language_instruction = (
            "Recommendation content language: `en`\n"
            "- Write recommendation content fields (`title`, `summary`, `why_recommended`, `digest`) in English.\n"
            "- Do not localize operational text, status text, or downstream output labels/schema."
        )
    return f"""You are running GoodToKnow unattended as a local scheduled product run.

Working repo: `{runtime_repo}`
Product run id: `{run_id}`
Repo run dir: `{repo_run_dir}`
App-state run dir: `{app_run_dir}`

Follow the active runtime selected by `bootstrap/stack.yaml` and treat the runtime and output skills as the source of truth.

Important isolation rules for unattended product runs:
- Ignore any `.omx/` directory contents in this runtime repo. They are not part of the GTN runtime contract.
- Do not use `omx_*` MCP tools, Ralph/Ralplan workflows, or session-restoration logic in this unattended run.
- Do not inspect or rely on parent-directory `AGENTS.md` files outside the provided runtime repo.
- Stay inside the stack/runtime/output contracts available on disk under this repo.

Important runtime seam:
- Preserve the provided run identity by keeping all repo artifacts under `{repo_run_dir}`.
- When invoking deterministic local helpers, pass the exact run identity with:
  `python3 runtime/codex-agent-loop/scripts/run_active_stack.py --stage <stage> --run-id "{run_id}" --run-dir "{repo_run_dir}"`
- Do not let helper scripts invent a different run id for this scheduled product run.

Recommendation-writing contract:
{language_instruction}

Required outcomes:
1. Run the deterministic pre-discovery phase first.
2. Follow the active discovery skills from `bootstrap/stack.yaml` and use Codex web search when required by those skills.
3. If the active output skill supports feedback collection, fetch feedback first, then sync/ingest it using that skill's own protocol.
4. Run the deterministic post-discovery phase so `briefing.json`, `briefing.md`, and the main-track output payload artifacts (for example `notion-payload.json` and `feishu-payload.json`) end up under `{repo_run_dir}`.
5. If `GTN_HOME/hard-rules/subscriptions.json` contains subscriptions, prepare the hard-rule worklist with:
   `python3 runtime/codex-agent-loop/scripts/prepare_hard_rule_worklist.py --run-dir "{repo_run_dir}"`
6. If the hard-rule worklist contains eligible subscriptions, use Codex native web search/browsing to research each subscription and write a normalized JSON list to `{repo_run_dir}/hard-rule-items.json`.
   - Read `runtime/codex-agent-loop/references/hard-rule-web-research.md` before researching this track.
   - For `producthunt`, follow the live-web inspection posture in that reference: browse current Product Hunt pages, prefer canonical Product Hunt URLs, and do not guess from memory.
   - For `arxiv`, use native web search/browsing to find current arXiv papers relevant to the topic, and prefer canonical arXiv abstract URLs plus published timestamps visible on arXiv.
   - Each hard-rule item should include: `subscription_id`, `source`, `topic`, `title`, `summary`, `link`, `published_at`, `dedup_key`, `raw`.
7. Finalize hard-rule artifacts and refresh-state with:
   `python3 runtime/codex-agent-loop/scripts/run_hard_rules.py --run-id "{run_id}" --run-dir "{repo_run_dir}" --items-json "{repo_run_dir}/hard-rule-items.json" --worklist-json "{repo_run_dir}/hard-rule-worklist.json" --result-path "{repo_run_dir}/hard-rule-result.json"`
8. For each active hard-rule output skill, build the corresponding payload from `hard-rule-briefing.json` and publish/prepare it using that skill's own protocol.
9. If the active output skill publishes to an external destination, preserve user feedback fields and write any skill-owned publish-result artifact that the output skill expects.
10. If Feishu or another non-primary push destination fails, do not keep investigating indefinitely once the local artifacts and Notion-facing outputs are already complete. Record the destination failure in its publish-result artifact and stop with a compact partial-success result.
11. Write a compact structured result file at `{result_path}` before stopping:
   - `success` when the main local artifacts and required configured destinations succeed
   - `partial_success` when the main local artifacts are complete but an auxiliary destination such as Feishu fails
   Include a short message and any useful destination-specific details you already know.

Do not ask the user follow-up questions. Operate within the existing skill contracts and repo boundaries.
"""
