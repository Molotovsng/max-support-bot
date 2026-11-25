import unittest
from unittest.mock import patch

from constants import STATE_SELECT_CONTACT_MODE, STATE_WAITING_MESSAGE
from maxbot.models import IncomingEvent
from maxbot.service import BotService


class DummyClient:
    def __init__(self) -> None:
        self.sent_messages: list[dict] = []
        self.callback_answers: list[dict] = []
        self.source_message_text = "ID пользователя: 42"
        self.next_send_result: dict = {}

    async def send_message(self, **kwargs):
        self.sent_messages.append(kwargs)
        return self.next_send_result

    async def answer_callback(self, callback_id, **kwargs):
        self.callback_answers.append({"callback_id": callback_id, **kwargs})
        return {}

    async def get_message(self, message_id):
        return {"body": {"text": self.source_message_text}}


class DummyRegistry:
    def __init__(self) -> None:
        self.users: set[int] = set()

    def add(self, user_id: int) -> bool:
        is_new = user_id not in self.users
        self.users.add(user_id)
        return is_new


class DummyAppealLinks:
    def __init__(self) -> None:
        self.links: dict[str, int] = {}

    def save_link(self, message_id: str, user_id: int) -> None:
        self.links[message_id] = user_id

    def get_user_id(self, message_id: str) -> int | None:
        return self.links.get(message_id)


class BotServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("maxbot.service.SPECIALIST_IDS", {9001})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_bot_started_sends_greeting(self) -> None:
        client = DummyClient()
        service = BotService(client, DummyRegistry(), DummyAppealLinks())

        event = IncomingEvent(
            update_type="bot_started",
            timestamp=1710000100,
            user_id=42,
            chat_id=777,
            chat_type="dialog",
            raw={},
        )

        await service.handle_update(event)

        self.assertEqual(len(client.sent_messages), 1)
        self.assertEqual(client.sent_messages[0]["chat_id"], 777)

    async def test_user_type_button_switches_to_contact_mode(self) -> None:
        client = DummyClient()
        service = BotService(client, DummyRegistry(), DummyAppealLinks())
        service._reset_user_session(42)

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000200,
            user_id=42,
            chat_id=777,
            chat_type="dialog",
            text="Сотрудник",
            raw={},
        )

        await service.handle_update(event)

        self.assertEqual(service.sessions[42].state, STATE_SELECT_CONTACT_MODE)
        self.assertEqual(service.sessions[42].user_type, "employee")

    async def test_contact_mode_button_switches_to_waiting_message(self) -> None:
        client = DummyClient()
        service = BotService(client, DummyRegistry(), DummyAppealLinks())
        session = service._reset_user_session(42)
        session.user_type = "employee"
        session.state = STATE_SELECT_CONTACT_MODE

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000201,
            user_id=42,
            chat_id=777,
            chat_type="dialog",
            text="Отправить обращение с обратной связью",
            raw={},
        )

        await service.handle_update(event)

        self.assertEqual(service.sessions[42].state, STATE_WAITING_MESSAGE)
        self.assertFalse(service.sessions[42].is_anonymous)

    async def test_message_is_forwarded_without_visible_user_id(self) -> None:
        client = DummyClient()
        client.next_send_result = {"message": {"body": {"mid": "mid-1"}}}
        links = DummyAppealLinks()
        service = BotService(client, DummyRegistry(), links)
        session = service._reset_user_session(42)
        session.is_anonymous = False
        session.user_type = "employee"
        session.state = STATE_WAITING_MESSAGE

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000300,
            user_id=42,
            chat_id=777,
            chat_type="dialog",
            text="Описание ситуации",
            raw={},
        )

        await service.handle_update(event)

        self.assertEqual(client.sent_messages[0]["chat_id"], -100000000001)
        self.assertIn("Тип пользователя: Сотрудник", client.sent_messages[0]["text"])
        self.assertNotIn("Компания: Демо", client.sent_messages[0]["text"])
        self.assertNotIn("Подразделение:", client.sent_messages[0]["text"])
        self.assertNotIn("ID пользователя", client.sent_messages[0]["text"])
        self.assertEqual(links.get_user_id("mid-1"), 42)

    async def test_anonymous_message_does_not_save_reply_link(self) -> None:
        client = DummyClient()
        client.next_send_result = {"message": {"body": {"mid": "mid-2"}}}
        links = DummyAppealLinks()
        service = BotService(client, DummyRegistry(), links)
        session = service._reset_user_session(42)
        session.is_anonymous = True
        session.user_type = "contractor"
        session.state = STATE_WAITING_MESSAGE

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000400,
            user_id=42,
            chat_id=777,
            chat_type="dialog",
            text="Анонимное сообщение",
            raw={},
        )

        await service.handle_update(event)

        self.assertIsNone(links.get_user_id("mid-2"))
        self.assertNotIn("Инструкция для специалиста", client.sent_messages[0]["text"])

    async def test_specialist_reply_reaches_user_by_saved_message_link(self) -> None:
        client = DummyClient()
        links = DummyAppealLinks()
        links.save_link("m1", 42)
        service = BotService(client, DummyRegistry(), links)

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000500,
            user_id=9001,
            chat_id=-100000000001,
            chat_type="chat",
            text="Ответ специалиста",
            reply_to_message_id="m1",
            reply_type="reply",
            raw={
                "message": {
                    "body": {"text": "Ответ специалиста"},
                    "link": {"message": {"mid": "m1", "text": "Исходное обращение"}},
                }
            },
        )

        await service.handle_specialist_reply(event)

        self.assertEqual(client.sent_messages[0]["user_id"], 42)
        self.assertIn("Ответ специалиста службы поддержки", client.sent_messages[0]["text"])

    async def test_service_chat_message_without_reply_is_not_treated_as_specialist_reply(self) -> None:
        client = DummyClient()
        service = BotService(client, DummyRegistry(), DummyAppealLinks())

        event = IncomingEvent(
            update_type="message_created",
            timestamp=1710000600,
            user_id=None,
            chat_id=-100000000001,
            text="Свободный текст",
            raw={},
        )

        self.assertFalse(service._should_handle_as_specialist_reply(event))


if __name__ == "__main__":
    unittest.main()
