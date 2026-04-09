from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from urllib import error, request

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
SETTINGS_PATH = SKILL_DIR / "settings.json"
MAX_REQUEST_BODY_BYTES = 20_000


def load_json(path: Path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def now_iso() -> str:
    return datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds")


def build_result(state: str, message: str, details: dict) -> dict:
    return {
        "state": state,
        "message": message,
        "updated_at": now_iso(),
        "details": details,
    }


def message_body_size(message: dict) -> int:
    return len(json.dumps(message, ensure_ascii=False).encode("utf-8"))


def publish_message(webhook_url: str, message: dict, urlopen_func=request.urlopen) -> tuple[str, str, dict]:
    body_size = message_body_size(message)
    if body_size > MAX_REQUEST_BODY_BYTES:
        details = {
            "body_size_bytes": body_size,
            "max_request_body_bytes": MAX_REQUEST_BODY_BYTES,
        }
        return "failed", "Feishu webhook payload exceeds the request-body budget", details

    payload = json.dumps(message, ensure_ascii=False).encode("utf-8")
    req = request.Request(
        webhook_url,
        data=payload,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urlopen_func(req, timeout=20) as response:
            status_code = getattr(response, "status", 200)
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        details = {"http_status": exc.code, "response_body": body}
        return "failed", f"Feishu webhook returned HTTP {exc.code}", details
    except error.URLError as exc:
        details = {"reason": str(exc.reason)}
        return "failed", f"Feishu webhook request failed: {exc.reason}", details

    try:
        response_payload = json.loads(body)
    except json.JSONDecodeError:
        details = {"http_status": status_code, "response_body": body}
        return "failed", "Feishu webhook returned a non-JSON response", details

    if status_code >= 400:
        details = {"http_status": status_code, "response_body": response_payload}
        return "failed", f"Feishu webhook returned HTTP {status_code}", details

    if "code" not in response_payload:
        details = {"http_status": status_code, "response_body": response_payload}
        return "failed", "Feishu webhook response did not include a result code", details

    response_code = response_payload.get("code", 0)
    if response_code != 0:
        details = {"http_status": status_code, "response_body": response_payload}
        return "failed", f"Feishu webhook rejected payload with code {response_code}", details

    details = {"http_status": status_code, "response_body": response_payload}
    return "success", "Feishu webhook publish succeeded", details


def main() -> None:
    parser = argparse.ArgumentParser(description="Publish a Feishu payload to a custom bot webhook.")
    parser.add_argument("feishu_payload_path", help="Path to feishu-payload.json")
    parser.add_argument(
        "--output",
        help="Optional explicit output path. Defaults to feishu-publish-result.json next to the input payload",
    )
    args = parser.parse_args()

    payload_path = Path(args.feishu_payload_path).resolve()
    if not payload_path.exists():
        raise SystemExit(f"Feishu payload not found: {payload_path}")

    settings = load_json(SETTINGS_PATH)
    payload = load_json(payload_path)
    webhook_url = str(settings.get("webhook_url", "")).strip()
    output_path = Path(args.output).resolve() if args.output else payload_path.with_name("feishu-publish-result.json")

    if not webhook_url:
        result = build_result(
            "skipped",
            "Feishu webhook is not configured",
            {
                "payload_path": str(payload_path),
                "webhook_configured": False,
            },
        )
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"[feishu-briefing] skipped publish because webhook_url is empty")
        return

    state, message, details = publish_message(webhook_url, payload["message"])
    result = build_result(
        state,
        message,
        {
            "payload_path": str(payload_path),
            "webhook_configured": True,
            **details,
        },
    )
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[feishu-briefing] {message.lower()}")


if __name__ == "__main__":
    main()
