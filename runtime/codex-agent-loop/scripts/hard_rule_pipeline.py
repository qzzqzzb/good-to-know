from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import unescape
from pathlib import Path
import sys
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

SCRIPT_DIR = Path(__file__).resolve().parent


def find_import_root(start: Path) -> Path:
    for candidate in [start, *start.parents]:
        if (candidate / "runtime" / "gtn_local_product" / "hard_rule_config.py").exists():
            return candidate
    return start


IMPORT_ROOT = find_import_root(SCRIPT_DIR)
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))
if str(IMPORT_ROOT) not in sys.path:
    sys.path.insert(0, str(IMPORT_ROOT))

from runtime.gtn_local_product.hard_rule_config import load_refresh_state, load_subscriptions, save_refresh_state, should_refresh_hard_rules
from runtime.gtn_local_product.paths import resolve_paths

from build_hard_rule_briefing import build_payload, render_markdown

ARXIV_API_URL = "https://export.arxiv.org/api/query"
PRODUCT_HUNT_URL = "https://www.producthunt.com/"
TAG_RE = re.compile(r"<[^>]+>")
WHITESPACE_RE = re.compile(r"\s+")
ARXIV_MAX_AGE_DAYS = 90


@dataclass
class HardRuleRunResult:
    state: str
    reason: str
    item_count: int
    processed_subscription_ids: list[str]
    skipped_subscription_ids: list[str]
    artifact_paths: list[str]


@dataclass
class HardRuleWorklist:
    eligible_subscriptions: list[dict]
    skipped_subscription_ids: list[str]


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def parse_published_at(value: object) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        return datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None


def filter_hard_rule_items(items: list[dict], now: datetime | None = None) -> list[dict]:
    current = now or datetime.now(timezone.utc)
    minimum_published_at = current - timedelta(days=ARXIV_MAX_AGE_DAYS)
    filtered: list[dict] = []
    for item in items:
        source = str(item.get("source", "")).strip().lower()
        if source != "arxiv":
            filtered.append(item)
            continue
        published_at = parse_published_at(item.get("published_at"))
        if published_at is None:
            continue
        published_utc = published_at.astimezone(timezone.utc)
        if published_utc >= minimum_published_at:
            filtered.append(item)
    return filtered


def build_hard_rule_worklist() -> HardRuleWorklist:
    paths = resolve_paths()
    subscriptions = load_subscriptions(paths)
    refresh_state = load_refresh_state(paths)
    refresh_entries = refresh_state.setdefault("subscriptions", {})
    eligible: list[dict] = []
    skipped_ids: list[str] = []
    for item in subscriptions:
        subscription_id = str(item.get("id", "")).strip()
        last_refreshed_at = None
        if isinstance(refresh_entries, dict):
            entry = refresh_entries.get(subscription_id, {})
            if isinstance(entry, dict):
                last_refreshed_at = str(entry.get("last_refreshed_at", "")).strip() or None
        if should_refresh_hard_rules(last_refreshed_at):
            eligible.append(item)
        else:
            skipped_ids.append(subscription_id)
    return HardRuleWorklist(eligible_subscriptions=eligible, skipped_subscription_ids=skipped_ids)


def update_refresh_state(processed_subscription_ids: list[str], items: list[dict]) -> None:
    paths = resolve_paths()
    refresh_state = load_refresh_state(paths)
    refresh_entries = refresh_state.setdefault("subscriptions", {})
    if not isinstance(refresh_entries, dict):
        return
    timestamp = now_iso()
    item_counts: dict[str, int] = {}
    for item in items:
        subscription_id = str(item.get("subscription_id", "")).strip()
        if not subscription_id:
            continue
        item_counts[subscription_id] = item_counts.get(subscription_id, 0) + 1
    for subscription_id in processed_subscription_ids:
        refresh_entries[subscription_id] = {
            "last_refreshed_at": timestamp,
            "last_item_count": item_counts.get(subscription_id, 0),
        }
    save_refresh_state(paths, refresh_state)


def finalize_hard_rule_items(
    run_id: str,
    run_dir: Path,
    items: list[dict],
    result_path: Path | None = None,
    processed_subscription_ids: list[str] | None = None,
    skipped_subscription_ids: list[str] | None = None,
    now: datetime | None = None,
) -> HardRuleRunResult:
    items = filter_hard_rule_items(items, now=now)
    payload = build_payload(items, run_id)
    json_path = run_dir / "hard-rule-briefing.json"
    md_path = run_dir / "hard-rule-briefing.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")
    processed_ids = list(processed_subscription_ids or [])
    skipped_ids = list(skipped_subscription_ids or [])
    if processed_ids:
        update_refresh_state(processed_ids, items)
    result = HardRuleRunResult(
        state="success",
        reason="refreshed",
        item_count=len(items),
        processed_subscription_ids=processed_ids,
        skipped_subscription_ids=skipped_ids,
        artifact_paths=[str(json_path), str(md_path)],
    )
    write_result(result_path, result)
    return result


