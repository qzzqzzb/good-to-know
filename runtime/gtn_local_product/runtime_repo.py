from __future__ import annotations

from pathlib import Path


def read_run_output_dir(runtime_repo: Path) -> Path:
    stack_path = runtime_repo / "bootstrap" / "stack.yaml"
    run_output_dir = "runs"
    if not stack_path.exists():
        return runtime_repo / run_output_dir

    for raw_line in stack_path.read_text(encoding="utf-8").splitlines():
        stripped = raw_line.strip()
        if stripped.startswith("run_output_dir:"):
            _, value = stripped.split(":", 1)
            value = value.strip() or "runs"
            run_output_dir = value
            break

    return runtime_repo / run_output_dir
