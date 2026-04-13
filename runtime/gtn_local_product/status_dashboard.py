from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from importlib import metadata
from io import StringIO
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from rich import box
from rich.align import Align
from rich.console import Group
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from .cadence import DEFAULT_ANCHOR_HOUR, next_run_epoch, parse_cadence
from .launchd import launch_agent_loaded
from .locks import load_lock, lock_status
from .models import StateData
from .paths import GTNPaths
from .status_data import (
    compute_feedback_distribution,
    latest_run_snapshot,
    load_history,
    runtime_storage_bytes,
    top_profile_keywords,
)
from .storage import load_json

PACKAGE_NAME = 'goodtoknow-gtn'
PYPI_JSON_URL = f'https://pypi.org/pypi/{PACKAGE_NAME}/json'
_VERSION_TOKEN_RE = re.compile(r'\d+|[A-Za-z]+')


def format_datetime(raw_value: str | None) -> str:
    value = (raw_value or '').strip()
    if not value:
        return '(unknown)'
    try:
        parsed = datetime.fromisoformat(value.replace('Z', '+00:00'))
    except ValueError:
        return value
    return parsed.astimezone().isoformat(timespec='seconds')


def format_relative_seconds(total_seconds: float | int | None) -> str:
    if total_seconds is None:
        return '(unknown)'
    seconds = max(int(total_seconds), 0)
    days, remainder = divmod(seconds, 86400)
    hours, remainder = divmod(remainder, 3600)
    minutes, secs = divmod(remainder, 60)
    parts: list[str] = []
    if days:
        parts.append(f'{days}d')
    if hours:
        parts.append(f'{hours}h')
    if minutes:
        parts.append(f'{minutes}m')
    if secs and not parts:
        parts.append(f'{secs}s')
    return ' '.join(parts) or '0s'


def format_bytes(num_bytes: int) -> str:
    value = float(max(num_bytes, 0))
    for unit in ('B', 'KB', 'MB', 'GB', 'TB'):
        if value < 1024 or unit == 'TB':
            if unit == 'B':
                return f'{int(value)} {unit}'
            return f'{value:.1f} {unit}'
        value /= 1024.0
    return '0 B'


def compact_text(value: str, limit: int = 52) -> str:
    clean = " ".join(value.split())
    if len(clean) <= limit:
        return clean
    return f"{clean[: limit - 1].rstrip()}..."


def status_badge(raw_state: str) -> str:
    state = raw_state.strip().lower()
    if state == 'success':
        return '[green]✅ SUCCESS[/]'
    if state == 'partial_success':
        return '[yellow]⚠ PARTIAL[/]'
    if state == 'failed':
        return '[red]✖ FAILED[/]'
    if state in {'running', 'in_progress'}:
        return '[cyan]● RUNNING[/]'
    return f'[white]{raw_state.upper() or "UNKNOWN"}[/]'


def feedback_badge(label: str, count: int) -> str:
    if label == 'Good to know':
        return f'[green]🟢 {count}[/]'
    if label == 'Bad recommendation':
        return f'[red]🔴 {count}[/]'
    return f'[yellow]🟡 {count}[/]'


def enabled_badge(enabled: bool) -> str:
    return '[green]ON[/]' if enabled else '[red]OFF[/]'


def lock_badge(lock_state_value: str) -> str:
    if lock_state_value == 'active':
        return '[yellow]🔒 active[/]'
    if lock_state_value == 'stale':
        return '[red]⚠ stale[/]'
    return '[green]○ none[/]'


def next_run_display(state: StateData, latest_updated_at: str | None) -> tuple[str, str]:
    if not state.enabled or not state.cadence:
        return '(disabled)', '(disabled)'
    _, seconds = parse_cadence(state.cadence)
    last_epoch = None
    if latest_updated_at:
        last_epoch = datetime.fromisoformat(latest_updated_at.replace('Z', '+00:00')).timestamp()
    estimate = next_run_epoch(last_epoch, seconds)
    if estimate is None:
        return '(unknown)', '(unknown)'
    scheduled = datetime.fromtimestamp(estimate, tz=timezone.utc).astimezone()
    remaining = scheduled.timestamp() - datetime.now(timezone.utc).astimezone().timestamp()
    return scheduled.isoformat(timespec='seconds'), format_relative_seconds(max(remaining, 0))


