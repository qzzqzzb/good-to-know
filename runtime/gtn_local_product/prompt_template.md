You are running GoodToKnow in unattended local product mode.

Repository root: {repo_root}
Product run id: {run_id}
Repo run dir: {repo_run_dir}
App-state run dir: {app_run_dir}
Expected result json path: {result_json_path}
Expected publish results path: {publish_results_path}

Follow the active runtime skill selected by `bootstrap/stack.yaml` as the source of truth.
Use the existing runtime/output skills rather than inventing a different pipeline.

Requirements for this unattended run:
1. Preserve a single run identity using `{run_id}` and the provided repo run dir.
2. Fetch Notion feedback first and sync it into memory before generating the next wave.
3. Build briefing artifacts into the provided repo run dir.
4. Build the Notion payload.
5. If Notion MCP is available, publish/update recommendations while preserving non-default Status values.
6. Write `{publish_results_path}` if publish results are available.
7. End with a concise status suitable for recording into `{result_json_path}` by the outer runner.
