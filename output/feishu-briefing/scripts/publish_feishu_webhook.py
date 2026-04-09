from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import tempfile
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


def should_try_curl_fallback(reason: object) -> bool:
    text = str(reason)
    ssl_markers = (
        "CERTIFICATE_VERIFY_FAILED",
        "certificate verify failed",
        "self-signed certificate",
    )
    return any(marker in text for marker in ssl_markers)


def publish_with_curl(
    webhook_url: str,
    message: dict,
    curl_bin: str,
    run_func=subprocess.run,
) -> tuple[str, str, dict]:
    payload = json.dumps(message, ensure_ascii=False)
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as body_file:
        body_file.write(payload)
        body_file.flush()
        body_path = body_file.name
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".json", delete=False) as response_file:
        response_path = response_file.name

    command = [
        curl_bin,
        "-sS",
        "-o",
        response_path,
        "-w",
        "%{http_code}",
        "-H",
        "Content-Type: application/json; charset=utf-8",
        "--data-binary",
        f"@{body_path}",
        webhook_url,
    ]
    result = run_func(command, capture_output=True, text=True, check=False)

    try:
        response_text = Path(response_path).read_text(encoding="utf-8")
    except FileNotFoundError:
        response_text = ""
    finally:
        Path(body_path).unlink(missing_ok=True)
        Path(response_path).unlink(missing_ok=True)

    if result.returncode != 0:
        details = {
            "curl_returncode": result.returncode,
            "stderr": result.stderr.strip(),
            "stdout": result.stdout.strip(),
        }
        return "failed", "Feishu webhook curl fallback failed", details

    try:
        status_code = int((result.stdout or "0").strip() or "0")
    except ValueError:
        status_code = 0

    try:
        response_payload = json.loads(response_text)
    except json.JSONDecodeError:
        details = {"http_status": status_code, "response_body": response_text, "transport": "curl"}
        return "failed", "Feishu webhook curl fallback returned a non-JSON response", details

    if status_code >= 400:
        details = {"http_status": status_code, "response_body": response_payload, "transport": "curl"}
        return "failed", f"Feishu webhook returned HTTP {status_code}", details

    response_code = response_payload.get("code", 0)
    if response_code != 0:
        details = {"http_status": status_code, "response_body": response_payload, "transport": "curl"}
        return "failed", f"Feishu webhook rejected payload with code {response_code}", details

    details = {"http_status": status_code, "response_body": response_payload, "transport": "curl"}
    return "success", "Feishu webhook publish succeeded", details


def publish_message(
    webhook_url: str,
    message: dict,
    urlopen_func=request.urlopen,
    curl_path_resolver=shutil.which,
    run_func=subprocess.run,
) -> tuple[str, str, dict]:
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
        if should_try_curl_fallback(exc.reason):
            curl_bin = curl_path_resolver("curl")
            if curl_bin:
                return publish_with_curl(webhook_url, message, curl_bin=curl_bin, run_func=run_func)
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