def configured_runtime_repo(state: StateData) -> Path | None:
    if not state.runtime_repo_path:
        return None
    return Path(state.runtime_repo_path).expanduser().resolve()


def display_destination(raw_value: str, reveal: int = 14, sensitive: bool = False) -> str:
    value = raw_value.strip()
    if not value:
        return '(unset)'
    if sensitive:
        if '://' in value:
            scheme, remainder = value.split('://', 1)
            host = remainder.split('/', 1)[0]
            return f'{scheme}://{host}/... (configured)'
        return '(configured)'
    if len(value) <= reveal * 2:
        return value
    return f'{value[:reveal]}...{value[-reveal:]}'


def anchor_display() -> str:
    return f"{DEFAULT_ANCHOR_HOUR:02d}:00"


def repo_declared_version() -> str | None:
    pyproject_path = Path(__file__).resolve().parents[2] / 'pyproject.toml'
    if not pyproject_path.exists():
        return None
    try:
        import tomllib

        payload = tomllib.loads(pyproject_path.read_text(encoding='utf-8'))
        version = str(((payload.get('project') or {}).get('version') or '')).strip()
        return version or None
    except ModuleNotFoundError:
        raw = pyproject_path.read_text(encoding='utf-8')
    except (OSError, ValueError):
        return None
    match = re.search(r'(?m)^version\s*=\s*"([^"]+)"\s*$', raw)
    if not match:
        return None
    version = match.group(1).strip()
    return version or None


def installed_version_info() -> tuple[str, str]:
    try:
        return metadata.version(PACKAGE_NAME), 'installed'
    except metadata.PackageNotFoundError:
        declared = repo_declared_version()
        if declared:
            return declared, 'repo'
        return '(unknown)', 'unknown'


def fetch_latest_pypi_version(timeout_seconds: float = 2.0) -> tuple[str | None, str | None]:
    request = Request(
        PYPI_JSON_URL,
        headers={
            'Accept': 'application/json',
            'User-Agent': f'{PACKAGE_NAME}-status-check',
        },
    )
    try:
        with urlopen(request, timeout=timeout_seconds) as response:
            payload = json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError, ValueError) as exc:
        return None, str(exc)
    version = str((payload.get('info') or {}).get('version') or '').strip()
    return (version or None), None


def compare_versions(left: str, right: str) -> int:
    parsed = compare_versions_with_packaging(left, right)
    if parsed is not None:
        return parsed
    return basic_compare_versions(left, right)


def compare_versions_with_packaging(left: str, right: str) -> int | None:
    try:
        from packaging.version import InvalidVersion, Version
    except ImportError:
        return None

    try:
        left_version = Version(left)
        right_version = Version(right)
    except InvalidVersion:
        return None

    if left_version < right_version:
        return -1
    if left_version > right_version:
        return 1
    return 0


def basic_compare_versions(left: str, right: str) -> int:
    left_tokens = version_tokens(left)
    right_tokens = version_tokens(right)
    sentinel = (1, 0)
    for index in range(max(len(left_tokens), len(right_tokens))):
        left_token = left_tokens[index] if index < len(left_tokens) else sentinel
        right_token = right_tokens[index] if index < len(right_tokens) else sentinel
        if left_token == right_token:
            continue
        return -1 if left_token < right_token else 1
    return 0


def version_tokens(value: str) -> list[tuple[int, int | str]]:
    tokens: list[tuple[int, int | str]] = []
    for token in _VERSION_TOKEN_RE.findall(value):
        if token.isdigit():
            tokens.append((1, int(token)))
        else:
            tokens.append((0, token.lower()))
    return tokens


def latest_version_display(
    current_version: str,
    current_source: str,
    latest_version: str | None,
    latest_error: str | None,
) -> str:
    if latest_version:
        if current_source == 'installed':
            comparison = compare_versions(current_version, latest_version)
            if comparison == 0:
                return f'{latest_version} (up to date)'
            if comparison < 0:
                return f'{latest_version} (update available)'
            return f'{latest_version} (local build ahead)'
        if current_version == latest_version:
            return f'{latest_version} (matches repo)'
        return latest_version
    if latest_error:
        return '(check failed)'
    return '(unknown)'


