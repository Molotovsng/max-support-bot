import asyncio
from dataclasses import replace
from pathlib import Path
import tempfile
import unittest
from unittest.mock import AsyncMock, Mock, patch

from constants import BUTTON_USER_EMPLOYEE, DEFAULT_DEPARTMENT_CHAT_IDS, DESTINATION_CHAT_ID, STATE_SELECT_USER_TYPE, STATE_WAITING_MESSAGE
from maxbot.models import IncomingEvent
from maxbot.normalizer import normalize_update
from maxbot.service import BotService
from maxbot.storage import AppealLinkRegistry
from test_service import DummyAppealLinks, DummyClient, DummyRegistry


class RoutingSecurityTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("maxbot.service.SPECIALIST_IDS", {9001})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.client, self.registry, self.links = DummyClient(), DummyRegistry(), DummyAppealLinks()
        self.service = BotService(self.client, self.registry, self.links)
        self.client.get_message = AsyncMock(side_effect=AssertionError("Source text must not determine routing"))

    def private(self, **changes):
        base = IncomingEvent(update_type="message_created", timestamp=None, user_id=42, chat_id=777, chat_type="dialog", text="PRIVATE_TEXT")
        return replace(base, **changes)

    def reply(self, **changes):
        base = IncomingEvent(update_type="message_created", timestamp=None, user_id=9001, chat_id=DESTINATION_CHAT_ID, chat_type="chat", text="PRIVATE_REPLY", reply_to_message_id="appeal-mid", reply_type="reply")
        return replace(base, **changes)

    async def test_only_allowed_specialist_can_use_a_saved_link(self):
        self.links.save_link("appeal-mid", 42)
        for actor in (None, 123, True):
            with self.subTest(actor=actor):
                await self.service.handle_update(self.reply(user_id=actor))
                await self.service.handle_specialist_reply(self.reply(user_id=actor))
        self.assertEqual(self.client.sent_messages, [])
        await self.service.handle_update(self.reply())
        self.assertEqual(self.client.sent_messages[0]["user_id"], 42)
        self.client.get_message.assert_not_awaited()

    async def test_existing_flat_json_registry_is_used_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "appeal_links.json"
            original = b'{"appeal-mid": 42}\n'
            path.write_bytes(original)
            service = BotService(self.client, self.registry, AppealLinkRegistry(str(path)))
            await service.handle_update(self.reply())
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(self.client.sent_messages[0]["user_id"], 42)

    async def test_a_reply_cannot_use_a_link_from_another_department(self):
        chat_id = DEFAULT_DEPARTMENT_CHAT_IDS["store_security"]
        self.links.save_link(f"{chat_id}:appeal-mid", 42)
        await self.service.handle_update(self.reply())
        self.assertTrue(all("user_id" not in item for item in self.client.sent_messages))
        await self.service.handle_update(self.reply(chat_id=chat_id))
        self.assertEqual(self.client.sent_messages[-1]["user_id"], 42)

    async def test_unauthorized_actor_cannot_even_read_routing_registry(self):
        with patch.object(self.links, "get_user_id") as lookup:
            await self.service.handle_specialist_reply(self.reply(user_id=123))
        lookup.assert_not_called()
        self.assertEqual(self.client.sent_messages, [])

    async def test_source_text_and_reply_text_cannot_supply_recipient_id(self):
        for source in ("ID пользователя: 42", "PRIVATE_SOURCE"):
            event = self.reply(text="ID пользователя: 42", raw={"message": {"body": {"text": "ID пользователя: 42"}, "link": {"message": {"text": source}}}})
            await self.service.handle_update(event)
        self.assertTrue(self.client.sent_messages)
        self.assertTrue(all("user_id" not in message for message in self.client.sent_messages))
        self.assertTrue(all(message["chat_id"] == DESTINATION_CHAT_ID for message in self.client.sent_messages))
        self.client.get_message.assert_not_awaited()

    async def test_other_chats_non_replies_and_edited_events_cannot_forward_reply(self):
        self.links.save_link("appeal-mid", 42)
        cases = ({"chat_id": 888}, {"chat_type": "dialog"}, {"reply_type": "forward"}, {"reply_type": None}, {"reply_to_message_id": None}, {"update_type": "message_edited"}, {"actor_is_bot": True})
        for changed in cases:
            with self.subTest(changed=changed):
                await self.service.handle_update(self.reply(**changed))
        self.assertEqual(self.client.sent_messages, [])
        self.assertEqual(self.service.sessions, {})

    async def test_channel_post_without_sender_cannot_impersonate_specialist(self):
        self.links.save_link("appeal-mid", 42)
        raw = {"update_type": "message_created", "user": {"user_id": 9001}, "message": {"recipient": {"chat_id": DESTINATION_CHAT_ID, "chat_type": "channel"}, "body": {"text": "PRIVATE_REPLY"}, "link": {"type": "reply", "message": {"mid": "appeal-mid"}}}}
        await self.service.handle_update(normalize_update(raw))
        self.assertEqual(self.client.sent_messages, [])

    async def test_group_and_unknown_chat_events_do_not_create_sessions(self):
        for kind in ("chat", "channel", None):
            for text in ("/start", BUTTON_USER_EMPLOYEE, "PRIVATE_APPEAL"):
                await self.service.handle_update(self.private(chat_type=kind, text=text))
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.registry.users, set())
        self.assertEqual(self.client.sent_messages, [])

    async def test_service_chat_buttons_and_start_do_not_enter_user_flow(self):
        for kind, text in (("message_created", "/start"), ("message_created", BUTTON_USER_EMPLOYEE), ("bot_started", None)):
            await self.service.handle_update(self.private(update_type=kind, chat_id=DESTINATION_CHAT_ID, text=text))
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.client.sent_messages, [])

    async def test_bot_messages_and_edits_cannot_deliver_a_new_appeal(self):
        session = self.service._session_for(42)
        session.state, session.user_type = STATE_WAITING_MESSAGE, "employee"
        for changed in ({"actor_is_bot": True}, {"update_type": "message_edited"}, {"update_type": "comment_created"}, {"update_type": "unknown"}):
            await self.service.handle_update(self.private(**changed))
        self.assertEqual(self.client.sent_messages, [])
        self.assertEqual(session.state, STATE_WAITING_MESSAGE)

    async def test_whitespace_does_not_crash_command_routing(self):
        await self.service.handle_update(self.private(text="   \n"))
        self.assertEqual(len(self.client.sent_messages), 1)
        self.assertEqual(self.client.sent_messages[0]["chat_id"], 777)

    async def test_invalid_stored_recipient_is_never_used(self):
        for value in (True, 0, -1, "42"):
            self.links.links["appeal-mid"] = value
            await self.service.handle_specialist_reply(self.reply())
        self.assertTrue(all("user_id" not in message for message in self.client.sent_messages))

    async def test_anonymity_uses_mode_at_submission_before_api_await(self):
        for anonymous in (True, False):
            with self.subTest(anonymous=anonymous):
                client, links = DummyClient(), DummyAppealLinks()
                service = BotService(client, DummyRegistry(), links)
                session = service._session_for(42)
                session.department_key = "economic_security"
                session.state, session.user_type, session.is_anonymous = STATE_WAITING_MESSAGE, "employee", anonymous
                async def change_mode_during_send(**kwargs):
                    client.sent_messages.append(kwargs)
                    session.is_anonymous = not anonymous
                    return {"message": {"body": {"mid": "delivered-mid"}}}
                client.send_message = change_mode_during_send
                await service.handle_update(self.private())
                self.assertEqual(links.get_user_id(f"{DESTINATION_CHAT_ID}:delivered-mid"), None if anonymous else 42)

    async def test_callback_uses_actor_and_acknowledges_before_changing_state(self):
        raw = {"update_type": "message_callback", "callback": {"callback_id": "cb", "payload": "department:economic_security", "user": {"user_id": 42}}, "message": {"sender": {"user_id": 999, "is_bot": True}, "recipient": {"chat_id": 777, "chat_type": "dialog"}}}
        await self.service.handle_update(normalize_update(raw))
        self.assertEqual(len(self.client.callback_answers), 1)
        self.assertEqual(self.service.sessions[42].state, STATE_SELECT_USER_TYPE)
        self.assertNotIn(999, self.service.sessions)

    async def test_callback_without_payload_does_not_use_source_message_text(self):
        await self.service.handle_update(self.private(update_type="message_callback", callback_id="cb", text=BUTTON_USER_EMPLOYEE))
        self.assertEqual(len(self.client.callback_answers), 1)
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.client.sent_messages, [])

    async def test_group_and_deleted_source_callbacks_are_acknowledged_without_state_change(self):
        for changed in ({"chat_type": "chat"}, {"chat_type": None, "chat_id": None}):
            await self.service.handle_update(self.private(update_type="message_callback", callback_id="cb", callback_payload="user_type:employee", **changed))
        self.assertEqual(len(self.client.callback_answers), 2)
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.client.sent_messages, [])

    async def test_missing_callback_actor_or_id_cannot_change_state(self):
        for changed in ({"user_id": None}, {"user_id": True}, {"callback_id": None}, {"actor_is_bot": True}):
            event = replace(self.private(update_type="message_callback", callback_id="cb", callback_payload="user_type:employee"), **changed)
            await self.service.handle_update(event)
        self.assertEqual(self.service.sessions, {})
        self.assertEqual(self.client.callback_answers, [])

    async def test_callback_answer_failure_does_not_log_payload_or_lose_button_action(self):
        self.client.answer_callback = AsyncMock(side_effect=RuntimeError("PRIVATE_TOKEN PRIVATE_PAYLOAD"))
        with self.assertLogs("maxbot.service", level="DEBUG") as captured:
            await self.service.handle_update(self.private(update_type="message_callback", callback_id="cb", callback_payload="department:economic_security"))
        self.assertEqual(self.service.sessions[42].state, STATE_SELECT_USER_TYPE)
        self.assertNotIn("PRIVATE_", " ".join(captured.output))

    async def test_forwarded_message_with_registered_mid_cannot_trigger_reply(self):
        self.links.save_link("appeal-mid", 42)
        event = normalize_update({"update_type": "message_created", "message": {"sender": {"user_id": 9001}, "recipient": {"chat_id": DESTINATION_CHAT_ID, "chat_type": "chat"}, "body": {"text": "PRIVATE_REPLY"}, "link": {"type": "forward", "message": {"mid": "appeal-mid"}}}})
        await self.service.handle_update(event)
        self.assertEqual(self.client.sent_messages, [])
