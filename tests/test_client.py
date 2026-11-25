import unittest
from unittest.mock import patch

import httpx

from maxbot.client import MaxClient


class MaxClientTests(unittest.IsolatedAsyncioTestCase):
    async def test_tls_context_is_explicit_even_when_environment_proxy_is_enabled(self):
        client = MaxClient("TEST_TOKEN", "https://platform-api2.max.ru", trust_env=True)
        with patch("maxbot.client.httpx.AsyncClient") as constructor:
            client._get_client(httpx.Timeout(30))
        self.assertIs(constructor.call_args.kwargs["verify"], client._ssl_context)
        self.assertTrue(constructor.call_args.kwargs["trust_env"])

    async def test_api_failure_does_not_log_response_recipient_or_token(self):
        token = "TEST_PRIVATE_TOKEN"
        client = MaxClient(token, "https://platform-api2.max.ru")
        def reject(request):
            self.assertEqual(request.headers["Authorization"], token)
            return httpx.Response(403, json={"message": "PRIVATE_APPEAL_TEXT", "token": token})
        client._client = httpx.AsyncClient(transport=httpx.MockTransport(reject))
        try:
            with self.assertLogs("maxbot.client", level="DEBUG") as captured:
                with self.assertRaises(httpx.HTTPStatusError) as caught:
                    await client.send_message(user_id=987654321, text="PRIVATE_APPEAL_TEXT")
            output = " ".join(captured.output) + str(caught.exception)
            for value in (token, "PRIVATE_APPEAL_TEXT", "987654321", "user_id="):
                self.assertNotIn(value, output)
            self.assertEqual(caught.exception.response.status_code, 403)
        finally:
            await client.aclose()
    async def test_client_uses_configured_trust_env_value(self) -> None:
        client = MaxClient("token", "https://platform-api2.max.ru", trust_env=False)

        http_client = client._get_client(httpx.Timeout(30.0))

        self.assertFalse(http_client._trust_env)
        await client.aclose()

    async def test_client_reuses_same_async_client_instance(self) -> None:
        client = MaxClient("token", "https://platform-api2.max.ru", trust_env=False)

        first = client._get_client(httpx.Timeout(30.0))
        second = client._get_client(httpx.Timeout(45.0))

        self.assertIs(first, second)
        self.assertEqual(second.timeout.read, 45.0)
        await client.aclose()


if __name__ == "__main__":
    unittest.main()
