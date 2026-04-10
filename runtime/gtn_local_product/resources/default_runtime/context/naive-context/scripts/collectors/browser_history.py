from __future__ import annotations

import hashlib
import os
import shutil
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

INTERNAL_SCHEMES = ("chrome://", "edge://", "brave://", "about:", "file://")
TRACKING_PREFIXES = (
    "utm_",
    "vero_",
    "mc_",
)
TRACKING_KEYS = {
    "fbclid",
    "gclid",
    "igshid",
    "si",
    "ref",
    "ref_src",
    "source",
}


def _slugify(value: str) -> str:
    cleaned = "".join(ch.lower() if ch.isalnum() else "-" for ch in value)
    slug = "-".join(part for part in cleaned.split("-") if part)
    return slug or "item"


def _short_hash(value: str, length: int = 8) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:length]


def _trim_tracking_params(params: Iterable[Tuple[str, str]]) -> list[Tuple[str, str]]:
    kept = []
    for key, value in params:
        lowered = key.lower()
        if lowered in TRACKING_KEYS or any(lowered.startswith(prefix) for prefix in TRACKING_PREFIXES):
            continue
        kept.append((key, value))
    return kept


def normalize_url(url: str) -> str:
    parsed = urlparse(url.strip())
    scheme = parsed.scheme.lower() or "https"
    netloc = parsed.netloc.lower()
    path = parsed.path or "/"
    if path != "/":
        path = path.rstrip("/")
    query = urlencode(_trim_tracking_params(parse_qsl(parsed.query, keep_blank_values=True)), doseq=True)
    return urlunparse((scheme, netloc, path, "", query, ""))


def build_context_dedup_key(browser: str, url: str, unix_timestamp: float) -> str:
    normalized_url = normalize_url(url)
    event_ts = int(unix_timestamp)
    return f"browser_history:{browser}:{normalized_url}:{event_ts}"


def build_context_entry_id(dedup_key: str, url: str, browser: str) -> str:
    parsed = urlparse(normalize_url(url))
    host = _slugify(parsed.netloc)
    path = _slugify(parsed.path)[:24].strip("-") or "page"
    return f"browser-history-{_slugify(browser)}-{host}-{path}-{_short_hash(dedup_key)}"


def chrome_time_to_unix(timestamp: int) -> Optional[float]:
    if not timestamp:
        return None
    try:
        return timestamp / 1_000_000 - 11644473600
    except Exception:
        return None


def firefox_time_to_unix(timestamp: int) -> Optional[float]:
    if not timestamp:
        return None
    try:
        return timestamp / 1_000_000
    except Exception:
        return None


def safe_copy_db(source_path: Path) -> Optional[Path]:
    if not source_path.exists():
        return None

    temp_dir = Path(tempfile.mkdtemp(prefix="naive-context-history-"))
    destination_path = temp_dir / source_path.name
    try:
        shutil.copy2(source_path, destination_path)
        return destination_path
    except Exception:
        return None


def get_platform() -> str:
    if sys.platform.startswith("win"):
        return "windows"
    if sys.platform.startswith("darwin"):
        return "mac"
    return "linux"


def get_chromium_history_paths() -> Dict[str, List[Path]]:
    platform_name = get_platform()
    home = Path.home()
    paths: Dict[str, List[Path]] = {"chrome": [], "edge": [], "brave": []}

    if platform_name == "windows":
        local = Path(os.environ.get("LOCALAPPDATA", ""))
        paths["chrome"] = [
            local / "Google/Chrome/User Data/Default/History",
            local / "Google/Chrome/User Data/Profile 1/History",
            local / "Google/Chrome/User Data/Profile 2/History",
        ]
        paths["edge"] = [
            local / "Microsoft/Edge/User Data/Default/History",
            local / "Microsoft/Edge/User Data/Profile 1/History",
            local / "Microsoft/Edge/User Data/Profile 2/History",
        ]
        paths["brave"] = [
            local / "BraveSoftware/Brave-Browser/User Data/Default/History",
            local / "BraveSoftware/Brave-Browser/User Data/Profile 1/History",
            local / "BraveSoftware/Brave-Browser/User Data/Profile 2/History",
        ]
    elif platform_name == "mac":
        paths["chrome"] = [
            home / "Library/Application Support/Google/Chrome/Default/History",
            home / "Library/Application Support/Google/Chrome/Profile 1/History",
            home / "Library/Application Support/Google/Chrome/Profile 2/History",
        ]
        paths["edge"] = [
            home / "Library/Application Support/Microsoft Edge/Default/History",
            home / "Library/Application Support/Microsoft Edge/Profile 1/History",
            home / "Library/Application Support/Microsoft Edge/Profile 2/History",
        ]
        paths["brave"] = [
            home / "Library/Application Support/BraveSoftware/Brave-Browser/Default/History",
            home / "Library/Application Support/BraveSoftware/Brave-Browser/Profile 1/History",
            home / "Library/Application Support/BraveSoftware/Brave-Browser/Profile 2/History",
        ]
    else:
        paths["chrome"] = [
            home / ".config/google-chrome/Default/History",
            home / ".config/google-chrome/Profile 1/History",
            home / ".config/google-chrome/Profile 2/History",
            home / ".config/chromium/Default/History",
        ]
        paths["edge"] = [
            home / ".config/microsoft-edge/Default/History",
            home / ".config/microsoft-edge/Profile 1/History",
            home / ".config/microsoft-edge/Profile 2/History",
        ]
        paths["brave"] = [
            home / ".config/BraveSoftware/Brave-Browser/Default/History",
            home / ".config/BraveSoftware/Brave-Browser/Profile 1/History",
            home / ".config/BraveSoftware/Brave-Browser/Profile 2/History",
        ]

    return paths


