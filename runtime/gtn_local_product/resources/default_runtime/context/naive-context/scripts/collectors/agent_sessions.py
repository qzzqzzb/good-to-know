from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, List, Optional


COMMON_PATH_RE = re.compile(
    r"(?P<path>(?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+\.(?:md|py|json|ya?ml|toml|ts|tsx|js|jsx|sh|txt)|AGENTS\.md|README\.md|\.gitignore)"
)
REDIRECT_RE = re.compile(r"(?:>|>>)\s*(?P<path>[^\s\"']+)")
FILE_OP_RE = re.compile(
    r"\b(?:mv|cp|rm|touch|mkdir)\b(?:\s+-[^\s]+\b)*\s+(?P<path>[^\s\"']+)"
)


@dataclass
class Episode:
    provider: str
    session_id: str
    cwd: str
    session_path: Path
    index: int
    anchor_message: str
    start_time: datetime
    last_time: datetime
    targets: list[str] = field(default_factory=list)
    tool_kinds: list[str] = field(default_factory=list)


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug or "item"


def _short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _parse_iso_timestamp(value: str | None) -> Optional[datetime]:
    if not value:
        return None
    try:
        normalized = value.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).astimezone()
    except ValueError:
        return None


def _clean_text(value: str) -> str:
    text = value.strip()
    text = re.sub(r"<local-command-caveat>.*?</local-command-caveat>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _trim_text(value: str, limit: int = 160) -> str:
    text = _clean_text(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip() + "…"


def _looks_like_cli_noise(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    prefixes = (
        "<local-command-caveat>",
        "<command-name>",
        "<local-command-stdout>",
        "<command-message>",
    )
    return text.startswith(prefixes)


def _is_low_signal_prompt(value: str) -> bool:
    normalized = _clean_text(value).lower()
    return normalized in {"hi", "hello", "hey", "test", "plugins"}


def _is_high_signal_prompt(value: str) -> bool:
    cleaned = _clean_text(value)
    return bool(cleaned) and not _looks_like_cli_noise(value) and not _is_low_signal_prompt(cleaned)


def _within_lookback(when: datetime | None, lookback_hours: int) -> bool:
    if when is None:
        return False
    cutoff = datetime.now(timezone.utc).astimezone() - timedelta(hours=lookback_hours)
    return when >= cutoff


def _iter_recent_files(roots: Iterable[Path], pattern: str) -> list[Path]:
    files: list[Path] = []
    for root in roots:
        if not root.exists():
            continue
        files.extend(path for path in root.rglob(pattern) if path.is_file())
    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def _normalize_target(path_text: str, cwd: str) -> Optional[str]:
    path_text = path_text.strip().strip("\"'`;:,")
    if not path_text or path_text.startswith("-"):
        return None
    if path_text in {"/dev/null", "EOF", "PATCH"}:
        return None
    if "\n" in path_text or "\\" in path_text:
        return None
    if not any(token in path_text for token in ("/", ".")) and path_text not in {"AGENTS.md", "README.md", ".gitignore"}:
        return None
    path = Path(path_text)
    if path.is_absolute():
        try:
            return str(path.relative_to(cwd))
        except ValueError:
            return str(path)
    return str(path)


def _extract_targets_from_command(command: str, cwd: str) -> list[str]:
    targets: list[str] = []

    for match in REDIRECT_RE.finditer(command):
        target = _normalize_target(match.group("path"), cwd)
        if target and target not in targets:
            targets.append(target)

    for match in FILE_OP_RE.finditer(command):
        target = _normalize_target(match.group("path"), cwd)
        if target and target not in targets:
            targets.append(target)

    for match in COMMON_PATH_RE.finditer(command):
        target = _normalize_target(match.group("path"), cwd)
        if target and target not in targets:
            targets.append(target)

    return targets[:6]


def _extract_targets_from_patch(arguments: str, cwd: str) -> list[str]:
    targets: list[str] = []
    for line in arguments.splitlines():
        stripped = line.strip()
        prefixes = ("*** Add File: ", "*** Update File: ", "*** Delete File: ", "*** Move to: ")
        for prefix in prefixes:
            if stripped.startswith(prefix):
                target = _normalize_target(stripped[len(prefix) :], cwd)
                if target and target not in targets:
                    targets.append(target)
    return targets[:6]


def _looks_like_write_command(command: str) -> bool:
    checks = (
        "apply_patch <<",
        "cat >",
        "cat >>",
        "printf ",
        "touch ",
        "mkdir ",
        " mv ",
        " rm ",
        "sed -i",
        "perl -pi",
    )
    return any(token in command for token in checks) or bool(REDIRECT_RE.search(command))


def _build_episode_entry_id(provider: str, session_id: str, cwd: str, index: int) -> str:
    path_slug = _slugify(Path(cwd).name or cwd)[:24].strip("-") or "session"
    seed = f"{provider}:{session_id}:{index}:{cwd}"
    return f"agent-episode-{_slugify(provider)}-{path_slug}-{_short_hash(seed)}"


def _build_episode_dedup_key(provider: str, session_id: str, index: int) -> str:
    return f"agent_episode:{provider}:{session_id}:{index}"


def _episode_to_observation(episode: Episode) -> dict:
    path_name = Path(episode.cwd).name or episode.cwd
    target_text = ""
    if episode.targets:
        preview = ", ".join(episode.targets[:3])
        target_text = f" touching {preview}"

    summary = f'{episode.provider.capitalize()} work in {path_name}: "{episode.anchor_message}"{target_text}'
    return {
        "entry_id": _build_episode_entry_id(episode.provider, episode.session_id, episode.cwd, episode.index),
        "dedup_key": _build_episode_dedup_key(episode.provider, episode.session_id, episode.index),
        "time": episode.start_time.isoformat(timespec="seconds"),
        "source": f"agent_session:{episode.provider}",
        "tags": ["agent_session", episode.provider, "llm_session", "edit_episode"],
        "summary": _trim_text(summary, limit=220),
        "raw": (
            f"{episode.session_path} | cwd={episode.cwd} | "
            f"targets={','.join(episode.targets) if episode.targets else '(unknown)'}"
        ),
    }


def _build_session_summary_observation(
    provider: str,
    session_id: str,
    cwd: str,
    session_path: Path,
    started_at: datetime,
    first_user_message: str,
) -> dict:
    summary = f'{provider.capitalize()} session in {Path(cwd).name or cwd}: "{first_user_message}"'
    return {
        "entry_id": _build_episode_entry_id(provider, session_id, cwd, 0),
        "dedup_key": _build_episode_dedup_key(provider, session_id, 0),
        "time": started_at.isoformat(timespec="seconds"),
        "source": f"agent_session:{provider}",
        "tags": ["agent_session", provider, "llm_session", "session_summary"],
        "summary": summary,
        "raw": f"{session_path} | cwd={cwd}",
    }


def _collect_codex_session_observations(
    path: Path,
    lookback_hours: int,
    include_subagents: bool,
    include_non_edit_sessions: bool,
    max_observations_per_session: int,
) -> list[dict]:
    session_id: Optional[str] = None
    cwd: Optional[str] = None
    started_at: Optional[datetime] = None
    is_subagent = False
    latest_user_message: Optional[str] = None
    first_user_message: Optional[str] = None
    current_episode: Optional[Episode] = None
    episodes: list[Episode] = []

    def finalize_episode() -> None:
        nonlocal current_episode
        if current_episode is None:
            return
        episodes.append(current_episode)
        current_episode = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            item_type = item.get("type")
            payload = item.get("payload", {})
            event_time = _parse_iso_timestamp(item.get("timestamp"))

            if item_type == "session_meta":
                session_id = payload.get("id", session_id)
                cwd = payload.get("cwd", cwd)
                started_at = _parse_iso_timestamp(payload.get("timestamp")) or started_at
                source = payload.get("source")
                if isinstance(source, dict) and source.get("subagent"):
                    is_subagent = True
                continue

            if item_type == "event_msg" and isinstance(payload, dict) and payload.get("type") == "user_message":
                message = str(payload.get("message", ""))
                if _is_high_signal_prompt(message):
                    latest_user_message = _trim_text(message)
                    first_user_message = first_user_message or latest_user_message
                    if current_episode is not None:
                        finalize_episode()
                continue

            if item_type != "response_item" or payload.get("type") != "function_call":
                continue

            name = payload.get("name")
            arguments = payload.get("arguments", "")
            if not session_id or not cwd:
                continue

            write_targets: list[str] = []
            tool_kind: Optional[str] = None

            if name == "apply_patch":
                write_targets = _extract_targets_from_patch(arguments, cwd)
                tool_kind = "apply_patch"
            elif name == "exec_command":
                if not _looks_like_write_command(arguments):
                    continue
                write_targets = _extract_targets_from_command(arguments, cwd)
                tool_kind = "exec_command"
            else:
                continue

            if current_episode is None:
                anchor = latest_user_message or first_user_message or "Implemented a coding task"
                episode_index = len(episodes) + 1
                current_episode = Episode(
                    provider="codex",
                    session_id=session_id,
                    cwd=cwd,
                    session_path=path,
                    index=episode_index,
                    anchor_message=anchor,
                    start_time=event_time or started_at or datetime.now(timezone.utc).astimezone(),
                    last_time=event_time or started_at or datetime.now(timezone.utc).astimezone(),
                )

            current_episode.last_time = event_time or current_episode.last_time
            if tool_kind and tool_kind not in current_episode.tool_kinds:
                current_episode.tool_kinds.append(tool_kind)
            for target in write_targets:
                if target not in current_episode.targets:
                    current_episode.targets.append(target)

    finalize_episode()

    if is_subagent and not include_subagents:
        return []
    if not _within_lookback(started_at, lookback_hours):
        return []
    if not session_id or not cwd:
        return []

    if episodes:
        return [_episode_to_observation(episode) for episode in episodes[:max_observations_per_session]]

    if include_non_edit_sessions and first_user_message:
        return [_build_session_summary_observation("codex", session_id, cwd, path, started_at, first_user_message)]

    return []


def _collect_claude_session_observations(
    path: Path,
    lookback_hours: int,
    include_non_edit_sessions: bool,
    max_observations_per_session: int,
) -> list[dict]:
    session_id: Optional[str] = None
    cwd: Optional[str] = None
    started_at: Optional[datetime] = None
    latest_user_message: Optional[str] = None
    first_user_message: Optional[str] = None
    current_episode: Optional[Episode] = None
    episodes: list[Episode] = []

    def finalize_episode() -> None:
        nonlocal current_episode
        if current_episode is None:
            return
        episodes.append(current_episode)
        current_episode = None

    with path.open("r", encoding="utf-8", errors="replace") as handle:
        for line in handle:
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue

            session_id = item.get("sessionId", session_id)
            cwd = item.get("cwd", cwd)
            event_time = _parse_iso_timestamp(item.get("timestamp"))
            started_at = event_time or started_at

            if item.get("type") == "user":
                message = item.get("message", {})
                content = message.get("content")
                if isinstance(content, str) and _is_high_signal_prompt(content):
                    latest_user_message = _trim_text(content)
                    first_user_message = first_user_message or latest_user_message
                    if current_episode is not None:
                        finalize_episode()
                continue

            if item.get("type") != "assistant":
                continue

            message = item.get("message", {})
            contents = message.get("content")
            if not isinstance(contents, list):
                continue

            for block in contents:
                if block.get("type") != "tool_use":
                    continue

                name = block.get("name")
                write_targets: list[str] = []
                tool_kind: Optional[str] = None

                if name in {"Write", "Edit", "MultiEdit"}:
                    input_data = block.get("input", {})
                    file_path = input_data.get("file_path")
                    if isinstance(file_path, str):
                        target = _normalize_target(file_path, cwd or "")
                        if target:
                            write_targets = [target]
                    tool_kind = name.lower()
                elif name == "Bash":
                    command = str(block.get("input", {}).get("command", ""))
                    if not _looks_like_write_command(command):
                        continue
                    write_targets = _extract_targets_from_command(command, cwd or "")
                    tool_kind = "bash"
                else:
                    continue

                if not session_id or not cwd:
                    continue

                if current_episode is None:
                    anchor = latest_user_message or first_user_message or "Implemented a coding task"
                    episode_index = len(episodes) + 1
                    current_episode = Episode(
                        provider="claude",
                        session_id=session_id,
                        cwd=cwd,
                        session_path=path,
                        index=episode_index,
                        anchor_message=anchor,
                        start_time=event_time or datetime.now(timezone.utc).astimezone(),
                        last_time=event_time or datetime.now(timezone.utc).astimezone(),
                    )

                current_episode.last_time = event_time or current_episode.last_time
                if tool_kind and tool_kind not in current_episode.tool_kinds:
                    current_episode.tool_kinds.append(tool_kind)
                for target in write_targets:
                    if target not in current_episode.targets:
                        current_episode.targets.append(target)

    finalize_episode()

    if not _within_lookback(started_at, lookback_hours):
        return []
    if not session_id or not cwd:
        return []

    if episodes:
        return [_episode_to_observation(episode) for episode in episodes[:max_observations_per_session]]

    if include_non_edit_sessions and first_user_message:
        return [_build_session_summary_observation("claude", session_id, cwd, path, started_at, first_user_message)]

    return []


def collect_agent_session_observations(config: dict) -> List[dict]:
    lookback_hours = int(config.get("lookback_hours", 72))
    max_entries = int(config.get("max_entries", 12))
    max_observations_per_session = int(config.get("max_observations_per_session", 3))
    providers = set(config.get("providers", ["codex", "claude"]))
    include_subagents = bool(config.get("include_codex_subagents", False))
    include_non_edit_sessions = bool(config.get("include_non_edit_sessions", True))

    observations: List[dict] = []

    if "codex" in providers:
        codex_roots = [Path.home() / ".codex" / "sessions"]
        for path in _iter_recent_files(codex_roots, "*.jsonl"):
            observations.extend(
                _collect_codex_session_observations(
                    path,
                    lookback_hours=lookback_hours,
                    include_subagents=include_subagents,
                    include_non_edit_sessions=include_non_edit_sessions,
                    max_observations_per_session=max_observations_per_session,
                )
            )

    if "claude" in providers:
        claude_roots = [
            Path.home() / ".claude" / "projects",
            Path.home() / ".claude_bak" / "projects",
        ]
        for path in _iter_recent_files(claude_roots, "*.jsonl"):
            observations.extend(
                _collect_claude_session_observations(
                    path,
                    lookback_hours=lookback_hours,
                    include_non_edit_sessions=include_non_edit_sessions,
                    max_observations_per_session=max_observations_per_session,
                )
            )

    observations.sort(key=lambda item: item.get("time", ""), reverse=True)
    return observations[:max_entries]
