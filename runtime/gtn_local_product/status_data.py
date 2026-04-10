from __future__ import annotations

import json
import re
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import StateData
from .paths import GTNPaths
from .storage import load_json, save_json

STATUS_SCHEMA_VERSION = 1
RUN_SUMMARY_FILENAME = "status-summary.json"
TOKEN_RE = re.compile(r"[A-Za-z][A-Za-z0-9_-]{2,}|[\u4e00-\u9fff]{2,}")
STOPWORDS = {
    "and",
    "about",
    "after",
    "briefing",
    "context",
    "created",
    "entry",
    "feedback",
    "findings",
    "generated",
    "goodtoknow",
    "gtn",
    "memory",
    "naive",
    "notion",
    "observation",
    "observations",
    "outbox",
    "page",
    "pages",
    "profile",
    "raw",
    "recorded",
    "source",
    "status",
    "summary",
    "tags",
    "time",
    "type",
    "user",
    "users",
    "web",
    "web_search",
}


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def read_json_if_exists(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    return load_json(path, default)


def run_summary_path(run_dir: Path) -> Path:
    return run_dir / RUN_SUMMARY_FILENAME


def history_payload_default() -> dict[str, Any]:
    return {
        "version": STATUS_SCHEMA_VERSION,
        "schema_started_at": now_iso(),
        "updated_at": now_iso(),
        "aggregated_run_ids": [],
        "totals": {
            "push_count": 0,
            "pushed_recommendations_total": 0,
        },
    }


def load_history(history_path: Path) -> dict[str, Any]:
    payload = read_json_if_exists(history_path, history_payload_default())
    if payload.get("version") != STATUS_SCHEMA_VERSION:
        payload = history_payload_default()
    payload.setdefault("aggregated_run_ids", [])
    payload.setdefault("totals", {})
    payload["totals"].setdefault("push_count", 0)
    payload["totals"].setdefault("pushed_recommendations_total", 0)
    payload.setdefault("schema_started_at", now_iso())
    payload.setdefault("updated_at", now_iso())
    return payload


def write_history(history_path: Path, payload: dict[str, Any]) -> None:
    payload["version"] = STATUS_SCHEMA_VERSION
    payload["updated_at"] = now_iso()
    save_json(history_path, payload)


def _load_findings(findings_path: Path) -> list[dict[str, Any]]:
    payload = read_json_if_exists(findings_path, [])
    if isinstance(payload, list):
        return [dict(item) for item in payload]
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return [dict(item) for item in items]
    return []


def _load_briefing_items(briefing_path: Path) -> list[dict[str, Any]]:
    payload = read_json_if_exists(briefing_path, {})
    if isinstance(payload, dict):
        items = payload.get("items", [])
        if isinstance(items, list):
            return [dict(item) for item in items]
    return []


def _repo_run_dir_from_manifest(app_run_dir: Path) -> Path | None:
    manifest_path = app_run_dir / "manifest.json"
    if not manifest_path.exists():
        return None
    payload = read_json_if_exists(manifest_path, {})
    repo_run_dir = str(payload.get("repo_run_dir", "")).strip()
    if not repo_run_dir:
        return None
    return Path(repo_run_dir).expanduser().resolve()


def build_run_summary(
    run_id: str,
    app_run_dir: Path,
    result_payload: dict[str, Any] | None,
    repo_run_dir: Path | None = None,
) -> dict[str, Any]:
    resolved_repo_run_dir = repo_run_dir or _repo_run_dir_from_manifest(app_run_dir)
    findings_path = resolved_repo_run_dir / "memory-findings.json" if resolved_repo_run_dir else None
    briefing_path = resolved_repo_run_dir / "briefing.json" if resolved_repo_run_dir else None
    findings = _load_findings(findings_path) if findings_path else []
    briefing_items = _load_briefing_items(briefing_path) if briefing_path else []
    state = str((result_payload or {}).get("state", "unknown")).strip() or "unknown"
    publish_targets = sorted(
        [
            name
            for name in ("notion-payload.json", "feishu-payload.json")
            if resolved_repo_run_dir and (resolved_repo_run_dir / name).exists()
        ]
    )
    pushed = state in {"success", "partial_success"} and bool(publish_targets)
    feishu_publish_result = read_json_if_exists(
        resolved_repo_run_dir / "feishu-publish-result.json",
        {},
    ) if resolved_repo_run_dir else {}
    return {
        "version": STATUS_SCHEMA_VERSION,
        "run_id": run_id,
        "generated_at": now_iso(),
        "state": state,
        "message": str((result_payload or {}).get("message", "")).strip(),
        "updated_at": str((result_payload or {}).get("updated_at", "")).strip(),
        "repo_run_dir": str(resolved_repo_run_dir) if resolved_repo_run_dir else "",
        "app_run_dir": str(app_run_dir.resolve()),
        "metrics": {
            "records_scanned": len(findings),
            "webpages_searched": sum(1 for item in findings if str(item.get("source", "")).strip() == "web_search"),
            "recommendations_produced": len(briefing_items),
        },
        "published": pushed,
        "publish_targets": publish_targets,
        "publish_results": {
            "feishu": str(feishu_publish_result.get("state", "")).strip() or "missing",
        },
    }


def write_run_summary(app_run_dir: Path, summary: dict[str, Any]) -> Path:
    path = run_summary_path(app_run_dir)
    save_json(path, summary)
    return path


def load_run_summary(app_run_dir: Path) -> dict[str, Any] | None:
    path = run_summary_path(app_run_dir)
    if not path.exists():
        return None
    payload = read_json_if_exists(path, {})
    if payload.get("version") != STATUS_SCHEMA_VERSION:
        return None
    return payload


def update_history_with_summary(history_path: Path, summary: dict[str, Any]) -> dict[str, Any]:
    payload = load_history(history_path)
    run_id = str(summary.get("run_id", "")).strip()
    if not run_id:
        return payload
    if run_id in payload["aggregated_run_ids"]:
        return payload

    payload["aggregated_run_ids"].append(run_id)
    if summary.get("published"):
        metrics = summary.get("metrics", {})
        payload["totals"]["push_count"] += 1
        payload["totals"]["pushed_recommendations_total"] += int(metrics.get("recommendations_produced", 0) or 0)
    write_history(history_path, payload)
    return payload


def latest_run_snapshot(paths: GTNPaths) -> tuple[dict[str, Any] | None, Path | None]:
    runs = sorted(path for path in paths.runs_dir.iterdir() if path.is_dir()) if paths.runs_dir.exists() else []
    if not runs:
        return None, None
    latest = runs[-1]
    summary = load_run_summary(latest)
    if summary is not None:
        return summary, latest

    result_path = latest / "result.json"
    result_payload = read_json_if_exists(result_path, {}) if result_path.exists() else {}
    return build_run_summary(latest.name, latest, result_payload or None), latest


def compute_feedback_distribution(runtime_repo: Path) -> dict[str, int]:
    settings_path = runtime_repo / "output" / "notion-briefing" / "settings.json"
    index_path = runtime_repo / "output" / "notion-briefing" / "page_index.json"
    settings = read_json_if_exists(settings_path, {})
    index = read_json_if_exists(index_path, {"pages": {}})
    default_status = str(settings.get("default_status", "No feedback")).strip() or "No feedback"
    counts = {default_status: 0, "Good to know": 0, "Bad recommendation": 0}
    pages = index.get("pages", {})
    if not isinstance(pages, dict):
        return counts
    for payload in pages.values():
        status = str(payload.get("last_seen_status", default_status)).strip() or default_status
        counts.setdefault(status, 0)
        counts[status] += 1
    return counts


def _read_texts(paths: list[Path]) -> str:
    parts: list[str] = []
    for path in paths:
        if not path.exists():
            continue
        parts.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(parts)


def top_profile_keywords(runtime_repo: Path, limit: int = 6) -> list[tuple[str, int]]:
    text = _read_texts(
        [
            runtime_repo / "memory" / "naive-memory" / "user_context.md",
            runtime_repo / "context" / "naive-context" / "outbox.md",
        ]
    )
    counts: Counter[str] = Counter()
    for token in TOKEN_RE.findall(text.lower()):
        if token in STOPWORDS:
            continue
        counts[token] += 1
    return counts.most_common(limit)


def runtime_storage_bytes(runtime_repo: Path) -> int:
    if not runtime_repo.exists():
        return 0
    total = 0
    for path in runtime_repo.rglob("*"):
        try:
            if path.is_symlink():
                continue
            if path.is_file():
                total += path.stat().st_size
        except OSError:
            continue
    return total


def ensure_state_initialized_at(state: StateData) -> StateData:
    if not state.initialized_at:
        state.initialized_at = now_iso()
    return state
