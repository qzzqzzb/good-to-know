from __future__ import annotations

import hashlib
import re
import sys
from typing import Iterable, Tuple
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

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
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
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


def build_dedup_key(url: str) -> str:
    normalized = normalize_url(url)
    lowered = normalized.lower()

    arxiv_match = re.search(r"arxiv\.org/(?:abs|pdf|html|e-print)/([0-9]{4}\.[0-9]+(?:v\d+)?)", lowered)
    if arxiv_match:
        identifier = re.sub(r"v\d+$", "", arxiv_match.group(1))
        return f"arxiv:{identifier}"

    doi_match = re.search(r"(?:dx\.)?doi\.org/(.+)", lowered)
    if doi_match:
        return f"doi:{doi_match.group(1).rstrip('/')}"

    github_issue_match = re.search(r"github\.com/([^/]+/[^/]+)/(issues|pull)/(\d+)", lowered)
    if github_issue_match:
        repo = github_issue_match.group(1)
        kind = github_issue_match.group(2)
        number = github_issue_match.group(3)
        return f"github:{repo}/{kind}/{number}"

    github_repo_match = re.search(r"github\.com/([^/]+/[^/?#]+)", lowered)
    if github_repo_match:
        return f"github:{github_repo_match.group(1).rstrip('/')}"

    hn_match = re.search(r"news\.ycombinator\.com/item\?id=(\d+)", lowered)
    if hn_match:
        return f"hn:{hn_match.group(1)}"

    return f"url:{normalized}"


def build_entry_id(dedup_key: str) -> str:
    if dedup_key.startswith("arxiv:"):
        return f"finding-arxiv-{_slugify(dedup_key.split(':', 1)[1])}"

    if dedup_key.startswith("doi:"):
        suffix = dedup_key.split(":", 1)[1]
        readable = _slugify(suffix)[:40].strip("-") or "doi"
        return f"finding-doi-{readable}-{_short_hash(dedup_key)}"

    if dedup_key.startswith("github:"):
        suffix = dedup_key.split(":", 1)[1]
        return f"finding-github-{_slugify(suffix)}"

    if dedup_key.startswith("hn:"):
        return f"finding-hn-{_slugify(dedup_key.split(':', 1)[1])}"

    if dedup_key.startswith("url:"):
        normalized_url = dedup_key.split(":", 1)[1]
        parsed = urlparse(normalized_url)
        host = _slugify(parsed.netloc)
        path = _slugify(parsed.path)[:24].strip("-") or "page"
        return f"finding-url-{host}-{path}-{_short_hash(dedup_key)}"

    return f"finding-{_slugify(dedup_key)[:40]}-{_short_hash(dedup_key)}"


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python3 discovery/web-discovery/scripts/make_finding_id.py <url>")

    url = sys.argv[1]
    dedup_key = build_dedup_key(url)
    entry_id = build_entry_id(dedup_key)
    print(f"entry_id: {entry_id}")
    print(f"dedup_key: {dedup_key}")


if __name__ == "__main__":
    main()
