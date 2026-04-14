from __future__ import annotations

import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
RUNTIME_DIR = SCRIPT_DIR.parent
REPO_ROOT = RUNTIME_DIR.parent.parent
DEFAULT_RUNS_DIR = REPO_ROOT / "runs"
ENTRY_PATTERN = re.compile(r"^##\s+(.+)$", re.MULTILINE)


def split_entries(text: str) -> list[tuple[str, str]]:
    matches = list(ENTRY_PATTERN.finditer(text))
    entries: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        entry_id = match.group(1).strip()
        start = match.start()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        block = text[start:end].strip()
        if block:
            entries.append((entry_id, block))
    return entries


def parse_tags(raw_value: str) -> list[str]:
    value = raw_value.strip()
    if value.startswith("[") and value.endswith("]"):
        inner = value[1:-1].strip()
        if not inner:
            return []
        return [part.strip() for part in inner.split(",") if part.strip()]
    return [value] if value else []


def parse_block(entry_id: str, block: str) -> dict:
    lines = block.splitlines()
    data: dict[str, object] = {"entry_id": entry_id}
    current_key: str | None = None
    current_mode: str | None = None
    buffer: list[str] = []

    def flush_buffer() -> None:
        nonlocal current_key, current_mode, buffer
        if current_key is None:
            return
        text = "\n".join(buffer).strip()
        data[current_key] = text
        current_key = None
        current_mode = None
        buffer = []

    for line in lines[1:]:
        if line.startswith("- "):
            flush_buffer()
            content = line[2:]
            if ":" not in content:
                continue
            key, raw_value = content.split(":", 1)
            key = key.strip()
            value = raw_value.strip()

            if value in {">", "|"}:
                current_key = key
                current_mode = value
                buffer = []
                continue

            if key == "tags":
                data[key] = parse_tags(value)
            else:
                data[key] = value
            continue

        if current_key is not None and (line.startswith("  ") or not line.strip()):
            if current_mode == ">":
                stripped = line.strip()
                if stripped:
                    buffer.append(stripped)
            else:
                buffer.append(line[2:] if line.startswith("  ") else "")

    flush_buffer()
    return data


def load_findings(path: Path) -> list[dict]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(payload, list):
            records = payload
        else:
            records = payload.get("items", [])
        return [dict(record) for record in records]

    text = path.read_text(encoding="utf-8")
    records = []
    for entry_id, block in split_entries(text):
        record = parse_block(entry_id, block)
        if record.get("type") != "finding":
            continue
        records.append(record)
    records.sort(key=lambda item: str(item.get("time", "")), reverse=True)
    return records


def parse_score(raw_value: object) -> int:
    try:
        score = int(str(raw_value).strip())
    except (TypeError, ValueError):
        return 5
    return max(1, min(10, score))


def build_run_id() -> str:
    now = datetime.now(timezone.utc).astimezone()
    return now.isoformat(timespec="seconds").replace(":", "-")


def sort_time_key(raw_value: object) -> float:
    value = str(raw_value).strip()
    if not value:
        return 0.0
    parsed = _parse_iso_datetime(value)
    return parsed.timestamp() if parsed else 0.0


def _parse_iso_datetime(value: str) -> datetime | None:
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def build_briefing_payload(findings: list[dict], run_id: str, wakeup_text: str = "") -> dict:
    generated_at = datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")
    items = []
    missing_score_items: list[str] = []

    for finding in findings:
        summary = str(finding.get("summary", "")).strip()
        raw_score = finding.get("score")
        if raw_score in (None, ""):
            missing_score_items.append(str(finding.get("entry_id", "(unknown)")))
        score = parse_score(raw_score if raw_score not in (None, "") else 5)
        why_recommended = str(finding.get("why_recommended", "")).strip()
        digest = str(finding.get("digest", "")).strip() or summary
        item = {
            "entry_id": finding.get("entry_id", ""),
            "dedup_key": finding.get("dedup_key", ""),
            "time": finding.get("time", ""),
            "source": finding.get("source", ""),
            "title": finding.get("title") or summary or finding.get("entry_id", ""),
            "tags": finding.get("tags", []),
            "score": score,
            "summary": summary,
            "why_recommended": why_recommended,
            "digest": digest,
            "raw": finding.get("raw", ""),
        }
        items.append(item)

    items.sort(key=lambda item: (int(item.get("score", 5)), sort_time_key(item.get("time", ""))), reverse=True)
    for recommendation_index, item in enumerate(items, start=1):
        item["recommendation_index"] = recommendation_index

    return {
        "run_id": run_id,
        "generated_at": generated_at,
        "memory_wakeup": wakeup_text,
        "warnings": {
            "missing_score_entry_ids": missing_score_items,
        },
        "items": items,
    }


