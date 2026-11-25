import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import httpx

from config import Settings
from constants import CONTACT_MODES, DEFAULT_DEPARTMENT_CHAT_IDS, DEPARTMENTS, USER_TYPES
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
                await process_update(service, {"update_type": "message_callback", "callback": {"callback_id": "test-cb", "payload": "department:logistics_security", "user": {"user_id": 42}}, "message": {"sender": {"user_id": 999, "is_bot": True}, "recipient": {"chat_id": 777, "chat_type": "dialog"}}})
                self.assertEqual(paths, ["/answers", "/messages"])
                self.assertEqual(service.sessions[42].department_key, "logistics_security")
                self.assertNotIn(999, service.sessions)
            finally:
                await service.client.aclose()

    async def test_complete_appeal_flow_and_specialist_reply_use_mock_api(self):
        from itertools import product

        for department, user_type, mode in product(DEPARTMENTS, USER_TYPES, CONTACT_MODES):
            with self.subTest(department=department, user_type=user_type, mode=mode), tempfile.TemporaryDirectory() as directory:
                anonymous = mode == "anonymous"
                destination = DEFAULT_DEPARTMENT_CHAT_IDS[department]
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
                    for text in (DEPARTMENTS[department], USER_TYPES[user_type], f"Отправить {CONTACT_MODES[mode].lower()}", "PRIVATE_APPEAL_TEXT"):
                        await process_update(service, {"update_type": "message_created", "message": {"sender": {"user_id": 42}, "recipient": {"chat_id": 777, "chat_type": "dialog"}, "body": {"text": text}}})
                    self.assertEqual(len(sent), 6)
                    self.assertEqual(sent[4]["params"]["chat_id"], str(destination))
                    self.assertIn("PRIVATE_APPEAL_TEXT", sent[4]["body"]["text"])
                    self.assertNotIn("ID пользователя", sent[4]["body"]["text"])
                    self.assertEqual(service.appeal_links.get_user_id(f"{destination}:test-mid-5"), None if anonymous else 42)
                    if not anonymous:
                        await process_update(service, {"update_type": "message_created", "message": {"sender": {"user_id": 9001}, "recipient": {"chat_id": destination, "chat_type": "chat"}, "body": {"text": "PRIVATE_SPECIALIST_REPLY"}, "link": {"type": "reply", "message": {"mid": "test-mid-5"}}}})
                        self.assertEqual(sent[-1]["params"]["user_id"], "42")
                        self.assertIn("PRIVATE_SPECIALIST_REPLY", sent[-1]["body"]["text"])
                finally:
                    await service.client.aclose()
