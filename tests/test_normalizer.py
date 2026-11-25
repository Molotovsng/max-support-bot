import unittest

from maxbot.normalizer import normalize_update


class NormalizeUpdateTests(unittest.TestCase):
    def test_normalizes_message_created(self) -> None:
        update = {
            "update_type": "message_created",
            "timestamp": 1710000000,
            "chat_id": 10,
            "message": {
                "mid": "m1",
                "sender": {"user_id": 42},
                "body": {"text": "hello"},
                "link": {"type": "reply", "mid": "m0"},
            },
        }

        event = normalize_update(update)

        self.assertEqual(event.update_type, "message_created")
        self.assertEqual(event.timestamp, 1710000000)
        self.assertEqual(event.user_id, 42)
        self.assertEqual(event.chat_id, 10)
        self.assertEqual(event.message_id, "m1")
        self.assertEqual(event.text, "hello")
        self.assertEqual(event.reply_to_message_id, "m0")

    def test_normalizes_callback(self) -> None:
        update = {
            "update_type": "message_callback",
            "timestamp": 1710000001,
            "user": {"user_id": 7},
            "message": {"mid": "m2"},
            "callback": {"callback_id": "cb1", "payload": "start", "user": {"user_id": 7}},
        }

        event = normalize_update(update)

        self.assertEqual(event.timestamp, 1710000001)
        self.assertEqual(event.user_id, 7)
        self.assertEqual(event.message_id, "m2")
        self.assertEqual(event.callback_id, "cb1")
        self.assertEqual(event.callback_payload, "start")

    def test_normalizes_callback_user_from_callback_object(self) -> None:
        update = {
            "update_type": "message_callback",
            "timestamp": 1710000002,
            "message": {"mid": "m3"},
            "callback": {
                "callback_id": "cb2",
                "payload": "demo",
                "user": {"user_id": "9"},
            },
        }

        event = normalize_update(update)

        self.assertEqual(event.user_id, 9)
        self.assertEqual(event.callback_payload, "demo")

    def test_normalizes_body_mid_and_body_reply_to(self) -> None:
        update = {
            "update_type": "message_created",
            "timestamp": 1710000003,
            "message": {
                "sender": {"user_id": 12},
                "recipient": {"chat_id": -100000000001},
                "body": {
                    "mid": "body-mid-1",
                    "text": "reply text",
                    "reply_to": {"mid": "source-mid-1"},
                },
            },
        }

        event = normalize_update(update)

        self.assertEqual(event.message_id, "body-mid-1")
        self.assertEqual(event.reply_to_message_id, "source-mid-1")
        self.assertEqual(event.chat_id, -100000000001)

    def test_normalizes_channel_reply_from_link_message(self) -> None:
        update = {
            "update_type": "message_created",
            "timestamp": 1710000004,
            "message": {
                "recipient": {"chat_id": -100000000001, "chat_type": "channel"},
                "body": {
                    "mid": "reply-mid-1",
                    "text": "Ответ специалиста",
                },
                "link": {
                    "type": "reply",
                    "message": {
                        "mid": "source-mid-2",
                        "text": "ID РїРѕР»СЊР·РѕРІР°С‚РµР»СЏ: 42",
                    },
                },
            },
        }

        event = normalize_update(update)

        self.assertEqual(event.message_id, "reply-mid-1")
        self.assertEqual(event.reply_to_message_id, "source-mid-2")
        self.assertEqual(event.text, "Ответ специалиста")

    def test_callback_uses_clicking_user_instead_of_bot_sender(self):
        event = normalize_update({"update_type": "message_callback", "user": {"user_id": 99}, "callback": {"callback_id": "cb", "payload": "user_type:employee", "user": {"user_id": 42, "is_bot": False}}, "message": {"sender": {"user_id": 999, "is_bot": True}, "recipient": {"chat_id": 777, "chat_type": "dialog"}}})
        self.assertEqual(event.user_id, 42)
        self.assertFalse(event.actor_is_bot)
        self.assertEqual(event.chat_type, "dialog")

    def test_missing_callback_actor_cannot_fall_back_to_other_users(self):
        event = normalize_update({"update_type": "message_callback", "user": {"user_id": 42}, "callback": {"sender": {"user_id": 42}, "callback_id": "cb"}, "message": {"sender": {"user_id": 999}}})
        self.assertIsNone(event.user_id)

    def test_missing_message_sender_cannot_use_top_level_identity(self):
        event = normalize_update({"update_type": "message_created", "user": {"user_id": 42}, "message": {"recipient": {"chat_id": 777, "chat_type": "channel"}, "body": {"text": "reply"}}})
        self.assertIsNone(event.user_id)
        self.assertEqual(event.chat_type, "channel")

    def test_forward_is_not_a_reply_even_with_legacy_reply_fields(self):
        for kind in ("forward", None):
            event = normalize_update({"update_type": "message_created", "message": {"link": {"type": kind, "message": {"mid": "source"}}, "body": {"reply_to": {"mid": "other"}}}})
            self.assertIsNone(event.reply_to_message_id)
            self.assertIsNone(event.reply_type)

    def test_conflicting_chats_and_boolean_id_are_rejected(self):
        event = normalize_update({"update_type": "message_created", "chat_id": 999, "message": {"sender": {"user_id": True}, "recipient": {"chat_id": 777, "chat_type": "dialog"}}})
        self.assertIsNone(event.user_id)
        self.assertIsNone(event.chat_id)
        self.assertIsNone(event.chat_type)

    def test_bot_started_is_private_without_message_recipient(self):
        event = normalize_update({"update_type": "bot_started", "user": {"user_id": 42}, "chat_id": 777})
        self.assertEqual(event.chat_type, "dialog")


if __name__ == "__main__":
    unittest.main()
