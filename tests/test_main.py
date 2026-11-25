import unittest
import importlib
import logging
import tempfile
from logging.handlers import RotatingFileHandler
from pathlib import Path
from unittest.mock import AsyncMock, Mock

import httpx
from unittest.mock import patch

from config import Settings

import main


class PollingLoggingTests(unittest.TestCase):
    def test_import_does_not_configure_logging_or_open_files(self):
        handlers = logging.getLogger().handlers[:]
        try:
            with patch("logging.handlers.RotatingFileHandler", side_effect=AssertionError("Import must not open logs")):
                importlib.reload(main)
        finally:
            importlib.reload(main)
        self.assertEqual(logging.getLogger().handlers, handlers)

    def test_network_warning_does_not_include_exception_value(self):
        with self.assertLogs(main.logger, level="WARNING") as captured:
            main._log_polling_network_warning(Settings(max_bot_token="TEST_TOKEN"), "Network unavailable", RuntimeError("PRIVATE_TOKEN PRIVATE_TEXT"))
        self.assertNotIn("PRIVATE_", " ".join(captured.output))

    def test_log_file_rotates(self):
        root = logging.RootLogger(logging.INFO)
        real_get_logger = logging.getLogger
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "test.log"
            with patch("main.logging.getLogger", side_effect=lambda name=None: real_get_logger(name) if name else root):
                main.configure_logging(path)
            try:
                handler = next(h for h in root.handlers if isinstance(h, RotatingFileHandler))
                self.assertGreater(handler.backupCount, 0)
                handler.maxBytes = 1
                root.error("PRIVATE_CONTENT_MUST_NOT_APPEAR")
                root.error("PRIVATE_CONTENT_MUST_NOT_APPEAR")
                self.assertTrue(path.with_name("test.log.1").exists())
                self.assertNotIn("PRIVATE_CONTENT", path.read_text(encoding="utf-8"))
            finally:
                for handler in root.handlers:
                    handler.close()
    def test_logs_network_warning_when_suppression_disabled(self) -> None:
        settings = Settings(
            max_bot_token="token",
            suppress_polling_network_errors=False,
        )

        with patch.object(main.logger, "warning") as warning:
            main._log_polling_network_warning(
                settings,
                "Polling timeout, retrying in 5 seconds",
                RuntimeError("boom"),
            )

        warning.assert_called_once()

    def test_skips_network_warning_when_suppression_enabled(self) -> None:
        settings = Settings(
            max_bot_token="token",
            suppress_polling_network_errors=True,
        )

        with patch.object(main.logger, "warning") as warning:
            main._log_polling_network_warning(
                settings,
                "Polling timeout, retrying in 5 seconds",
                RuntimeError("boom"),
            )

        warning.assert_not_called()


class WebhookSecurityTests(unittest.IsolatedAsyncioTestCase):
    def settings(self):
        return Settings(max_bot_token="TEST_TOKEN", max_transport="webhook", max_webhook_url="https://example.test/webhook/max", max_webhook_secret="test_secret_123")

    async def test_missing_or_wrong_secret_cannot_process_an_update(self):
        service = Mock(handle_update=AsyncMock())
        app = main.create_app(self.settings(), service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as client:
            for secret in (None, "wrong_secret"):
                headers = {} if secret is None else {"X-Max-Bot-Api-Secret": secret}
                response = await client.post("/webhook/max", headers=headers, json={"update_type": "bot_started"})
                self.assertEqual(response.status_code, 403)
        service.handle_update.assert_not_awaited()

    async def test_valid_secret_is_compared_in_constant_time_and_processed(self):
        service = Mock(handle_update=AsyncMock())
        app = main.create_app(self.settings(), service)
        compare = main.secrets.compare_digest
        with patch("main.secrets.compare_digest", wraps=compare) as checked:
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as client:
                response = await client.post("/webhook/max", headers={"X-Max-Bot-Api-Secret": "test_secret_123"}, json={"update_type": "bot_started", "user": {"user_id": 42}, "chat_id": 7})
        self.assertEqual(response.status_code, 200)
        checked.assert_called_once()
        self.assertIsInstance(checked.call_args.args[0], bytes)
        service.handle_update.assert_awaited_once()

    async def test_malformed_json_and_non_object_are_rejected(self):
        service = Mock(handle_update=AsyncMock())
        app = main.create_app(self.settings(), service)
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app), base_url="https://test") as client:
            for content in ("not json", "[]"):
                response = await client.post("/webhook/max", headers={"X-Max-Bot-Api-Secret": "test_secret_123"}, content=content)
                self.assertEqual(response.status_code, 400)
        service.handle_update.assert_not_awaited()

    async def test_update_exception_does_not_log_sensitive_value(self):
        service = Mock(handle_update=AsyncMock(side_effect=RuntimeError("PRIVATE_TOKEN PRIVATE_APPEAL")))
        with self.assertLogs(main.logger, level="ERROR") as captured:
            await main.process_update(service, {"update_type": "message_created"})
        self.assertNotIn("PRIVATE_", " ".join(captured.output))

    async def test_endpoint_cannot_be_created_without_secret(self):
        with self.assertRaises(ValueError):
            main.create_app(Settings(max_bot_token="TEST_TOKEN"), Mock())


if __name__ == "__main__":
    unittest.main()
