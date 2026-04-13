from __future__ import annotations

import argparse
import importlib.resources as pkg_resources
import json
import shutil
import subprocess
import sys
import tarfile
import tempfile
from urllib.parse import urlparse
from urllib.request import urlopen
from datetime import datetime, timezone
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cadence import parse_cadence
from .configuration import (
    CONFIG_KEYS,
    TIER_PRESETS,
    apply_tier_to_runtime,
    get_config_value,
    normalize_tier,
    set_feishu_webhook_url,
    set_notion_page_url,
    state_tier,
)
from .hard_rule_config import (
    SUPPORTED_HARD_RULE_SOURCES,
    build_subscriptions_from_sources,
    delete_subscription,
    load_subscriptions,
    parse_topic_overrides,
    prompt_source_selection,
    supported_sources_lines,
    upsert_subscriptions,
)
from .launchd import launch_agent_loaded, load_launch_agent, unload_launch_agent, write_launch_agent
from .locks import STALE_LOCK_SECONDS, lock_status, load_lock
from .models import StateData
from .paths import GTNPaths, ensure_directories, resolve_paths
from .runner import resolve_codex_executable, run_once
from .status_dashboard import build_status_dashboard, build_status_snapshot
from .status_data import ensure_state_initialized_at
from .storage import load_json, save_json