def run_hard_rule_subscriptions(run_id: str, run_dir: Path, result_path: Path | None = None) -> HardRuleRunResult:
    worklist = build_hard_rule_worklist()
    if not worklist.eligible_subscriptions and not worklist.skipped_subscription_ids:
        result = HardRuleRunResult("skipped", "no_subscriptions", 0, [], [], [])
        write_result(result_path, result)
        return result

    if not worklist.eligible_subscriptions:
        result = HardRuleRunResult("skipped", "fresh_enough", 0, [], worklist.skipped_subscription_ids, [])
        write_result(result_path, result)
        return result

    items: list[dict] = []
    processed_ids: list[str] = []
    for subscription in worklist.eligible_subscriptions:
        fetched = fetch_subscription_items(subscription)
        items.extend(fetched)
        processed_ids.append(str(subscription.get("id", "")))
    return finalize_hard_rule_items(
        run_id=run_id,
        run_dir=run_dir,
        items=items,
        result_path=result_path,
        processed_subscription_ids=processed_ids,
        skipped_subscription_ids=worklist.skipped_subscription_ids,
    )


def write_result(path: Path | None, result: HardRuleRunResult) -> None:
    if path is None:
        return
    payload = {
        "state": result.state,
        "reason": result.reason,
        "item_count": result.item_count,
        "processed_subscription_ids": result.processed_subscription_ids,
        "skipped_subscription_ids": result.skipped_subscription_ids,
        "artifact_paths": result.artifact_paths,
        "updated_at": now_iso(),
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def fetch_subscription_items(subscription: dict) -> list[dict]:
    source = str(subscription.get("source", "")).strip()
    if source == "arxiv":
        return fetch_arxiv_items(subscription)
    if source == "producthunt":
        return fetch_producthunt_items(subscription)
    return []


def fetch_arxiv_items(subscription: dict) -> list[dict]:
    topic = str(subscription.get("topic", "")).strip()
    top_n = int(subscription.get("top_n", 5))
    query = quote_plus(topic)
    request = Request(
        f"{ARXIV_API_URL}?search_query=all:{query}&start=0&max_results={top_n}&sortBy=submittedDate&sortOrder=descending",
        headers={"User-Agent": "goodtoknow-gtn-hard-rules/1.0"},
    )
    with urlopen(request, timeout=15) as response:
        payload = response.read()
    root = ET.fromstring(payload)
    ns = {"atom": "http://www.w3.org/2005/Atom"}
    items: list[dict] = []
    for entry in root.findall("atom:entry", ns):
        title = compact_whitespace(entry.findtext("atom:title", default="", namespaces=ns))
        summary = compact_whitespace(entry.findtext("atom:summary", default="", namespaces=ns))
        link = compact_whitespace(entry.findtext("atom:id", default="", namespaces=ns))
        published = compact_whitespace(entry.findtext("atom:published", default="", namespaces=ns))
        if not title or not link:
            continue
        items.append(
            {
                "subscription_id": subscription.get("id", ""),
                "source": "arxiv",
                "topic": topic,
                "title": title,
                "summary": summary or title,
                "link": link,
                "published_at": published,
                "dedup_key": f"hard-rule:arxiv:{link}",
                "raw": link,
            }
        )
    return items


def fetch_producthunt_items(subscription: dict) -> list[dict]:
    topic = str(subscription.get("topic", "")).strip()
    top_n = int(subscription.get("top_n", 5))
    request = Request(
        PRODUCT_HUNT_URL,
        headers={"User-Agent": "goodtoknow-gtn-hard-rules/1.0"},
    )
    with urlopen(request, timeout=15) as response:
        html = response.read().decode("utf-8", errors="replace")

    cards = re.findall(r'href="(/products/[^"]+|/posts/[^"]+)".{0,240}?>(.*?)</a>', html, flags=re.IGNORECASE | re.DOTALL)
    items: list[dict] = []
    seen_links: set[str] = set()
    topic_terms = [part for part in re.split(r"\s+", topic.lower()) if part]
    for relative_link, raw_title in cards:
        link = f"https://www.producthunt.com{relative_link}"
        if link in seen_links:
            continue
        seen_links.add(link)
        title = compact_whitespace(unescape(TAG_RE.sub(" ", raw_title)))
        if not title:
            continue
        searchable = title.lower()
        if topic_terms and not any(term in searchable for term in topic_terms):
            continue
        items.append(
            {
                "subscription_id": subscription.get("id", ""),
                "source": "producthunt",
                "topic": topic,
                "title": title,
                "summary": title,
                "link": link,
                "published_at": "",
                "dedup_key": f"hard-rule:producthunt:{link}",
                "raw": link,
            }
        )
        if len(items) >= top_n:
            break
    return items


def compact_whitespace(value: str) -> str:
    return WHITESPACE_RE.sub(" ", value).strip()