def get_firefox_history_paths() -> List[Path]:
    platform_name = get_platform()
    home = Path.home()

    if platform_name == "windows":
        base = Path(os.environ.get("APPDATA", "")) / "Mozilla/Firefox/Profiles"
    elif platform_name == "mac":
        base = home / "Library/Application Support/Firefox/Profiles"
    else:
        base = home / ".mozilla/firefox"

    if not base.exists():
        return []

    return list(base.glob("*/places.sqlite"))


def read_chromium_history(db_path: Path, browser_name: str) -> List[dict]:
    temp_db = safe_copy_db(db_path)
    if temp_db is None:
        return []

    query = """
    SELECT urls.url, urls.title, urls.visit_count, urls.last_visit_time
    FROM urls
    ORDER BY urls.last_visit_time DESC
    """

    records = []
    try:
        connection = sqlite3.connect(str(temp_db))
        cursor = connection.cursor()
        cursor.execute(query)
        for url, title, visit_count, last_visit_time in cursor.fetchall():
            records.append(
                {
                    "browser": browser_name,
                    "url": url,
                    "title": title or "",
                    "visit_count": visit_count or 0,
                    "last_visit_unix": chrome_time_to_unix(last_visit_time),
                }
            )
        connection.close()
    except Exception:
        return []

    return records


def read_firefox_history(db_path: Path) -> List[dict]:
    temp_db = safe_copy_db(db_path)
    if temp_db is None:
        return []

    query = """
    SELECT url, title, visit_count, last_visit_date
    FROM moz_places
    ORDER BY last_visit_date DESC
    """

    records = []
    try:
        connection = sqlite3.connect(str(temp_db))
        cursor = connection.cursor()
        cursor.execute(query)
        for url, title, visit_count, last_visit_date in cursor.fetchall():
            records.append(
                {
                    "browser": "firefox",
                    "url": url,
                    "title": title or "",
                    "visit_count": visit_count or 0,
                    "last_visit_unix": firefox_time_to_unix(last_visit_date),
                }
            )
        connection.close()
    except Exception:
        return []

    return records


def collect_all_history(selected_browsers: List[str]) -> List[dict]:
    records: List[dict] = []
    chromium_paths = get_chromium_history_paths()

    for browser_name in ("chrome", "edge", "brave"):
        if browser_name not in selected_browsers:
            continue
        for db_path in chromium_paths.get(browser_name, []):
            if db_path.exists():
                records.extend(read_chromium_history(db_path, browser_name))

    if "firefox" in selected_browsers:
        for db_path in get_firefox_history_paths():
            records.extend(read_firefox_history(db_path))

    return records


def is_recent(unix_timestamp: Optional[float], lookback_hours: int) -> bool:
    if unix_timestamp is None:
        return False
    try:
        visit_time = datetime.fromtimestamp(unix_timestamp, tz=timezone.utc)
    except (OSError, OverflowError, ValueError):
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(hours=lookback_hours)
    return visit_time >= cutoff


def normalize_history_records(records: List[dict], lookback_hours: int, max_entries: int) -> List[dict]:
    deduped: Dict[str, dict] = {}

    for record in records:
        url = (record.get("url") or "").strip()
        if not url or url.startswith(INTERNAL_SCHEMES):
            continue
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            continue
        if not is_recent(record.get("last_visit_unix"), lookback_hours):
            continue

        dedup_bucket = f"{record['browser']}::{normalize_url(url)}"
        existing = deduped.get(dedup_bucket)
        if existing is None or (record.get("last_visit_unix") or 0) > (existing.get("last_visit_unix") or 0):
            deduped[dedup_bucket] = record

    sorted_records = sorted(
        deduped.values(),
        key=lambda item: item.get("last_visit_unix") or 0,
        reverse=True,
    )

    observations = []
    for record in sorted_records[:max_entries]:
        visit_unix = record.get("last_visit_unix")
        if visit_unix is None:
            continue
        last_visit_time = datetime.fromtimestamp(visit_unix, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
        title = record.get("title") or urlparse(record["url"]).netloc
        dedup_key = build_context_dedup_key(record["browser"], record["url"], visit_unix)
        entry_id = build_context_entry_id(dedup_key, record["url"], record["browser"])
        observations.append(
            {
                "entry_id": entry_id,
                "dedup_key": dedup_key,
                "time": last_visit_time,
                "source": f"browser_history:{record['browser']}",
                "tags": ["browser_history", record["browser"]],
                "summary": f"Visited {title}",
                "raw": record["url"],
            }
        )

    return observations


def collect_browser_history_observations(settings: dict) -> List[dict]:
    lookback_hours = int(settings.get("lookback_hours", 72))
    max_entries = int(settings.get("max_entries", 20))
    selected_browsers = [str(name).lower() for name in settings.get("browsers", ["chrome", "edge", "brave", "firefox"])]
    records = collect_all_history(selected_browsers)
    return normalize_history_records(records, lookback_hours, max_entries)
