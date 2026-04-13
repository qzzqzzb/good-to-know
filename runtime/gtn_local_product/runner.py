from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .cadence import parse_cadence, should_run_scheduled_now
from .configuration import state_language
from .locks import ActiveRunError, StaleLockError, acquire_lock, release_lock
from .models import LockInfo, ManifestData, ResultState, StateData
from .paths import GTNPaths, ensure_directories
from .prompting import render_prompt
from .runtime_repo import read_run_output_dir
from .status_data import build_run_summary, latest_run_snapshot, update_history_with_summary, write_run_summary
from .storage import save_json

SubprocessRunner = Callable[[list[str], Path, Path, Path, Path], subprocess.CompletedProcess[str]]
MAX_TRANSIENT_RETRIES = 5
TRANSIENT_FAILURE_MARKERS = (
    "stream disconnected before completion",
    "error sending request for url",
    "connection reset",
    "timed out",
    "429",
    "rate limit",
    "too many requests",
)


class PreflightError(RuntimeError):
    def __init__(self, state: ResultState, message: str):
        self.state = state
        super().__init__(message)


EXIT_CODES = {
    ResultState.SUCCESS: 0,
    ResultState.PARTIAL_SUCCESS: 10,
    ResultState.BLOCKED_MISSING_CODEX_BINARY: 11,
    ResultState.BLOCKED_MISSING_CODEX_AUTH: 12,
    ResultState.BLOCKED_MISSING_SEARCH_CAPABILITY: 13,
    ResultState.BLOCKED_MISSING_NOTION_AUTH: 14,
    ResultState.FAILED_PREFLIGHT: 15,
    ResultState.FAILED: 16,
    ResultState.RUNNING: 17,
}

def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")

def build_run_id() -> str:
    return now_iso().replace(":", "-")

def default_subprocess_runner(
    command: list[str],
    cwd: Path,
    stdout_path: Path,
    stderr_path: Path,
    prompt_path: Path,
) -> subprocess.CompletedProcess[str]:
    with (
        stdout_path.open("w", encoding="utf-8") as out,
        stderr_path.open("w", encoding="utf-8") as err,
    ):
        if command and command[-1] == "-":
            with prompt_path.open("r", encoding="utf-8") as prompt_handle:
                return subprocess.run(command, cwd=cwd, stdin=prompt_handle, stdout=out, stderr=err, text=True, check=False)
        return subprocess.run(command, cwd=cwd, stdout=out, stderr=err, text=True, check=False)


def build_codex_command(
    codex_path: Path,
    runtime_repo: Path,
    app_run_dir: Path,
    last_message_path: Path,
    gtn_home: Path | None = None,
) -> list[str]:
    temp_dir = app_run_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    command: list[str] = []
    if gtn_home is not None:
        command.extend(["env", f"GTN_HOME={gtn_home}"])
    command.extend(
        [
            "TMPDIR=" + str(temp_dir),
            "TMP=" + str(temp_dir),
            "TEMP=" + str(temp_dir),
        ]
    )
    command.extend(
        [
        str(codex_path),
        "--search",
        "exec",
        "--sandbox",
        "workspace-write",
        "--add-dir",
        str(app_run_dir),
        "-C",
        str(runtime_repo),
        "--skip-git-repo-check",
        "-o",
        str(last_message_path),
        "-",
        ]
    )
    return command


def build_codex_resume_command(
    codex_path: Path,
    app_run_dir: Path,
    last_message_path: Path,
    gtn_home: Path | None = None,
    prompt: str = "继续",
) -> list[str]:
    temp_dir = app_run_dir / "tmp"
    temp_dir.mkdir(parents=True, exist_ok=True)
    command: list[str] = []
    if gtn_home is not None:
        command.extend(["env", f"GTN_HOME={gtn_home}"])
    command.extend(
        [
            "TMPDIR=" + str(temp_dir),
            "TMP=" + str(temp_dir),
            "TEMP=" + str(temp_dir),
        ]
    )
    command.extend(
        [
            str(codex_path),
            "exec",
            "resume",
            "--last",
            "--skip-git-repo-check",
            "-o",
            str(last_message_path),
            prompt,
        ]
    )
    return command

def resolve_codex_executable(explicit_path: str | None) -> Path:
    if explicit_path:
        path = Path(explicit_path).expanduser().resolve()
        if path.exists():
            return path
    found = shutil.which("codex")
    if found:
        return Path(found).resolve()
    raise PreflightError(ResultState.BLOCKED_MISSING_CODEX_BINARY, "codex binary not found")

def ensure_codex_auth() -> None:
    auth_path = Path.home() / ".codex" / "auth.json"
    if not auth_path.exists() or not auth_path.read_text(encoding="utf-8").strip():
        raise PreflightError(ResultState.BLOCKED_MISSING_CODEX_AUTH, "codex auth.json missing or empty")

