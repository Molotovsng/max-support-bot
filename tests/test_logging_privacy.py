import logging
import sys
import unittest
from unittest.mock import patch

from constants import DESTINATION_CHAT_ID, STATE_WAITING_MESSAGE
from maxbot.logging_utils import PrivateExceptionFormatter
from maxbot.models import IncomingEvent
from maxbot.service import BotService
from test_service import DummyAppealLinks, DummyClient, DummyRegistry


class PrivacyTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("maxbot.service.SPECIALIST_IDS", {9001})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_appeals_never_log_text_identifiers_or_api_responses(self):
        for anonymous in (True, False):
            client = DummyClient()
            client.next_send_result = {"message": {"body": {"mid": "PRIVATE_MESSAGE_ID", "text": "PRIVATE_APPEAL_TEXT"}}}
            links = DummyAppealLinks()
            service = BotService(client, DummyRegistry(), links)
            session = service._session_for(987654321)
            session.state, session.user_type, session.is_anonymous = STATE_WAITING_MESSAGE, "employee", anonymous
            event = IncomingEvent(update_type="message_created", timestamp=123456789, user_id=987654321, chat_id=876543210, chat_type="dialog", text="PRIVATE_APPEAL_TEXT", raw={"PRIVATE_RAW": "PRIVATE_TOKEN"})
            with self.assertLogs("maxbot.service", level="DEBUG") as captured:
                await service.handle_update(event)
            output = " ".join(captured.output)
            for sensitive in ("PRIVATE_", "987654321", "876543210", "123456789", str(DESTINATION_CHAT_ID)):
                self.assertNotIn(sensitive, output)
            self.assertEqual(links.get_user_id("PRIVATE_MESSAGE_ID"), None if anonymous else 987654321)

    async def test_unknown_events_and_callbacks_do_not_log_payloads(self):
        service = BotService(DummyClient(), DummyRegistry(), DummyAppealLinks())
        for kind in ("PRIVATE_UNKNOWN_TYPE", "message_callback"):
            event = IncomingEvent(update_type=kind, timestamp=None, user_id=987654321, chat_id=7, callback_payload="PRIVATE_CALLBACK", raw={"PRIVATE_RAW": "PRIVATE_TOKEN"})
            with self.assertLogs("maxbot.service", level="DEBUG") as captured:
                await service.handle_update(event)
            self.assertNotIn("PRIVATE_", " ".join(captured.output))
            self.assertNotIn("987654321", " ".join(captured.output))

    async def test_saved_reply_does_not_load_or_log_source_message(self):
        client = DummyClient()
        async def fail(_):
            raise RuntimeError("PRIVATE_TOKEN PRIVATE_APPEAL_TEXT")
        client.get_message = fail
        links = DummyAppealLinks()
        links.save_link("PRIVATE_SOURCE_ID", 987654321)
        service = BotService(client, DummyRegistry(), links)
        event = IncomingEvent(update_type="message_created", timestamp=None, user_id=9001, chat_id=DESTINATION_CHAT_ID, chat_type="chat", text="PRIVATE_REPLY", reply_type="reply", reply_to_message_id="PRIVATE_SOURCE_ID", raw={"message": {"body": {"text": "PRIVATE_REPLY"}, "link": {"message": {"text": "PRIVATE_SOURCE_TEXT"}}}})
        with self.assertLogs("maxbot.service", level="DEBUG") as captured:
            await service.handle_update(event)
        self.assertNotIn("PRIVATE_", " ".join(captured.output))
        self.assertNotIn("9001", " ".join(captured.output))
        self.assertEqual(client.sent_messages[0]["user_id"], 987654321)

    def test_exception_formatter_removes_cached_traceback_and_chained_values(self):
        try:
            raise RuntimeError("PRIVATE_EXCEPTION_VALUE")
        except RuntimeError:
            record = logging.LogRecord("test", logging.ERROR, __file__, 1, "Safe error", (), sys.exc_info())
        logging.Formatter().format(record)
        self.assertIn("PRIVATE_EXCEPTION_VALUE", record.exc_text)
        output = PrivateExceptionFormatter().format(record)
        self.assertNotIn("PRIVATE_EXCEPTION_VALUE", output)
        self.assertIn("RuntimeError", output)
