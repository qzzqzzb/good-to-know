from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR.parent
REPO_ROOT = RUNTIME_DIR.parent.parent
STACK_PATH = REPO_ROOT / "bootstrap" / "stack.yaml"


def parse_stack(path: Path) -> dict:
    lines = path.read_text(encoding="utf-8").splitlines()
    data: dict[str, object] = {}
    current_list_key: str | None = None

    for raw_line in lines:
        line = raw_line.rstrip()
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if stripped.startswith("- "):
            if current_list_key is None:
                raise ValueError(f"List item without a key in {path}: {raw_line}")
            data.setdefault(current_list_key, [])
            assert isinstance(data[current_list_key], list)
            data[current_list_key].append(stripped[2:].strip())
            continue

        current_list_key = None
        if ":" not in stripped:
            raise ValueError(f"Unsupported stack line in {path}: {raw_line}")

        key, raw_value = stripped.split(":", 1)
        key = key.strip()
        value = raw_value.strip()
        if value:
            data[key] = value
        else:
            data[key] = []
            current_list_key = key

    return data


def run_python(script_path: Path, *args: str) -> None:
    command = [sys.executable, str(script_path), *args]
    subprocess.run(command, check=True, cwd=REPO_ROOT)


def ensure_skill_path(relative_path: str) -> Path:
    skill_path = (REPO_ROOT / relative_path).resolve()
    if not skill_path.exists():
        raise FileNotFoundError(f"Skill path not found: {relative_path}")
    return skill_path


def stack_run_output_dir(stack: dict) -> Path:
    configured = str(stack.get("run_output_dir", "runs") or "runs")
    return (REPO_ROOT / configured).resolve()


def resolve_run_dir(stack: dict, run_id: str | None, explicit_run_dir: Path | None) -> tuple[str, Path]:
    if explicit_run_dir is not None:
        resolved = explicit_run_dir.resolve()
        return run_id or resolved.name, resolved
    effective_run_id = run_id or datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds").replace(":", "-")
    return effective_run_id, stack_run_output_dir(stack) / effective_run_id


def run_context_phase(stack: dict) -> None:
    memory_skill = ensure_skill_path(str(stack["memory_skill"]))
    ingest_context = memory_skill / "scripts" / "ingest_context.py"

    for relative in stack.get("context_skills", []):
        skill_path = ensure_skill_path(str(relative))
        collect_script = skill_path / "scripts" / "collect.py"
        outbox_path = skill_path / "outbox.md"
        run_python(collect_script)
        run_python(ingest_context, str(outbox_path))


def run_findings_phase(stack: dict) -> None:
    memory_skill = ensure_skill_path(str(stack["memory_skill"]))
    ingest_findings = memory_skill / "scripts" / "ingest_findings.py"

    for relative in stack.get("discovery_skills", []):
        skill_path = ensure_skill_path(str(relative))
        outbox_path = skill_path / "outbox.md"
        if not outbox_path.exists():
            continue
        run_python(ingest_findings, str(outbox_path))


def run_feedback_phase(stack: dict) -> None:
    memory_skill = ensure_skill_path(str(stack["memory_skill"]))
    ingest_context = memory_skill / "scripts" / "ingest_context.py"

    for relative in stack.get("output_skills", []):
        skill_path = ensure_skill_path(str(relative))
        feedback_outbox = skill_path / "feedback_outbox.md"
        if not feedback_outbox.exists():
            continue
        run_python(ingest_context, str(feedback_outbox))


def build_outputs(stack: dict, run_id: str | None = None, run_dir: Path | None = None) -> Path:
    build_briefing = RUNTIME_DIR / "scripts" / "build_briefing.py"
    repo_run_id, repo_run_dir = resolve_run_dir(stack, run_id=run_id, explicit_run_dir=run_dir)
    repo_run_dir.mkdir(parents=True, exist_ok=True)

    run_python(build_briefing, "--run-id", repo_run_id, "--run-dir", str(repo_run_dir))

    briefing_path = repo_run_dir / "briefing.json"
    for relative in stack.get("output_skills", []):
        skill_path = ensure_skill_path(str(relative))
        build_payload = skill_path / "scripts" / "build_notion_payload.py"
        if build_payload.exists():
            run_python(build_payload, str(briefing_path))

    return repo_run_dir


def write_result(result_path: Path, state: str, stage: str, run_id: str, run_dir: Path | None) -> None:
    payload = {
        "state": state,
        "stage": stage,
        "run_id": run_id,
        "run_dir": str(run_dir) if run_dir is not None else None,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
    }
    result_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Run deterministic parts of the active stack.")
    parser.add_argument(
        "--stage",
        choices=("pre-discovery", "post-discovery", "local-only"),
        default="local-only",
        help=(
            "pre-discovery: refresh context and ingest it; "
            "post-discovery: ingest discovery findings and build outputs; "
            "local-only: do both deterministic phases assuming discovery outboxes are already ready"
        ),
    )
    parser.add_argument("--run-id", help="Optional explicit run id for repo artifact generation")
    parser.add_argument("--run-dir", help="Optional explicit run directory for repo artifact generation")
    parser.add_argument("--result-path", help="Optional structured result JSON output path")
    args = parser.parse_args()

    stack = parse_stack(STACK_PATH)
    resolved_run_dir = Path(args.run_dir).resolve() if args.run_dir else None
    effective_run_id = args.run_id or (resolved_run_dir.name if resolved_run_dir else datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds").replace(":", "-"))
    repo_run_dir: Path | None = None

    if args.stage in {"pre-discovery", "local-only"}:
        run_context_phase(stack)

    if args.stage in {"post-discovery", "local-only"}:
        run_findings_phase(stack)
        run_feedback_phase(stack)
        repo_run_dir = build_outputs(stack, run_id=effective_run_id, run_dir=resolved_run_dir)

    if args.result_path:
        write_result(Path(args.result_path).resolve(), "success", args.stage, effective_run_id, repo_run_dir)

    print(f"[codex-agent-loop] completed stage: {args.stage}")


if __name__ == "__main__":
    main()