def ensure_search_capability(codex_path: Path) -> None:
    result = subprocess.run([str(codex_path), "--help"], capture_output=True, text=True, check=False)
    if "--search" not in result.stdout:
        raise PreflightError(ResultState.BLOCKED_MISSING_SEARCH_CAPABILITY, "codex --search capability missing")

def ensure_notion_config(runtime_repo: Path) -> None:
    settings = runtime_repo / "output" / "notion-briefing" / "settings.json"
    if not settings.exists():
        return
    config = json.loads(settings.read_text(encoding="utf-8"))
    if not (config.get("database_url") or config.get("parent_page_url")):
        return
    user_cfg = Path.home() / ".codex" / "config.toml"
    if not user_cfg.exists() or "[mcp_servers.notion]" not in user_cfg.read_text(encoding="utf-8", errors="replace"):
        raise PreflightError(ResultState.BLOCKED_MISSING_NOTION_AUTH, "Notion MCP config missing for configured output")

def write_manifest(manifest_path: Path, manifest: ManifestData) -> None:
    save_json(manifest_path, manifest)

def write_result(result_path: Path, state: ResultState, message: str, details: dict | None = None) -> None:
    payload = {
        "state": state.value,
        "message": message,
        "updated_at": now_iso(),
        "details": details or {},
    }
    save_json(result_path, payload)


