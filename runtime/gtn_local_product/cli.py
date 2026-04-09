from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from .cadence import next_run_epoch, parse_cadence
from .launchd import launch_agent_loaded, load_launch_agent, unload_launch_agent, write_launch_agent
from .locks import STALE_LOCK_SECONDS, lock_status, load_lock
from .models import StateData
from .paths import GTNPaths, ensure_directories, resolve_paths
from .runner import resolve_codex_executable, run_once
from .storage import load_json, save_json

PRESERVED_RUNTIME_STATE_PATHS = frozenset(
    {
        "context/naive-context/outbox.md",
        "context/naive-context/settings.json",
        "discovery/web-discovery/outbox.md",
        "memory/mempalace-memory/identity.md",
        "memory/naive-memory/external_findings.md",
        "memory/naive-memory/user_context.md",
        "output/notion-briefing/feedback_outbox.md",
        "output/notion-briefing/page_index.json",
        "output/notion-briefing/settings.json",
    }
)


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def load_state(paths: GTNPaths) -> StateData:
    raw = load_json(paths.state_file, {})
    if not raw:
        return StateData(
            launch_agent_path=str(paths.launch_agent_path),
        )
    return StateData(**raw)

def save_state(paths: GTNPaths, state: StateData) -> None:
    if not state.launch_agent_path:
        state.launch_agent_path = str(paths.launch_agent_path)
    save_json(paths.state_file, state)


def require_initialized_runtime(state: StateData) -> Path:
    if not state.runtime_repo_path:
        raise SystemExit("GTN is not initialized. Run the install/init flow first.")
    runtime_repo = Path(state.runtime_repo_path).expanduser().resolve()
    if not runtime_repo.exists():
        raise SystemExit(f"Configured runtime repo does not exist: {runtime_repo}")
    if not (runtime_repo / "bootstrap" / "stack.yaml").exists():
        raise SystemExit(f"Configured runtime repo is invalid: missing bootstrap/stack.yaml in {runtime_repo}")
    return runtime_repo


def resolve_installed_gtn_wrapper() -> Path | None:
    found = shutil.which("gtn")
    if found:
        return Path(found).expanduser().resolve()
    argv0 = Path(sys.argv[0]).expanduser()
    if argv0.exists():
        return argv0.resolve()
    candidate = Path.home() / ".local" / "bin" / "gtn"
    if candidate.exists():
        return candidate.resolve()
    return None

