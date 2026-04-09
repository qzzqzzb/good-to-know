from __future__ import annotations

import importlib.util
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from urllib import error

ROOT = Path(__file__).resolve().parents[2]


def load_module(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


module = load_module(ROOT / "output/feishu-briefing/scripts/publish_feishu_webhook.py", "publish_feishu_webhook")


class FakeResponse:
    def __init__(self, body: str, status: int = 200):
        self._body = body.encode("utf-8")
        self.status = status

    def read(self) -> bytes:
        return self._body

    def __enter__(self) -> "FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None


class PublishFeishuWebhookTests(unittest.TestCase):
    def test_publish_message_reports_success(self) -> None:
        def fake_urlopen(req, timeout=20):
            self.assertEqual(req.full_url, "https://example.com/hook")
            payload = json.loads(req.data.decode("utf-8"))
            self.assertEqual(payload["msg_type"], "text")
            return FakeResponse('{"code":0,"msg":"success","data":{}}')

        state, message, details = module.publish_message(
            "https://example.com/hook",
            {"msg_type": "text", "content": {"text": "hello"}},
            urlopen_func=fake_urlopen,
        )

        self.assertEqual(state, "success")
        self.assertIn("succeeded", message)
        self.assertEqual(details["http_status"], 200)

    def test_publish_message_reports_feishu_error(self) -> None:
        def fake_urlopen(req, timeout=20):
            return FakeResponse('{"code":19024,"msg":"Key Words Not Found"}')

        state, message, details = module.publish_message(
            "https://example.com/hook",
            {"msg_type": "text", "content": {"text": "hello"}},
            urlopen_func=fake_urlopen,
        )

        self.assertEqual(state, "failed")
        self.assertIn("19024", message)
        self.assertEqual(details["response_body"]["msg"], "Key Words Not Found")

    def test_build_result_for_unconfigured_webhook_can_be_written(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            result_path = Path(tmp) / "feishu-publish-result.json"
            result = module.build_result(
                "skipped",
                "Feishu webhook is not configured",
                {"webhook_configured": False},
            )
            result_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            written = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(written["state"], "skipped")
            self.assertFalse(written["details"]["webhook_configured"])

    def test_publish_message_rejects_oversized_payload_before_request(self) -> None:
        oversized = {"msg_type": "text", "content": {"text": "内容" * 20_000}}

        def fail_if_called(req, timeout=20):
            raise AssertionError("urlopen should not be called for oversized payloads")

        state, message, details = module.publish_message(
            "https://example.com/hook",
            oversized,
            urlopen_func=fail_if_called,
        )

        self.assertEqual(state, "failed")
        self.assertIn("exceeds", message)
        self.assertGreater(details["body_size_bytes"], module.MAX_REQUEST_BODY_BYTES)

    def test_publish_message_falls_back_to_curl_on_ssl_verify_failure(self) -> None:
        def failing_urlopen(req, timeout=20):
            raise error.URLError("[SSL: CERTIFICATE_VERIFY_FAILED] self-signed certificate in certificate chain")

        def fake_run(command, capture_output=True, text=True, check=False):
            output_index = command.index("-o") + 1
            response_path = Path(command[output_index])
            response_path.write_text('{"code":0,"msg":"success","data":{}}', encoding="utf-8")
            return subprocess.CompletedProcess(command, 0, "200", "")

        state, message, details = module.publish_message(
            "https://example.com/hook",
            {"msg_type": "text", "content": {"text": "hello"}},
            urlopen_func=failing_urlopen,
            curl_path_resolver=lambda name: "/usr/bin/curl",
            run_func=fake_run,
        )

        self.assertEqual(state, "success")
        self.assertIn("succeeded", message)
        self.assertEqual(details["transport"], "curl")


if __name__ == "__main__":
    unittest.main()
