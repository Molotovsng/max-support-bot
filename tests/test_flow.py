import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from config import Settings
from constants import BUTTON_SEND_ANONYMOUS, BUTTON_SEND_IDENTIFIED, BUTTON_USER_EMPLOYEE, DESTINATION_CHAT_ID
from main import build_service, process_update


class ExistingFlowTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        patcher = patch("maxbot.service.SPECIALIST_IDS", {9001})
        patcher.start()
        self.addCleanup(patcher.stop)

    async def test_callback_is_answered_via_official_endpoint_for_clicking_user(self):
        with tempfile.TemporaryDirectory() as directory:
            service = build_service(Settings(max_bot_token="TEST_TOKEN", users_file=str(Path(directory) / "bot_users.json")))
            paths = []
            def api(request):
                paths.append(request.url.path)
                self.assertEqual(request.headers["Authorization"], "TEST_TOKEN")
                self.assertEqual(request.method, "POST")
                if request.url.path == "/answers":
                    self.assertEqual(request.url.params["callback_id"], "test-cb")
                    self.assertIn("notification", json.loads(request.content))
                    return httpx.Response(200, json={"success": True})
                self.assertEqual(request.url.path, "/messages")
                self.assertEqual(request.url.params["chat_id"], "777")
                return httpx.Response(200, json={"message": {"body": {"mid": "test-mid"}}})
            service.client._client = httpx.AsyncClient(transport=httpx.MockTransport(api), trust_env=False)
            try:
                await process_update(service, {"update_type": "message_callback", "callback": {"callback_id": "test-cb", "payload": "user_type:employee", "user": {"user_id": 42}}, "message": {"sender": {"user_id": 999, "is_bot": True}, "recipient": {"chat_id": 777, "chat_type": "dialog"}}})
                self.assertEqual(paths, ["/answers", "/messages"])
                self.assertEqual(service.sessions[42].user_type, "employee")
                self.assertNotIn(999, service.sessions)
            finally:
                await service.client.aclose()

    async def test_complete_appeal_flow_and_specialist_reply_use_mock_api(self):
        for anonymous in (True, False):
            with self.subTest(anonymous=anonymous), tempfile.TemporaryDirectory() as directory:
                service = build_service(Settings(max_bot_token="TEST_TOKEN", users_file=str(Path(directory) / "bot_users.json")))
                sent = []
                def api(request):
                    self.assertEqual(request.headers["Authorization"], "TEST_TOKEN")
                    self.assertEqual(request.method, "POST")
                    body = json.loads(request.content)
                    sent.append({"params": dict(request.url.params), "body": body})
                    return httpx.Response(200, json={"message": {"body": {"mid": f"test-mid-{len(sent)}", "text": body["text"]}}})
                service.client._client = httpx.AsyncClient(transport=httpx.MockTransport(api), trust_env=False)
                try:
                    await process_update(service, {"update_type": "bot_started", "timestamp": 1, "user": {"user_id": 42}, "chat_id": 777})
                    for text in (BUTTON_USER_EMPLOYEE, BUTTON_SEND_ANONYMOUS if anonymous else BUTTON_SEND_IDENTIFIED, "PRIVATE_APPEAL_TEXT"):
                        await process_update(service, {"update_type": "message_created", "message": {"sender": {"user_id": 42}, "recipient": {"chat_id": 777, "chat_type": "dialog"}, "body": {"text": text}}})
                    self.assertEqual(len(sent), 5)
                    self.assertEqual(sent[3]["params"]["chat_id"], str(DESTINATION_CHAT_ID))
                    self.assertIn("PRIVATE_APPEAL_TEXT", sent[3]["body"]["text"])
                    self.assertNotIn("ID пользователя", sent[3]["body"]["text"])
                    self.assertEqual(service.appeal_links.get_user_id("test-mid-4"), None if anonymous else 42)
                    if not anonymous:
                        await process_update(service, {"update_type": "message_created", "message": {"sender": {"user_id": 9001}, "recipient": {"chat_id": DESTINATION_CHAT_ID, "chat_type": "chat"}, "body": {"text": "PRIVATE_SPECIALIST_REPLY"}, "link": {"type": "reply", "message": {"mid": "test-mid-4"}}}})
                        self.assertEqual(sent[-1]["params"]["user_id"], "42")
                        self.assertIn("PRIVATE_SPECIALIST_REPLY", sent[-1]["body"]["text"])
                finally:
                    await service.client.aclose()
