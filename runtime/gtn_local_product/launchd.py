from __future__ import annotations

import os
import plistlib
import subprocess
from pathlib import Path
from typing import Callable

from .paths import DEFAULT_LAUNCH_AGENT_LABEL, GTNPaths

DEFAULT_MINIMAL_PATH = "/usr/local/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"


LaunchctlRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]



def render_launch_agent_plist(paths: GTNPaths, python_executable: Path, cadence_seconds: int) -> bytes:
    env_path = os.environ.get("PATH", DEFAULT_MINIMAL_PATH)
    payload = {
        "Label": DEFAULT_LAUNCH_AGENT_LABEL,
        "ProgramArguments": [
            str(python_executable.resolve()),
            "-m",
            "runtime.gtn_local_product",
            "--root",
            str(paths.root),
            "run",
            "--scheduled",
        ],
        "StartInterval": cadence_seconds,
        "RunAtLoad": False,
        "WorkingDirectory": str(paths.runtime_dir),
        "EnvironmentVariables": {
            "HOME": str(Path.home()),
            "GTN_HOME": str(paths.root),
            "PATH": env_path,
        },
        "StandardOutPath": str(paths.logs_dir / "launchd.stdout.log"),
        "StandardErrorPath": str(paths.logs_dir / "launchd.stderr.log"),
    }
    return plistlib.dumps(payload, sort_keys=True)



def write_launch_agent(paths: GTNPaths, python_executable: Path, cadence_seconds: int) -> Path:
    paths.launch_agent_path.parent.mkdir(parents=True, exist_ok=True)
    paths.launch_agent_path.write_bytes(render_launch_agent_plist(paths, python_executable, cadence_seconds))
    return paths.launch_agent_path



def _run_launchctl(command: list[str], runner: LaunchctlRunner | None = None) -> subprocess.CompletedProcess[str]:
    if runner is not None:
        return runner(command)
    return subprocess.run(command, capture_output=True, text=True, check=False)


def _ensure_launchctl_ok(result: subprocess.CompletedProcess[str], allow_missing: bool = False) -> subprocess.CompletedProcess[str]:
    if result.returncode == 0:
        return result
    stderr = (result.stderr or "") + (result.stdout or "")
    if allow_missing and ("Could not find specified service" in stderr or "No such process" in stderr):
        return result
    raise RuntimeError(stderr.strip() or f"launchctl failed with exit code {result.returncode}")



def load_launch_agent(plist_path: Path, runner: LaunchctlRunner | None = None) -> subprocess.CompletedProcess[str]:
    return _ensure_launchctl_ok(_run_launchctl(["launchctl", "load", "-w", str(plist_path)], runner=runner))



def unload_launch_agent(plist_path: Path, runner: LaunchctlRunner | None = None) -> subprocess.CompletedProcess[str]:
    return _ensure_launchctl_ok(
        _run_launchctl(["launchctl", "unload", "-w", str(plist_path)], runner=runner),
        allow_missing=True,
    )



def launch_agent_loaded(label: str = DEFAULT_LAUNCH_AGENT_LABEL, runner: LaunchctlRunner | None = None) -> bool:
    result = _run_launchctl(["launchctl", "list", label], runner=runner)
    return result.returncode == 0
