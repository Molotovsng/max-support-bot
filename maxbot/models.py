from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class IncomingEvent:
    update_type: str
    timestamp: int | None
    user_id: int | None
    chat_id: int | None
    message_id: str | None = None
    callback_id: str | None = None
    callback_payload: str | None = None
    text: str | None = None
    reply_to_message_id: str | None = None
    raw: dict[str, Any] = field(default_factory=dict)
    chat_type: str | None = None
    actor_is_bot: bool = False
    reply_type: str | None = None


@dataclass(slots=True)
class UserSession:
    user_id: int
    state: str
    company: str | None = None
    user_type: str | None = None
    topic: str | None = None
    is_anonymous: bool = False
    pending_text: str | None = None
