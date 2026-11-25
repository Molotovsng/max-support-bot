import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from config import Settings, load_settings


class LoadSettingsTests(unittest.TestCase):
    def setUp(self) -> None:
        patcher = patch("config.load_dotenv")
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_current_api_is_default_and_secrets_are_not_in_repr(self):
        settings = Settings(max_bot_token="TEST_TOKEN_VALUE", max_webhook_secret="TEST_SECRET_VALUE")
        self.assertEqual(settings.max_api_base, "https://platform-api2.max.ru")
        self.assertNotIn("TEST_TOKEN_VALUE", repr(settings))
        self.assertNotIn("TEST_SECRET_VALUE", repr(settings))

    def test_invalid_settings_are_rejected_without_echoing_values(self):
        cases = (
            {"max_bot_token": "replace_me"},
            {"max_bot_token": "PRIVATE_TOKEN\nINJECTED"},
            {"max_api_base": "https://platform-api.max.ru"},
            {"max_api_base": "http://PRIVATE_TOKEN.example"},
            {"max_transport": "PRIVATE_TOKEN"},
            {"max_polling_timeout": 91}, {"max_polling_limit": 0}, {"app_port": 0},
        )
        for changed in cases:
            with self.subTest(fields=list(changed)):
                with self.assertRaises(ValueError) as caught:
                    Settings(**({"max_bot_token": "TEST_TOKEN"} | changed))
                self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    def test_webhook_requires_valid_secret_and_https_url(self):
        base = {"max_bot_token": "TEST_TOKEN", "max_transport": "webhook", "max_webhook_url": "https://example.test/webhook/max", "max_webhook_secret": "test_secret_123"}
        for changed in ({"max_webhook_secret": None}, {"max_webhook_secret": "replace_me"}, {"max_webhook_secret": "tiny"}, {"max_webhook_url": None}, {"max_webhook_url": "http://example.test"}, {"max_webhook_url": "https://example.test:8000"}, {"max_webhook_url": "https://example.test/?token=PRIVATE_TOKEN"}):
            with self.subTest(fields=list(changed)), self.assertRaises(ValueError):
                Settings(**(base | changed))
        self.assertTrue(Settings(**base).use_webhook)

    def test_invalid_environment_numbers_and_booleans_do_not_echo_values(self):
        for name in ("MAX_POLLING_LIMIT", "MAX_POLLING_TIMEOUT", "APP_PORT", "HTTPX_TRUST_ENV"):
            with self.subTest(name=name), patch.dict(os.environ, {"MAX_BOT_TOKEN": "TEST_TOKEN", name: "PRIVATE_TOKEN"}, clear=True):
                with self.assertRaises(ValueError) as caught:
                    load_settings()
                self.assertNotIn("PRIVATE_TOKEN", str(caught.exception))

    def test_dotenv_is_read_only_and_does_not_override_environment(self):
        with patch.dict(os.environ, {"MAX_BOT_TOKEN": "TEST_TOKEN"}, clear=True), patch("config.load_dotenv") as loader:
            load_settings()
        self.assertFalse(loader.call_args.kwargs["override"])
        self.assertEqual(loader.call_args.kwargs["dotenv_path"].name, ".env")

    def test_explicit_proxy_setting_takes_precedence_over_legacy_value(self):
        with patch.dict(os.environ, {"MAX_BOT_TOKEN": "TEST_TOKEN", "HTTPX_TRUST_ENV": "false", "MAX_USE_ENV_PROXY": "invalid legacy value"}, clear=True):
            self.assertFalse(load_settings().httpx_trust_env)

    def test_frozen_application_reads_adjacent_configuration(self):
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "test-bot.exe"
            with patch.dict(os.environ, {"MAX_BOT_TOKEN": "TEST_TOKEN"}, clear=True), patch("config.sys.frozen", True, create=True), patch("config.sys.executable", str(executable)), patch("config.load_dotenv") as loader:
                load_settings()
            self.assertEqual(loader.call_args.kwargs["dotenv_path"], executable.parent / ".env")

    def test_httpx_trust_env_is_disabled_by_default(self) -> None:
        with patch.dict(os.environ, {"MAX_BOT_TOKEN": "token"}, clear=True):
            settings = load_settings()

        self.assertFalse(settings.httpx_trust_env)
        self.assertFalse(settings.suppress_polling_network_errors)

    def test_httpx_trust_env_can_be_enabled(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAX_BOT_TOKEN": "token",
                "HTTPX_TRUST_ENV": "true",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertTrue(settings.httpx_trust_env)

    def test_legacy_proxy_setting_still_works(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAX_BOT_TOKEN": "token",
                "MAX_USE_ENV_PROXY": "true",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertTrue(settings.httpx_trust_env)

    def test_suppress_polling_network_errors_can_be_enabled(self) -> None:
        with patch.dict(
            os.environ,
            {
                "MAX_BOT_TOKEN": "token",
                "SUPPRESS_POLLING_NETWORK_ERRORS": "yes",
            },
            clear=True,
        ):
            settings = load_settings()

        self.assertTrue(settings.suppress_polling_network_errors)


if __name__ == "__main__":
    unittest.main()