DEFAULT_RUNTIME_BUNDLE_URL = "https://github.com/qzzqzzb/good-to-know/archive/refs/heads/main.tar.gz"
PRESERVED_RUNTIME_STATE_PATHS = frozenset(
    {
        "context/naive-context/outbox.md",
        "context/naive-context/settings.json",
        "discovery/web-discovery/outbox.md",
        "memory/mempalace-memory/.data",
        "memory/mempalace-memory/identity.md",
        "memory/naive-memory/external_findings.md",
        "memory/naive-memory/user_context.md",
        "output/feishu-briefing/settings.json",
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
    state = ensure_state_initialized_at(state)
    if not state.launch_agent_path:
        state.launch_agent_path = str(paths.launch_agent_path)
    save_json(paths.state_file, state)


def resolve_runtime_bundle_url(explicit_url: str | None = None) -> str:
    return explicit_url or DEFAULT_RUNTIME_BUNDLE_URL


def runtime_uses_git_checkout(runtime_repo: Path) -> bool:
    return (runtime_repo / ".git").exists()


def copy_tree(source, destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for item in source.iterdir():
        target = destination / item.name
        if item.is_dir():
            copy_tree(item, target)
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(item.read_bytes())


def is_mutable_runtime_path(relative_path: Path) -> bool:
    rel = relative_path.as_posix()
    return any(rel == prefix or rel.startswith(f"{prefix}/") for prefix in PRESERVED_RUNTIME_STATE_PATHS)


def download_runtime_bundle(bundle_url: str, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    parsed = urlparse(bundle_url)
    bundle_name = Path(parsed.path).name or "runtime-bundle.tar.gz"
    bundle_path = destination_dir / bundle_name
    with urlopen(bundle_url) as response:
        bundle_path.write_bytes(response.read())
    return bundle_path


def extract_runtime_bundle(bundle_path: Path, destination_dir: Path) -> Path:
    destination_dir.mkdir(parents=True, exist_ok=True)
    with tarfile.open(bundle_path, "r:gz") as archive:
        members = archive.getmembers()
        archive.extractall(destination_dir)
    top_level_dirs = {
        member.name.split("/", 1)[0]
        for member in members
        if member.name and member.name.strip("/") and "/" in member.name
    }
    if len(top_level_dirs) == 1:
        extracted_root = destination_dir / next(iter(top_level_dirs))
    else:
        extracted_root = destination_dir
    if not (extracted_root / "bootstrap" / "stack.yaml").exists():
        raise SystemExit(f"Runtime bundle did not contain a valid GTN runtime: {bundle_path}")
    return extracted_root


def hydrate_runtime_bundle(runtime_repo: Path, bundle_url: str) -> Path:
    with tempfile.TemporaryDirectory(prefix="gtn-runtime-bundle-") as tmp:
        tmp_path = Path(tmp)
        bundle_path = download_runtime_bundle(bundle_url, tmp_path)
        extracted_root = extract_runtime_bundle(bundle_path, tmp_path / "extract")
        if runtime_repo.exists():
            shutil.rmtree(runtime_repo)
        runtime_repo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copytree(extracted_root, runtime_repo)
    return runtime_repo.resolve()


def hydrate_packaged_runtime(runtime_repo: Path) -> Path:
    source_root = Path(str(pkg_resources.files("runtime.gtn_local_product").joinpath("resources/default_runtime")))
    if not source_root.is_dir():
        raise SystemExit("Installed GTN package does not contain the default runtime resources.")
    if runtime_repo.exists():
        shutil.rmtree(runtime_repo)
    runtime_repo.parent.mkdir(parents=True, exist_ok=True)
    runtime_repo.mkdir(parents=True, exist_ok=True)

    # Mutable state/config files are copied into GTN_HOME; immutable defaults stay linked
    # back to the installed package so the package remains the primary source of truth.
    for source_path in sorted(source_root.rglob("*")):
        relative = source_path.relative_to(source_root)
        target = runtime_repo / relative
        if source_path.is_dir():
            target.mkdir(parents=True, exist_ok=True)
            continue
        target.parent.mkdir(parents=True, exist_ok=True)
        if is_mutable_runtime_path(relative):
            target.write_bytes(source_path.read_bytes())
        else:
            target.symlink_to(source_path)

    for relative in sorted(PRESERVED_RUNTIME_STATE_PATHS):
        target = runtime_repo / relative
        if "." not in Path(relative).name:
            target.mkdir(parents=True, exist_ok=True)
    return runtime_repo.resolve()


def snapshot_runtime_state_files(runtime_repo: Path) -> dict[str, bytes | None]:
    snapshots: dict[str, bytes | None] = {}
    for rel_path in sorted(PRESERVED_RUNTIME_STATE_PATHS):
        file_path = runtime_repo / rel_path
        if not file_path.exists():
            continue
        snapshots[rel_path] = file_path.read_bytes()
    return snapshots


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

def summarize_feishu_webhook(webhook_url: str) -> str:
    value = webhook_url.strip()
    if not value:
        return "Not configured"
    if "://" in value:
        scheme, remainder = value.split("://", 1)
        host = remainder.split("/", 1)[0]
        return f"{scheme}://{host}/... (configured)"
    return "(configured)"


def record_initial_user_profile(runtime_repo: Path, profile_text: str) -> None:
    script_path = runtime_repo / "memory" / "mempalace-memory" / "scripts" / "record_user_profile.py"
    if not script_path.exists():
        return
    result = subprocess.run(
        [sys.executable, str(script_path), profile_text],
        check=False,
        cwd=runtime_repo,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        message = (result.stderr or result.stdout or "profile recorder failed").strip().splitlines()[-1]
        raise RuntimeError(message)


def prompt_multiline(prompt: str) -> str:
    Console().print(prompt)
    lines: list[str] = []
    while True:
        line = input().rstrip("\n")
        if not line:
            break
        lines.append(line)
    return "\n".join(lines).strip()


def prompt_yes_no(question: str, default: bool = False) -> bool:
    suffix = " [Y/n] " if default else " [y/N] "
    answer = input(question + suffix).strip().lower()
    if not answer:
        return default
    return answer in {"y", "yes"}


def summarize_current_value(value: str, limit: int = 72) -> str:
    clean = " ".join(value.split())
    if not clean:
        return "(not set)"
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 3].rstrip()}..."


def current_profile_text(runtime_repo: Path) -> str:
    identity_path = runtime_repo / "memory" / "mempalace-memory" / "identity.md"
    if not identity_path.exists():
        return ""
    text = identity_path.read_text(encoding="utf-8").strip()
    if not text or "No user profile has been recorded yet." in text:
        return ""
    return text


def render_setup_prompt_block(
    console: Console,
    title: str,
    current_value: str,
    *,
    note: str | None = None,
) -> None:
    current_text = summarize_current_value(current_value)
    lines = [f"Current value: {current_text}"]
    if current_value.strip():
        lines[-1] += " (enter to keep and skip)"
    if note:
        lines.extend(["", note])
    console.print(
        Panel(
            "\n".join(lines),
            title=f"🚀 {title}",
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(1, 2),
        )
    )
    console.print()


def prompt_value_with_current(
    console: Console,
    title: str,
    current_value: str,
    *,
    note: str | None = None,
) -> str:
    render_setup_prompt_block(console, title, current_value, note=note)
    entered = input("New value: ").strip()
    if not entered and current_value.strip():
        return current_value.strip()
    return entered


def prompt_multiline_with_current(
    console: Console,
    title: str,
    current_value: str,
    *,
    note: str | None = None,
) -> str | None:
    render_setup_prompt_block(console, title, current_value, note=note)
    console.print("New value:")
    lines: list[str] = []
    while True:
        line = input().rstrip("\n")
        if not line:
            break
        lines.append(line)
    if not lines and current_value.strip():
        return None
    return "\n".join(lines).strip()


def configure_hard_rules(paths: GTNPaths, interactive: bool, args: argparse.Namespace) -> str:
    selected_sources = list(getattr(args, "hard_rule_sources", []) or [])
    overall_topic = str(getattr(args, "hard_rule_topic", "") or "").strip()
    overrides = parse_topic_overrides(list(getattr(args, "hard_rule_topic_overrides", []) or []))

    if interactive and not selected_sources:
        if prompt_yes_no("Configure hard-rule recommendations now?", default=False):
            Console().print("\nAvailable hard-rule sources:")
            for line in supported_sources_lines():
                Console().print(f"  {line}")
            raw_selection = input(
                "Select sources by number or source id (comma separated, blank to skip): "
            ).strip()
            if raw_selection:
                selected_sources = prompt_source_selection(raw_selection)
                overall_topic = input("Overall topic for selected sources: ").strip()
                source_labels = {item.source_id: item.label for item in SUPPORTED_HARD_RULE_SOURCES}
                for source in selected_sources:
                    override = input(
                        f"Topic override for {source_labels.get(source, source)} (blank to keep overall topic): "
                    ).strip()
                    if override:
                        overrides[source] = override

    if not selected_sources:
        return "Not configured"

    subscriptions = build_subscriptions_from_sources(selected_sources, overall_topic, overrides)
    if not subscriptions:
        return "Not configured"
    persisted = upsert_subscriptions(paths, subscriptions)
    return f"{len(subscriptions)} subscription(s) configured ({len(persisted)} total)"


def run_onboarding(
    paths: GTNPaths,
    runtime_repo: Path,
    tier: str,
    notion_page_url: str | None,
    feishu_webhook_url: str | None,
    user_profile: str | None,
    args: argparse.Namespace,
    no_prompt: bool = False,
) -> dict[str, str]:
    console = Console()
    interactive = sys.stdin.isatty() and not no_prompt
    results = {
        "tier": tier,
        "notion": "Not configured",
        "feishu": "Not configured",
        "profile": "Not recorded",
        "hard_rules": "Not configured",
    }

    apply_tier_to_runtime(runtime_repo, tier)

    current_notion_page_url = str(
        load_json(runtime_repo / "output" / "notion-briefing" / "settings.json", {}).get("parent_page_url", "")
    ).strip()
    effective_notion_page_url = (notion_page_url or "").strip()
    if not effective_notion_page_url and interactive:
        effective_notion_page_url = prompt_value_with_current(
            console,
            "Notion URL setup",
            current_notion_page_url,
        )
    if effective_notion_page_url:
        set_notion_page_url(runtime_repo, effective_notion_page_url)
        results["notion"] = effective_notion_page_url

    current_feishu_webhook_url = str(
        load_json(runtime_repo / "output" / "feishu-briefing" / "settings.json", {}).get("webhook_url", "")
    ).strip()
    effective_feishu_webhook_url = (feishu_webhook_url or "").strip()
    if not effective_feishu_webhook_url and interactive:
        effective_feishu_webhook_url = prompt_value_with_current(
            console,
            "Feishu webhook setup",
            current_feishu_webhook_url,
        )
    if effective_feishu_webhook_url:
        set_feishu_webhook_url(runtime_repo, effective_feishu_webhook_url)
        results["feishu"] = summarize_feishu_webhook(effective_feishu_webhook_url)

    current_profile = current_profile_text(runtime_repo)
    effective_user_profile = (user_profile or "").strip()
    if not effective_user_profile and interactive:
        effective_user_profile = prompt_multiline_with_current(
            console,
            "Profile setup",
            current_profile,
            note=(
                "Describe yourself in a few lines so GoodToKnow can make better recommendations.\n"
                "Include your interests, the work you do on this computer, and recurring topics you care about.\n"
                "Finish by entering an empty line."
            ),
        )
    if effective_user_profile is None:
        results["profile"] = "Recorded"
    elif effective_user_profile:
        try:
            record_initial_user_profile(runtime_repo, effective_user_profile)
        except (subprocess.CalledProcessError, RuntimeError) as exc:
            results["profile"] = f"Not recorded ({exc})"
        else:
            results["profile"] = "Recorded"
    results["hard_rules"] = configure_hard_rules(paths, interactive, args)
    return results


def render_setup_banner(console: Console, paths: GTNPaths) -> None:
    title = Text()
    title.append("🚀 GTN Setup", style="bold bright_cyan")
    title.append("  first-time local bootstrap", style="dim")
    console.print(
        Panel(
            title,
            border_style="bright_cyan",
            box=box.ROUNDED,
            padding=(0, 2),
            subtitle=str(paths.root),
        )
    )


def render_setup_summary(
    console: Console,
    paths: GTNPaths,
    runtime_repo: Path,
    codex_path: str,
    runtime_bundle_url: str,
    onboarding: dict[str, str],
) -> None:
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("GTN home", str(paths.root))
    table.add_row("Runtime", str(runtime_repo))
    table.add_row("Codex", codex_path)
    if runtime_bundle_url:
        table.add_row("Bundle", runtime_bundle_url)
    table.add_row("Tier", onboarding["tier"])
    table.add_row("Notion", onboarding["notion"])
    table.add_row("Feishu", onboarding["feishu"])
    table.add_row("Profile", onboarding["profile"])
    table.add_row("Hard rules", onboarding["hard_rules"])
    console.print(Panel(table, title="Setup Summary", border_style="green", box=box.ROUNDED))

def cmd_init(args: argparse.Namespace) -> int:
    console = Console()
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    ensure_directories(paths)
    codex_path = str(resolve_codex_executable(args.codex_path))
    render_setup_banner(console, paths)
    runtime_bundle_url = ""
    if args.runtime_repo:
        runtime_repo = Path(args.runtime_repo).expanduser().resolve()
        if not runtime_repo.exists():
            raise SystemExit(f"Runtime repo does not exist: {runtime_repo}")
        if not (runtime_repo / "bootstrap" / "stack.yaml").exists():
            raise SystemExit(f"Runtime repo does not look initialized: missing bootstrap/stack.yaml in {runtime_repo}")
    elif args.runtime_bundle_url:
        runtime_bundle_url = resolve_runtime_bundle_url(args.runtime_bundle_url)
        runtime_repo = hydrate_runtime_bundle(paths.runtime_dir, runtime_bundle_url)
    else:
        runtime_repo = hydrate_packaged_runtime(paths.runtime_dir)
    state = load_state(paths)
    state.runtime_repo_path = str(runtime_repo)
    state.runtime_bundle_url = runtime_bundle_url
    state.codex_path = codex_path
    state.tier = normalize_tier(getattr(args, "tier", None))
    state.launch_agent_path = str(paths.launch_agent_path)
    save_state(paths, state)
    onboarding = run_onboarding(
        paths=paths,
        runtime_repo=runtime_repo,
        tier=state.tier,
        notion_page_url=getattr(args, "notion_page_url", None),
        feishu_webhook_url=getattr(args, "feishu_webhook_url", None),
        user_profile=getattr(args, "user_profile", None),
        args=args,
        no_prompt=bool(getattr(args, "no_prompt", False)),
    )
    render_setup_summary(
        console=console,
        paths=paths,
        runtime_repo=runtime_repo,
        codex_path=codex_path,
        runtime_bundle_url=runtime_bundle_url,
        onboarding=onboarding,
    )
    return 0


def latest_app_run(paths: GTNPaths) -> Path | None:
    runs = sorted(path for path in paths.runs_dir.iterdir() if path.is_dir()) if paths.runs_dir.exists() else []
    return runs[-1] if runs else None


def print_run_summary(paths: GTNPaths, exit_code: int) -> None:
    latest = latest_app_run(paths)
    if latest is None:
        return
    result_path = latest / "result.json"
    payload = load_json(result_path, {}) if result_path.exists() else {}
    state = str(payload.get("state", "unknown")).strip() or "unknown"
    message = str(payload.get("message", "")).strip() or "(no message)"
    details = payload.get("details", {}) if isinstance(payload.get("details", {}), dict) else {}
    notion = details.get("notion", {}) if isinstance(details.get("notion", {}), dict) else {}
    feishu = details.get("feishu", {}) if isinstance(details.get("feishu", {}), dict) else {}
    discovery_count = details.get("discovery_findings")

    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    table.add_row("State", state)
    table.add_row("Message", message)
    if discovery_count is not None:
        table.add_row("Discovery", f"{discovery_count} finding(s)")
    if notion:
        notion_status = str(notion.get("state", "unknown"))
        notion_pages = notion.get("pages_created")
        if notion_pages is not None:
            notion_status = f"{notion_status} ({notion_pages} page(s))"
        table.add_row("Notion", notion_status)
    if feishu:
        feishu_status = str(feishu.get("state", "unknown"))
        if feishu.get("reason"):
            feishu_status = f"{feishu_status}: {feishu['reason']}"
        table.add_row("Feishu", feishu_status)
    table.add_row("Run dir", str(latest))
    if details.get("stdout_log"):
        table.add_row("Stdout", str(details["stdout_log"]))
    if details.get("stderr_log"):
        table.add_row("Stderr", str(details["stderr_log"]))

    if state == "success":
        border = "green"
        title = "Run Complete"
    elif state == "partial_success":
        border = "yellow"
        title = "Run Partial Success"
    else:
        border = "red"
        title = "Run Failed"
    Console().print(Panel(table, title=title, border_style=border, box=box.ROUNDED))


def cmd_run(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    require_initialized_runtime(state)
    rc = run_once(paths, state, scheduled=args.scheduled)
    print_run_summary(paths, rc)
    return rc


def cmd_config_get(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    runtime_repo = require_initialized_runtime(state)
    value = get_config_value(runtime_repo, state, args.key)
    print(value)
    return 0


def cmd_config_set(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    runtime_repo = require_initialized_runtime(state)

    if args.key == "tier":
        state.tier = normalize_tier(args.value)
        apply_tier_to_runtime(runtime_repo, state.tier)
        save_state(paths, state)
        print(f"tier={state.tier}")
        return 0
    if args.key == "notion-page-url":
        set_notion_page_url(runtime_repo, args.value)
        print(f"notion-page-url={args.value}")
        return 0
    if args.key == "feishu-webhook-url":
        set_feishu_webhook_url(runtime_repo, args.value)
        print(f"feishu-webhook-url={summarize_feishu_webhook(args.value)}")
        return 0
    raise SystemExit(f"Unsupported config key '{args.key}'")


def cmd_hard_rules_list(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    subscriptions = load_subscriptions(paths)
    if not subscriptions:
        print("No hard-rule subscriptions configured")
        return 0
    table = Table.grid(padding=(0, 2))
    table.add_column(style="bold cyan", justify="right")
    table.add_column()
    for item in subscriptions:
        table.add_row(
            str(item.get("id", "")),
            f"{item.get('source', '')} | topic={item.get('topic', '')} | top_n={item.get('top_n', '')}",
        )
    Console().print(Panel(table, title="Hard-Rule Subscriptions", border_style="cyan", box=box.ROUNDED))
    return 0


def cmd_hard_rules_add(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    subscriptions = upsert_subscriptions(paths, [build_subscriptions_from_sources([args.source], args.topic)[0]])
    print(f"Added hard-rule subscription for {args.source} ({len(subscriptions)} total)")
    return 0


def cmd_hard_rules_delete(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    removed = delete_subscription(paths, args.subscription_id)
    if removed is None:
        raise SystemExit(f"Hard-rule subscription not found: {args.subscription_id}")
    print(f"Deleted hard-rule subscription {removed['id']}")
    return 0

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


def install_runtime_editable(runtime_repo: Path) -> None:
    pip_command = [sys.executable, "-m", "pip", "install", "--editable", str(runtime_repo)]
    pip_result = subprocess.run(pip_command, text=True, capture_output=True)
    if pip_result.returncode == 0:
        return

    combined_output = f"{pip_result.stdout}\n{pip_result.stderr}"
    if "No module named pip" in combined_output:
        uv_bin = shutil.which("uv")
        if uv_bin:
            subprocess.run(
                [uv_bin, "pip", "install", "--python", sys.executable, "--editable", str(runtime_repo)],
                check=True,
            )
            return
        subprocess.run([sys.executable, "-m", "ensurepip", "--upgrade"], check=True)
        subprocess.run(pip_command, check=True)
        return

    raise subprocess.CalledProcessError(
        pip_result.returncode,
        pip_command,
        output=pip_result.stdout,
        stderr=pip_result.stderr,
    )


def cmd_update(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    runtime_repo = require_initialized_runtime(state)
    current_lock_state = lock_status(paths.lock_file)
    if current_lock_state == "active":
        lock = load_lock(paths.lock_file) or {}
        run_id = lock.get("run_id", "(unknown)")
        raise SystemExit(f"Cannot update while a GTN run is active (run_id={run_id}).")

    packaged_runtime_mode = not state.runtime_bundle_url and not runtime_uses_git_checkout(runtime_repo)
    if packaged_runtime_mode:
        python_hint = paths.root / ".venv" / "bin" / "python"
        print("GTN now expects package-manager-native upgrades.")
        print(f"Use: uv pip install --python {python_hint} --upgrade goodtoknow-gtn")
        return 0

    if state.runtime_bundle_url:
        snapshots = snapshot_runtime_state_files(runtime_repo)
        preserved_count = len(snapshots)
    else:
        dirty_paths = dirty_runtime_paths(runtime_repo)
        snapshots = snapshot_preserved_runtime_state(runtime_repo, dirty_paths)
        reset_runtime_paths_to_head(runtime_repo, sorted(snapshots))
        preserved_count = len(snapshots)

    try:
        if state.runtime_bundle_url:
            bundle_url = resolve_runtime_bundle_url(state.runtime_bundle_url)
            hydrate_runtime_bundle(runtime_repo, bundle_url)
            restore_runtime_state_snapshots(runtime_repo, snapshots)
        elif runtime_uses_git_checkout(runtime_repo):
            subprocess.run(["git", "-C", str(runtime_repo), "pull", "--ff-only"], check=True)
        else:
            hydrate_packaged_runtime(runtime_repo)
            restore_runtime_state_snapshots(runtime_repo, snapshots)
        install_runtime_editable(runtime_repo)
    finally:
        if not state.runtime_bundle_url and not packaged_runtime_mode and runtime_uses_git_checkout(runtime_repo):
            restore_runtime_state_snapshots(runtime_repo, snapshots)

    if preserved_count:
        print(f"Preserved local GTN state for {preserved_count} file(s).")
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
    print("If the goodtoknow-gtn package is still installed, remove it with: uv pip uninstall goodtoknow-gtn")
    return 0

def cmd_status(args: argparse.Namespace) -> int:
    paths = resolve_paths(root=Path(args.root).expanduser() if args.root else None)
    state = load_state(paths)
    if not state.initialized_at:
        state = ensure_state_initialized_at(state)
        save_state(paths, state)
    snapshot = build_status_snapshot(paths, state)
    Console().print(build_status_dashboard(snapshot))
    print(f"stale_lock_seconds={STALE_LOCK_SECONDS}")
    return 0

def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="gtn", description="GoodToKnow local product shell")
    parser.add_argument("--root", help="Override GTN home directory (default: ~/.gtn)")
    subparsers = parser.add_subparsers(dest="command", required=True)

    def add_setup_arguments(command_parser: argparse.ArgumentParser) -> None:
        command_parser.add_argument("--runtime-repo")
        command_parser.add_argument("--runtime-bundle-url")
        command_parser.add_argument("--codex-path")
        command_parser.add_argument("--tier", choices=sorted(TIER_PRESETS), default=state_tier(StateData()), help="Unified GTN monitoring/density tier")
        command_parser.add_argument("--notion-page-url", help="Optional Notion page URL for first-time output setup")
        command_parser.add_argument("--feishu-webhook-url", help="Optional Feishu webhook URL for first-time output setup")
        command_parser.add_argument("--user-profile", help="Optional free-form user profile text to seed GTN memory")
        command_parser.add_argument(
            "--hard-rule-source",
            dest="hard_rule_sources",
            action="append",
            help="Optional hard-rule source id to configure during setup (repeatable)",
        )
        command_parser.add_argument(
            "--hard-rule-topic",
            help="Optional overall hard-rule topic for setup-created subscriptions",
        )
        command_parser.add_argument(
            "--hard-rule-topic-override",
            dest="hard_rule_topic_overrides",
            action="append",
            help="Optional source=topic override for setup-created hard-rule subscriptions (repeatable)",
        )
        command_parser.add_argument("--no-prompt", action="store_true", help="Skip interactive onboarding prompts")
        command_parser.set_defaults(func=cmd_init)

    init_parser = subparsers.add_parser("init", help=argparse.SUPPRESS)
    add_setup_arguments(init_parser)

    setup_parser = subparsers.add_parser("setup", help="Initialize GTN state and run first-time onboarding")
    add_setup_arguments(setup_parser)

    config_parser = subparsers.add_parser("config", help="Read or update high-level GTN configuration")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)

    config_get_parser = config_subparsers.add_parser("get", help="Read a GTN config value")
    config_get_parser.add_argument("key", choices=CONFIG_KEYS)
    config_get_parser.set_defaults(func=cmd_config_get)

    config_set_parser = config_subparsers.add_parser("set", help="Update a GTN config value")
    config_set_parser.add_argument("key", choices=CONFIG_KEYS)
    config_set_parser.add_argument("value")
    config_set_parser.set_defaults(func=cmd_config_set)

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

    hard_rules_parser = subparsers.add_parser("hard-rules", help="Manage hard-rule recommendation subscriptions")
    hard_rules_subparsers = hard_rules_parser.add_subparsers(dest="hard_rules_command", required=True)

    hard_rules_list_parser = hard_rules_subparsers.add_parser("list", help="List hard-rule subscriptions")
    hard_rules_list_parser.set_defaults(func=cmd_hard_rules_list)

    hard_rules_add_parser = hard_rules_subparsers.add_parser("add", help="Add a hard-rule subscription")
    hard_rules_add_parser.add_argument("--source", required=True)
    hard_rules_add_parser.add_argument("--topic", required=True)
    hard_rules_add_parser.set_defaults(func=cmd_hard_rules_add)

    hard_rules_delete_parser = hard_rules_subparsers.add_parser("delete", help="Delete a hard-rule subscription")
    hard_rules_delete_parser.add_argument("subscription_id")
    hard_rules_delete_parser.set_defaults(func=cmd_hard_rules_delete)

    return parser

def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
