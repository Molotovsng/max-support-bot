from __future__ import annotations

import logging
from typing import Any

import httpx

from maxbot.tls import build_ssl_context, validate_api_base

logger = logging.getLogger(__name__)


class MaxClient:
    def __init__(self, token: str, base_url: str, *, trust_env: bool = False, root_ca_path: str | None = None) -> None:
        self.base_url = validate_api_base(base_url)
        self.trust_env = trust_env
        self._ssl_context = build_ssl_context(root_ca_path)
        self.headers = {
            "Authorization": token,
            "Content-Type": "application/json",
        }
        self._client: httpx.AsyncClient | None = None

    def _get_client(self, timeout: httpx.Timeout) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=timeout,
                trust_env=self.trust_env,
                verify=self._ssl_context,
            )
        else:
            self._client.timeout = timeout
        return self._client

    async def aclose(self) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
        timeout: int = 30,
    ) -> dict[str, Any]:
        url = f"{self.base_url}{path}"
        client = self._get_client(
            httpx.Timeout(
                connect=10.0,
                read=max(float(timeout) + 15.0, 30.0),
                write=30.0,
                pool=30.0,
            )
        )
        response = await client.request(
            method,
            url,
            headers=self.headers,
            params=params,
            json=json_body,
        )
        if response.status_code >= 400:
            logger.error("MAX API request failed status=%d", response.status_code)
            raise httpx.HTTPStatusError(
                f"MAX API request failed (HTTP {response.status_code})",
                request=response.request, response=response,
            )
        if not response.content:
            return {}
        return response.json()

    async def send_message(
        self,
        *,
        text: str,
        user_id: int | None = None,
        chat_id: int | None = None,
        attachments: list[dict[str, Any]] | None = None,
        notify: bool = True,
        text_format: str = "markdown",
    ) -> dict[str, Any]:
        if user_id is None and chat_id is None:
            raise ValueError("user_id or chat_id is required")
        payload: dict[str, Any] = {
            "text": text,
            "notify": notify,
            "format": text_format,
        }
        if attachments is not None:
            payload["attachments"] = attachments
        params: dict[str, Any] = {}
        if user_id is not None:
            params["user_id"] = user_id
        if chat_id is not None:
            params["chat_id"] = chat_id
        return await self._request("POST", "/messages", params=params, json_body=payload)

    async def edit_message(
        self,
        message_id: str,
        *,
        text: str,
        attachments: list[dict[str, Any]] | None = None,
        text_format: str = "markdown",
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "text": text,
            "format": text_format,
        }
        if attachments is not None:
            payload["attachments"] = attachments
        return await self._request(
            "PUT",
            "/messages",
            params={"message_id": message_id},
            json_body=payload,
        )

    async def answer_callback(
        self,
        callback_id: str,
        *,
        notification: str | None = None,
        text: str | None = None,
        attachments: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {}
        if notification is not None:
            payload["notification"] = notification
        if text is not None or attachments is not None:
            message: dict[str, Any] = {
                "text": text,
                "format": "markdown",
            }
            if attachments is not None:
                message["attachments"] = attachments
            payload["message"] = message
        return await self._request(
            "POST",
            "/answers",
            params={"callback_id": callback_id},
            json_body=payload,
        )

    async def get_message(self, message_id: str) -> dict[str, Any]:
        return await self._request("GET", f"/messages/{message_id}")

    async def get_updates(
        self,
        *,
        marker: int | None,
        limit: int,
        timeout: int,
        types: list[str],
    ) -> dict[str, Any]:
        params: dict[str, Any] = {
            "limit": limit,
            "timeout": timeout,
        }
        if marker is not None:
            params["marker"] = marker
        if types:
            params["types"] = types
        return await self._request("GET", "/updates", params=params, timeout=timeout + 10)

    async def subscribe_webhook(
        self,
        *,
        url: str,
        secret: str | None,
        update_types: list[str],
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "url": url,
            "update_types": update_types,
        }
        if secret:
            payload["secret"] = secret
        return await self._request("POST", "/subscriptions", json_body=payload)