def build_status_snapshot(paths: GTNPaths, state: StateData) -> dict:
    latest_summary, latest_run_dir = latest_run_snapshot(paths)
    latest_updated_at = str((latest_summary or {}).get('updated_at', '')).strip() or None
    next_run_at, next_run_in = next_run_display(state, latest_updated_at)
    lock = load_lock(paths.lock_file)
    runtime_repo = configured_runtime_repo(state)
    history = load_history(paths.status_history_file)
    notion_settings = {}
    feishu_settings = {}
    feedback_counts = {'No feedback': 0, 'Good to know': 0, 'Bad recommendation': 0}
    keywords: list[tuple[str, int]] = []
    runtime_size = 0
    if runtime_repo and runtime_repo.exists():
        notion_settings = load_json(runtime_repo / 'output' / 'notion-briefing' / 'settings.json', {})
        feishu_settings = load_json(runtime_repo / 'output' / 'feishu-briefing' / 'settings.json', {})
        feedback_counts = compute_feedback_distribution(runtime_repo)
        keywords = top_profile_keywords(runtime_repo)
        runtime_size = runtime_storage_bytes(runtime_repo)

    uptime_seconds = None
    if state.initialized_at:
        try:
            uptime_seconds = (
                datetime.now(timezone.utc).astimezone()
                - datetime.fromisoformat(state.initialized_at.replace('Z', '+00:00'))
            ).total_seconds()
        except ValueError:
            uptime_seconds = None

    current_version, current_version_source = installed_version_info()
    latest_version, latest_version_error = fetch_latest_pypi_version()

    return {
        'enabled': state.enabled and launch_agent_loaded(),
        'cadence': state.cadence or '(unset)',
        'anchor': anchor_display(),
        'runtime_repo': str(runtime_repo) if runtime_repo else '(unset)',
        'lock_state': lock_status(paths.lock_file),
        'lock_run_id': lock.get('run_id', '') if lock else '',
        'next_run_at': next_run_at,
        'next_run_in': next_run_in,
        'uptime': format_relative_seconds(uptime_seconds),
        'runtime_size': format_bytes(runtime_size),
        'latest_run_dir': str(latest_run_dir) if latest_run_dir else 'No run yet',
        'latest': latest_summary or {},
        'history': history,
        'feedback_counts': feedback_counts,
        'notion_target': display_destination(
            str(notion_settings.get('database_url') or notion_settings.get('parent_page_url') or '')
        ),
        'feishu_webhook': display_destination(str(feishu_settings.get('webhook_url', '')), sensitive=True),
        'keywords': keywords,
        'current_version': current_version,
        'current_version_source': current_version_source,
        'latest_version': latest_version_display(
            current_version,
            current_version_source,
            latest_version,
            latest_version_error,
        ),
    }