def cmd_init(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    ensure_directories(paths)
    codex_path = str(resolve_codex_executable(args.codex_path))
    runtime_repo = Path(args.runtime_repo).expanduser().resolve()
    if not runtime_repo.exists():
        raise SystemExit(f"Runtime repo does not exist: {runtime_repo}")
    if not (runtime_repo / "bootstrap" / "stack.yaml").exists():
        raise SystemExit(f"Runtime repo does not look initialized: missing bootstrap/stack.yaml in {runtime_repo}")
    state = load_state(paths)
    state.runtime_repo_path = str(runtime_repo)
    state.codex_path = codex_path
    state.launch_agent_path = str(paths.launch_agent_path)
    save_state(paths, state)
    print(f"Initialized GTN state at {paths.root}")
    print(f"runtime_repo={runtime_repo}")
    print(f"codex_path={codex_path}")
    return 0

def cmd_run(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    require_initialized_runtime(state)
    return run_once(paths, state, scheduled=args.scheduled)

def cmd_freq(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    ensure_directories(paths)
    state = load_state(paths)
    require_initialized_runtime(state)

    cadence, cadence_seconds = parse_cadence(args.cadence)
    codex_path = resolve_codex_executable(state.codex_path)
    state.codex_path = str(codex_path)
    state.cadence = cadence
    state.enabled = True
    plist_path = write_launch_agent(paths, Path(sys.executable), cadence_seconds)
    unload_launch_agent(plist_path)
    load_launch_agent(plist_path)
    save_state(paths, state)
    print(f"Enabled schedule {cadence} via {plist_path}")
    return 0

def cmd_stop(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    unload_launch_agent(paths.launch_agent_path)
    state.enabled = False
    save_state(paths, state)
    print("Disabled future scheduled runs")
    return 0


def dirty_runtime_paths(runtime_repo: Path) -> set[str]:
    result = subprocess.run(
        ["git", "-C", str(runtime_repo), "status", "--short", "--untracked-files=no"],
        check=True,
        capture_output=True,
        text=True,
    )
    paths: set[str] = set()
    for line in result.stdout.splitlines():
        if not line:
            continue
        path = line[3:]
        if " -> " in path:
            path = path.split(" -> ", 1)[1]
        paths.add(path)
    return paths


def snapshot_preserved_runtime_state(runtime_repo: Path, dirty_paths: set[str]) -> dict[str, bytes | None]:
    unsupported = sorted(path for path in dirty_paths if path not in PRESERVED_RUNTIME_STATE_PATHS)
    if unsupported:
        formatted = "\n".join(f"  - {path}" for path in unsupported)
        raise SystemExit(
            "Cannot update while non-runtime state files have local changes.\n"
            "Commit or stash these files and retry:\n"
            f"{formatted}"
        )

    snapshots: dict[str, bytes | None] = {}
    for rel_path in sorted(dirty_paths):
        file_path = runtime_repo / rel_path
        snapshots[rel_path] = file_path.read_bytes() if file_path.exists() else None
    return snapshots


def reset_runtime_paths_to_head(runtime_repo: Path, rel_paths: list[str]) -> None:
    if not rel_paths:
        return
    subprocess.run(["git", "-C", str(runtime_repo), "checkout", "HEAD", "--", *rel_paths], check=True)


def restore_runtime_state_snapshots(runtime_repo: Path, snapshots: dict[str, bytes | None]) -> None:
    for rel_path, content in snapshots.items():
        file_path = runtime_repo / rel_path
        if content is None:
            if file_path.exists():
                file_path.unlink()
            continue
        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_bytes(content)


def cmd_update(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    runtime_repo = require_initialized_runtime(state)
    current_lock_state = lock_status(paths.lock_file)
    if current_lock_state == "active":
        lock = load_lock(paths.lock_file) or {}
        run_id = lock.get("run_id", "(unknown)")
        raise SystemExit(f"Cannot update while a GTN run is active (run_id={run_id}).")

    dirty_paths = dirty_runtime_paths(runtime_repo)
    snapshots = snapshot_preserved_runtime_state(runtime_repo, dirty_paths)
    reset_runtime_paths_to_head(runtime_repo, sorted(snapshots))

    try:
        subprocess.run(["git", "-C", str(runtime_repo), "pull", "--ff-only"], check=True)
        subprocess.run([sys.executable, "-m", "pip", "install", "--editable", str(runtime_repo)], check=True)
    finally:
        restore_runtime_state_snapshots(runtime_repo, snapshots)

    if snapshots:
        print(f"Preserved local GTN state for {len(snapshots)} file(s).")
    print(f"Updated GTN runtime at {runtime_repo}")
    return 0


def cmd_uninstall(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    if not args.yes:
        if not sys.stdin.isatty():
            raise SystemExit("Refusing to uninstall without --yes in non-interactive mode.")
        confirm = input(f"Remove GTN runtime at {paths.root} and disable scheduling? [y/N] ").strip().lower()
        if confirm not in {"y", "yes"}:
            print("Aborted.")
            return 1

    unload_launch_agent(paths.launch_agent_path)
    if paths.launch_agent_path.exists():
        paths.launch_agent_path.unlink()

    wrapper = resolve_installed_gtn_wrapper()
    if wrapper and wrapper.exists():
        wrapper.unlink()

    if paths.root.exists():
        shutil.rmtree(paths.root)

    print(f"Uninstalled GTN from {paths.root}")
    return 0

def latest_result(paths: GTNPaths) -> tuple[dict | None, Path | None]:
    runs = sorted([path for path in paths.runs_dir.iterdir() if path.is_dir()]) if paths.runs_dir.exists() else []
    if not runs:
        return None, None
    latest = runs[-1]
    result_path = latest / "result.json"
    if not result_path.exists():
        return None, latest
    return json.loads(result_path.read_text(encoding="utf-8")), latest

def cmd_status(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    result, latest_run_dir = latest_result(paths)
    cadence = state.cadence or "(unset)"
    enabled = state.enabled and launch_agent_loaded()
    lock = load_lock(paths.lock_file)
    lock_state = lock_status(paths.lock_file)

    next_run = None
    if state.enabled and state.cadence:
        _, seconds = parse_cadence(state.cadence)
        last_epoch = None
        if result and result.get("updated_at"):
            last_epoch = datetime.fromisoformat(result["updated_at"].replace("Z", "+00:00")).timestamp()
        estimate = next_run_epoch(last_epoch, seconds)
        if estimate is not None:
            next_run = datetime.fromtimestamp(estimate, tz=timezone.utc).astimezone().isoformat(timespec="seconds")

    print(f"enabled={enabled}")
    print(f"cadence={cadence}")
    print(f"runtime_repo={state.runtime_repo_path or '(unset)'}")
    print(f"launch_agent={paths.launch_agent_path}")
    print(f"lock_state={lock_state}")
    if lock:
        print(f"lock_run_id={lock.get('run_id', '(unknown)')}")
    if latest_run_dir:
        print(f"last_run_dir={latest_run_dir}")
    if result:
        print(f"last_result={result.get('state', '(unknown)')}")
        print(f"last_updated={result.get('updated_at', '(unknown)')}")
    print(f"next_run={next_run or '(unknown)'}")
    print(f"stale_lock_seconds={STALE_LOCK_SECONDS}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gtn", description="GoodToKnow local product shell")
    parser.add_argument("--root", help="Override GTN home directory (default: ~/.gtn)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help=argparse.SUPPRESS)
    init_parser.add_argument("--runtime-repo", required=True)
    init_parser.add_argument("--codex-path")
    init_parser.set_defaults(func=cmd_init)

    run_parser = subparsers.add_parser("run", help="Run GoodToKnow now")
    run_parser.add_argument("--scheduled", action="store_true", help=argparse.SUPPRESS)
    run_parser.set_defaults(func=cmd_run)

    freq_parser = subparsers.add_parser("freq", help="Set the recurring run cadence")
    freq_parser.add_argument("cadence")
    freq_parser.set_defaults(func=cmd_freq)

    stop_parser = subparsers.add_parser("stop", help="Disable future scheduled runs")
    stop_parser.set_defaults(func=cmd_stop)

    update_parser = subparsers.add_parser("update", help="Update the installed GTN runtime")
    update_parser.set_defaults(func=cmd_update)

    uninstall_parser = subparsers.add_parser("uninstall", help="Remove GTN runtime, state, and schedule")
    uninstall_parser.add_argument("--yes", action="store_true", help="Skip confirmation prompt")
    uninstall_parser.set_defaults(func=cmd_uninstall)

    status_parser = subparsers.add_parser("status", help="Show scheduler and run status")
    status_parser.set_defaults(func=cmd_status)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