def render_markdown(payload: dict) -> str:
    lines = [
        "# Briefing",
        "",
        f"- run_id: {payload['run_id']}",
        f"- generated_at: {payload['generated_at']}",
        f"- items: {len(payload['items'])}",
        "",
    ]

    missing_score_items = payload.get("warnings", {}).get("missing_score_entry_ids", [])
    if missing_score_items:
        lines.extend(
            [
                "## Warnings",
                f"- missing_score_entry_ids: [{', '.join(missing_score_items)}]",
                "",
            ]
        )

    for item in payload["items"]:
        tags = ", ".join(item.get("tags", []))
        lines.extend(
            [
                f"## {item['title']}",
                f"- recommendation_index: {item.get('recommendation_index', '')}",
                f"- entry_id: {item['entry_id']}",
                f"- dedup_key: {item['dedup_key']}",
                f"- time: {item['time']}",
                f"- source: {item['source']}",
                f"- score: {item['score']}/10",
                f"- tags: [{tags}]",
                f"- raw: {item['raw']}",
                "",
                "### Summary",
                item["summary"] or "(missing summary)",
                "",
                "### Why Recommended",
                item["why_recommended"] or "(missing why_recommended)",
                "",
                "### Digest",
                item["digest"] or "(missing digest)",
                "",
            ]
        )

    return "\n".join(lines).rstrip() + "\n"


def resolve_run_dir(output_dir: Path, run_id: str | None, explicit_run_dir: Path | None) -> tuple[str, Path]:
    if explicit_run_dir is not None:
        resolved_dir = explicit_run_dir.resolve()
        effective_run_id = run_id or resolved_dir.name
        return effective_run_id, resolved_dir
    effective_run_id = run_id or build_run_id()
    return effective_run_id, output_dir.resolve() / effective_run_id


def write_result(path: Path, state: str, message: str, payload: dict) -> None:
    result = {
        "state": state,
        "message": message,
        "updated_at": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "details": payload,
    }
    path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description="Build a richer briefing artifact from stored findings.")
    parser.add_argument(
        "findings_path",
        nargs="?",
        help="Path to findings input. Supports legacy markdown and JSON exports from the active memory module.",
    )
    parser.add_argument(
        "--output-dir",
        default=str(DEFAULT_RUNS_DIR),
        help="Base output directory. A run subdirectory will be created inside it.",
    )
    parser.add_argument("--run-id", help="Optional explicit run id to reuse for artifact generation")
    parser.add_argument("--run-dir", help="Optional explicit run directory to write into")
    parser.add_argument("--wakeup-path", help="Optional path to session-start wake-up text")
    parser.add_argument("--result-path", help="Optional structured result JSON output path")
    args = parser.parse_args()

    if args.findings_path:
        findings_path = Path(args.findings_path).resolve()
    elif args.run_dir:
        findings_path = Path(args.run_dir).resolve() / "memory-findings.json"
    else:
        raise SystemExit("Findings input not provided. Pass a findings path or use --run-dir with memory-findings.json present.")
    if not findings_path.exists():
        raise SystemExit(f"Findings not found: {findings_path}")

    run_id, run_dir = resolve_run_dir(
        output_dir=Path(args.output_dir),
        run_id=args.run_id,
        explicit_run_dir=Path(args.run_dir) if args.run_dir else None,
    )
    run_dir.mkdir(parents=True, exist_ok=True)

    wakeup_text = ""
    if args.wakeup_path:
        wakeup_path = Path(args.wakeup_path).resolve()
        if not wakeup_path.exists():
            raise SystemExit(f"Wake-up text not found: {wakeup_path}")
        wakeup_text = wakeup_path.read_text(encoding="utf-8")

    payload = build_briefing_payload(load_findings(findings_path), run_id, wakeup_text=wakeup_text)

    missing_score_items = payload.get("warnings", {}).get("missing_score_entry_ids", [])
    if missing_score_items:
        print(
            "[codex-agent-loop] warning: missing score for "
            + ", ".join(missing_score_items)
            + "; defaulted to 5/10"
        )

    json_path = run_dir / "briefing.json"
    md_path = run_dir / "briefing.md"
    json_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(payload), encoding="utf-8")

    if args.result_path:
        write_result(
            Path(args.result_path).resolve(),
            state="success",
            message="Briefing artifacts created",
            payload={"run_id": run_id, "run_dir": str(run_dir), "artifacts": [str(json_path), str(md_path)]},
        )

    print(f"[codex-agent-loop] wrote briefing json to {json_path}")
    print(f"[codex-agent-loop] wrote briefing markdown to {md_path}")


if __name__ == "__main__":
    main()