def read_result_state(result_path: Path) -> tuple[ResultState | None, dict | None]:
    if not result_path.exists():
        return None, None
    try:
        payload = json.loads(result_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None, None
    raw_state = payload.get("state")
    if not raw_state:
        return None, payload
    try:
        return ResultState(raw_state), payload
    except ValueError:
        return None, payload


def exit_code_for_state(state: ResultState) -> int:
    return EXIT_CODES[state]


def _read_log_text(path: Path) -> str:
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8", errors="replace")


def is_transient_codex_failure(
    result: subprocess.CompletedProcess[str],
    stdout_path: Path,
    stderr_path: Path,
    inner_payload: dict | None = None,
) -> tuple[bool, str]:
    haystack = "\n".join(
        [
            str((inner_payload or {}).get("message", "")),
            _read_log_text(stdout_path),
            _read_log_text(stderr_path),
        ]
    ).lower()
    for marker in TRANSIENT_FAILURE_MARKERS:
        if marker in haystack:
            return True, marker
    return False, ""


def latest_completed_run_epoch(paths: GTNPaths) -> float | None:
    latest_summary, _ = latest_run_snapshot(paths)
    updated_at = str((latest_summary or {}).get("updated_at", "")).strip()
    if not updated_at:
        return None
    try:
        return datetime.fromisoformat(updated_at.replace("Z", "+00:00")).timestamp()
    except ValueError:
        return None


def maybe_skip_scheduled_run(paths: GTNPaths, state_data: StateData) -> dict[str, object] | None:
    cadence = str(state_data.cadence or "").strip()
    if not cadence:
        return None
    _, cadence_seconds = parse_cadence(cadence)
    now_epoch = datetime.now(timezone.utc).astimezone().timestamp()
    last_success_epoch = latest_completed_run_epoch(paths)
    decision = should_run_scheduled_now(now_epoch, cadence_seconds, last_success_epoch)
    if decision.should_run:
        return None
    return {
        "message": f"Skipped scheduled run ({decision.reason})",
        "details": {
            "schedule": {
                "reason": decision.reason,
                "previous_slot_at": datetime.fromtimestamp(decision.previous_slot_epoch, tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
                "next_slot_at": datetime.fromtimestamp(decision.next_slot_epoch, tz=timezone.utc).astimezone().isoformat(timespec="seconds"),
            }
        },
    }



def run_once(paths: GTNPaths, state_data: StateData, scheduled: bool = False, runner: SubprocessRunner | None = None) -> int:
    ensure_directories(paths)
    run_id = build_run_id()
    trigger = "scheduled" if scheduled else "manual"
    app_run_dir = paths.runs_dir / run_id
    app_run_dir.mkdir(parents=True, exist_ok=True)

    manifest_path = app_run_dir / "manifest.json"
    result_path = app_run_dir / "result.json"
    stdout_path = app_run_dir / "codex.stdout.log"
    stderr_path = app_run_dir / "codex.stderr.log"
    prompt_path = app_run_dir / "prompt.txt"
    last_message_path = app_run_dir / "last-message.txt"

    runtime_repo = Path(state_data.runtime_repo_path).expanduser().resolve()
    repo_run_dir = read_run_output_dir(runtime_repo) / run_id

    manifest = ManifestData(
        run_id=run_id,
        trigger=trigger,
        state=ResultState.RUNNING.value,
        started_at=now_iso(),
        runtime_repo_path=str(runtime_repo),
        repo_run_dir=str(repo_run_dir),
        app_run_dir=str(app_run_dir),
        result_path=str(result_path),
        last_message_path=str(last_message_path),
        log_path=str(stdout_path),
    )
    write_manifest(manifest_path, manifest)

    lock = LockInfo(
        pid=os.getpid(),
        run_id=run_id,
        runtime_repo_path=str(runtime_repo),
        started_at=manifest.started_at,
        trigger=trigger,
    )
    lock_acquired = False
    exit_code = 0
    final_result_payload: dict | None = None
    final_state: ResultState | None = None

    try:
        try:
            acquire_lock(paths.lock_file, lock)
            lock_acquired = True
        except ActiveRunError as exc:
            final_state = ResultState.FAILED_PREFLIGHT
            final_result_payload = {
                "state": final_state.value,
                "message": str(exc),
                "updated_at": now_iso(),
                "details": {"lock": exc.lock},
            }
            write_result(result_path, final_state, str(exc), {"lock": exc.lock})
            manifest.state = final_state.value
            manifest.error = str(exc)
            manifest.finished_at = now_iso()
            write_manifest(manifest_path, manifest)
            exit_code = 2
        except StaleLockError as exc:
            final_state = ResultState.FAILED_PREFLIGHT
            final_result_payload = {
                "state": final_state.value,
                "message": str(exc),
                "updated_at": now_iso(),
                "details": {"lock": exc.lock},
            }
            write_result(result_path, final_state, str(exc), {"lock": exc.lock})
            manifest.state = final_state.value
            manifest.error = str(exc)
            manifest.finished_at = now_iso()
            write_manifest(manifest_path, manifest)
            exit_code = 3

        if exit_code == 0:
            try:
                if scheduled:
                    skipped = maybe_skip_scheduled_run(paths, state_data)
                    if skipped is not None:
                        final_state = ResultState.SUCCESS
                        final_result_payload = {
                            "state": final_state.value,
                            "message": str(skipped["message"]),
                            "updated_at": now_iso(),
                            "details": dict(skipped["details"]),
                        }
                        write_result(result_path, final_state, str(skipped["message"]), dict(skipped["details"]))
                        manifest.state = final_state.value
                        manifest.finished_at = now_iso()
                        manifest.details = dict(skipped["details"])
                        write_manifest(manifest_path, manifest)
                        exit_code = exit_code_for_state(final_state)
                    else:
                        codex_path = resolve_codex_executable(state_data.codex_path)
                        ensure_codex_auth()
                        ensure_search_capability(codex_path)
                        ensure_notion_config(runtime_repo)
                        prompt_path.write_text(
                            render_prompt(
                                runtime_repo,
                                repo_run_dir,
                                app_run_dir,
                                run_id,
                                language=state_language(state_data),
                            ),
                            encoding="utf-8",
                        )

                        process_runner = runner or default_subprocess_runner
                        command = build_codex_command(codex_path, runtime_repo, app_run_dir, last_message_path, gtn_home=paths.root)
                        details = {
                            "repo_run_dir": str(repo_run_dir),
                            "stdout_log": str(stdout_path),
                            "stderr_log": str(stderr_path),
                            "attempts": [],
                        }
                        inner_payload = None
                        inner_state = None
                        result = None
                        for attempt in range(1, MAX_TRANSIENT_RETRIES + 2):
                            result_path.unlink(missing_ok=True)
                            result = process_runner(command, runtime_repo, stdout_path, stderr_path, prompt_path)
                            inner_state, inner_payload = read_result_state(result_path)
                            attempt_details = {
                                "attempt": attempt,
                                "command": "resume" if "resume" in command else "exec",
                                "returncode": result.returncode,
                            }
                            should_retry, retry_reason = is_transient_codex_failure(result, stdout_path, stderr_path, inner_payload)
                            if should_retry and attempt <= MAX_TRANSIENT_RETRIES:
                                attempt_details["retry_reason"] = retry_reason
                                details["attempts"].append(attempt_details)
                                command = build_codex_resume_command(codex_path, app_run_dir, last_message_path, gtn_home=paths.root)
                                continue
                            details["attempts"].append(attempt_details)
                            break

                        details["returncode"] = result.returncode if result is not None else 1
                        if inner_state is not None:
                            state = inner_state
                            message = str((inner_payload or {}).get("message", "Codex batch run finished"))
                            details["inner_result"] = inner_payload
                            final_result_payload = inner_payload
                        elif result is not None and result.returncode == 0:
                            state = ResultState.SUCCESS if repo_run_dir.exists() else ResultState.PARTIAL_SUCCESS
                            message = "Codex batch run finished"
                            write_result(result_path, state, message, details)
                            final_result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                        else:
                            state = ResultState.FAILED
                            message = f"Codex batch run failed with return code {details['returncode']}"
                            write_result(result_path, state, message, details)
                            final_result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                        final_state = state
                        manifest.state = state.value
                        manifest.finished_at = now_iso()
                        manifest.details = details
                        write_manifest(manifest_path, manifest)
                        exit_code = exit_code_for_state(state)
                else:
                    codex_path = resolve_codex_executable(state_data.codex_path)
                    ensure_codex_auth()
                    ensure_search_capability(codex_path)
                    ensure_notion_config(runtime_repo)
                    prompt_path.write_text(
                        render_prompt(
                            runtime_repo,
                            repo_run_dir,
                            app_run_dir,
                            run_id,
                            language=state_language(state_data),
                        ),
                        encoding="utf-8",
                    )

                    process_runner = runner or default_subprocess_runner
                    details = {
                        "repo_run_dir": str(repo_run_dir),
                        "stdout_log": str(stdout_path),
                        "stderr_log": str(stderr_path),
                        "attempts": [],
                    }
                    command = build_codex_command(codex_path, runtime_repo, app_run_dir, last_message_path, gtn_home=paths.root)
                    inner_payload = None
                    inner_state = None
                    result = None
                    for attempt in range(1, MAX_TRANSIENT_RETRIES + 2):
                        result_path.unlink(missing_ok=True)
                        result = process_runner(command, runtime_repo, stdout_path, stderr_path, prompt_path)
                        inner_state, inner_payload = read_result_state(result_path)
                        attempt_details = {
                            "attempt": attempt,
                            "command": "resume" if "resume" in command else "exec",
                            "returncode": result.returncode,
                        }
                        should_retry, retry_reason = is_transient_codex_failure(result, stdout_path, stderr_path, inner_payload)
                        if should_retry and attempt <= MAX_TRANSIENT_RETRIES:
                            attempt_details["retry_reason"] = retry_reason
                            details["attempts"].append(attempt_details)
                            command = build_codex_resume_command(codex_path, app_run_dir, last_message_path, gtn_home=paths.root)
                            continue
                        details["attempts"].append(attempt_details)
                        break

                    details["returncode"] = result.returncode if result is not None else 1
                    if inner_state is not None:
                        state = inner_state
                        message = str((inner_payload or {}).get("message", "Codex batch run finished"))
                        details["inner_result"] = inner_payload
                        final_result_payload = inner_payload
                    elif result is not None and result.returncode == 0:
                        state = ResultState.SUCCESS if repo_run_dir.exists() else ResultState.PARTIAL_SUCCESS
                        message = "Codex batch run finished"
                        write_result(result_path, state, message, details)
                        final_result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                    else:
                        state = ResultState.FAILED
                        message = f"Codex batch run failed with return code {details['returncode']}"
                        write_result(result_path, state, message, details)
                        final_result_payload = json.loads(result_path.read_text(encoding="utf-8"))
                    final_state = state
                    manifest.state = state.value
                    manifest.finished_at = now_iso()
                    manifest.details = details
                    write_manifest(manifest_path, manifest)
                    exit_code = exit_code_for_state(state)
            except PreflightError as exc:
                final_state = exc.state
                final_result_payload = {
                    "state": exc.state.value,
                    "message": str(exc),
                    "updated_at": now_iso(),
                    "details": {},
                }
                write_result(result_path, exc.state, str(exc))
                manifest.state = exc.state.value
                manifest.error = str(exc)
                manifest.finished_at = now_iso()
                write_manifest(manifest_path, manifest)
                exit_code = exit_code_for_state(exc.state)
            except Exception as exc:
                final_state = ResultState.FAILED
                final_result_payload = {
                    "state": final_state.value,
                    "message": str(exc),
                    "updated_at": now_iso(),
                    "details": {},
                }
                write_result(result_path, final_state, str(exc))
                manifest.state = final_state.value
                manifest.error = str(exc)
                manifest.finished_at = now_iso()
                write_manifest(manifest_path, manifest)
                exit_code = exit_code_for_state(final_state)
        if final_result_payload is None and result_path.exists():
            try:
                final_result_payload = json.loads(result_path.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                final_result_payload = None
        if final_state is not None:
            summary = build_run_summary(run_id, app_run_dir, final_result_payload, repo_run_dir=repo_run_dir)
            write_run_summary(app_run_dir, summary)
            update_history_with_summary(paths.status_history_file, summary)
    finally:
        if lock_acquired:
            release_lock(paths.lock_file)
    return exit_code
