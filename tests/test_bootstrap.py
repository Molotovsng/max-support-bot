import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import bootstrap


class ExecutableEntryTests(unittest.TestCase):
    def test_offline_check_does_not_read_config_use_network_or_write_data(self):
        with tempfile.TemporaryDirectory() as directory:
            previous = Path.cwd()
            try:
                os.chdir(directory)
                Path(".env").write_text("MAX_BOT_TOKEN=PRIVATE_SENTINEL\nMAX_API_BASE=invalid\n")
                Path("bot_users.json").write_text("[42]")
                original = {p.name: p.read_bytes() for p in Path.cwd().iterdir()}
                output = io.StringIO()
                with patch("main.main", side_effect=AssertionError("Must not start")), patch("config.load_settings", side_effect=AssertionError("Must not read config")), patch("dotenv.load_dotenv", side_effect=AssertionError("Must not read dotenv")), patch("socket.create_connection", side_effect=AssertionError("Must not connect")), contextlib.redirect_stdout(output):
                    result = bootstrap.main(["--check"])
                self.assertEqual(result, 0)
                self.assertEqual(json.loads(output.getvalue())["bot_started"], False)
                self.assertNotIn("PRIVATE_SENTINEL", output.getvalue())
                self.assertEqual(original, {p.name: p.read_bytes() for p in Path.cwd().iterdir()})
            finally:
                os.chdir(previous)

    def test_frozen_launch_uses_executable_directory_and_restores_cwd(self):
        previous = Path.cwd()
        with tempfile.TemporaryDirectory() as directory:
            expected = Path(directory).resolve()
            with patch("bootstrap.sys.frozen", True, create=True), patch("bootstrap.sys.executable", str(expected / "max-support-bot.exe")), patch("main.main", side_effect=lambda: self.assertEqual(Path.cwd(), expected)) as start:
                self.assertEqual(bootstrap.main([]), 0)
            start.assert_called_once()
        self.assertEqual(Path.cwd(), previous)

    def test_start_failure_does_not_echo_exception_details(self):
        output = io.StringIO()
        with patch("main.main", side_effect=RuntimeError("PRIVATE_SENTINEL")), self.assertLogs("bootstrap", level="ERROR") as captured, contextlib.redirect_stderr(output):
            result = bootstrap.main([])
        self.assertEqual(result, 1)
        self.assertNotIn("PRIVATE_SENTINEL", output.getvalue() + " ".join(captured.output))

    def test_unknown_arguments_do_not_echo_secret_values_or_start_bot(self):
        output = io.StringIO()
        with patch("main.main") as start, contextlib.redirect_stderr(output):
            self.assertEqual(bootstrap.main(["--token", "PRIVATE_SENTINEL"]), 2)
        self.assertNotIn("PRIVATE_SENTINEL", output.getvalue())
        start.assert_not_called()