def build_status_dashboard(snapshot: dict):
    latest = snapshot.get('latest', {})
    metrics = latest.get('metrics', {})
    history = snapshot.get('history', {}).get('totals', {})
    feedback_counts = snapshot.get('feedback_counts', {})
    header_meta = Text()
    header_meta.append(f" cadence {snapshot.get('cadence', '(unset)')} ", style='black on bright_cyan')
    header_meta.append(f" uptime {snapshot.get('uptime', '(unknown)')} ", style='black on bright_white')

    header = Text()
    header.append("👀 GoodToKnow Dashboard", style="bold bright_cyan")
    header.append("  forward-only status for your local GTN runtime", style="dim")
    header_panel = Panel(
        Align.center(Text.assemble(header, "\n", header_meta)),
        border_style="cyan",
        box=box.ROUNDED,
        padding=(0, 2),
    )

    last_run = Table.grid(padding=(0, 2))
    last_run.add_column(style='bold cyan', justify='right')
    last_run.add_column()
    last_run.add_row('State', status_badge(str(latest.get('state', '(unknown)'))))
    last_run.add_row('Updated', format_datetime(latest.get('updated_at')))
    last_run.add_row('Records scanned', str(metrics.get('records_scanned', 0)))
    last_run.add_row('Webpages searched', str(metrics.get('webpages_searched', 0)))
    last_run.add_row('Recommendations', str(metrics.get('recommendations_produced', 0)))
    last_run.add_row('Run dir', compact_text(str(snapshot.get('latest_run_dir', '(none)')), limit=34))

    history_table = Table.grid(padding=(0, 2))
    history_table.add_column(style='bold cyan', justify='right')
    history_table.add_column()
    history_table.add_row('Push count', str(history.get('push_count', 0)))
    history_table.add_row('Pushed recommendations', str(history.get('pushed_recommendations_total', 0)))
    history_table.add_row('No feedback', feedback_badge('No feedback', feedback_counts.get('No feedback', 0)))
    history_table.add_row('Good to know', feedback_badge('Good to know', feedback_counts.get('Good to know', 0)))
    history_table.add_row('Bad recommendation', feedback_badge('Bad recommendation', feedback_counts.get('Bad recommendation', 0)))

    system = Table.grid(padding=(0, 2))
    system.add_column(style='bold cyan', justify='right')
    system.add_column()
    system.add_row('Enabled', enabled_badge(bool(snapshot.get('enabled', False))))
    current_version = str(snapshot.get('current_version', '(unknown)'))
    if snapshot.get('current_version_source') == 'repo' and current_version != '(unknown)':
        current_version = f'{current_version} (repo)'
    system.add_row('Version', current_version)
    system.add_row('Latest', str(snapshot.get('latest_version', '(unknown)')))
    system.add_row('Cadence', str(snapshot.get('cadence', '(unset)')))
    system.add_row('Anchor', str(snapshot.get('anchor', '(unknown)')))
    system.add_row(
        'Next run',
        compact_text(
            f"{snapshot.get('next_run_at', '(unknown)')} ({snapshot.get('next_run_in', '(unknown)')})",
            limit=34,
        ),
    )
    system.add_row('Lock', lock_badge(str(snapshot.get('lock_state', '(unknown)'))))
    if snapshot.get('lock_run_id'):
        system.add_row('Lock run id', compact_text(str(snapshot.get('lock_run_id')), limit=34))
    system.add_row('Runtime size', str(snapshot.get('runtime_size', '(unknown)')))
    system.add_row('Uptime', str(snapshot.get('uptime', '(unknown)')))
    system.add_row('Notion', compact_text(str(snapshot.get('notion_target', '(unset)')), limit=36))
    system.add_row('Feishu', compact_text(str(snapshot.get('feishu_webhook', '(unset)')), limit=44))

    profile = Table.grid(padding=(0, 2))
    profile.add_column(style='bold cyan', justify='right')
    profile.add_column()
    keywords = snapshot.get('keywords', [])
    if keywords:
        for keyword, count in keywords:
            profile.add_row(keyword, str(count))
    else:
        profile.add_row('Keywords', '(insufficient data)')

    top_grid = Table.grid(expand=True)
    top_grid.add_column(ratio=1)
    top_grid.add_column(ratio=1)
    top_grid.add_row(
        Panel(last_run, title='Last Run Status', border_style='green', box=box.DOUBLE, padding=(0, 1)),
        Panel(system, title='System Status', border_style='yellow', box=box.DOUBLE, padding=(0, 1)),
    )

    bottom_grid = Table.grid(expand=True)
    bottom_grid.add_column(ratio=1)
    bottom_grid.add_column(ratio=1)
    bottom_grid.add_row(
        Panel(history_table, title='All History', border_style='blue', box=box.DOUBLE, padding=(0, 1)),
        Panel(profile, title='User Profile', border_style='magenta', box=box.DOUBLE, padding=(0, 1)),
    )

    return Group(header_panel, top_grid, bottom_grid)


def render_status_dashboard(snapshot: dict) -> str:
    buffer = StringIO()
    console = Console(file=buffer, force_terminal=False, width=120)
    console.print(build_status_dashboard(snapshot))
    return buffer.getvalue()
