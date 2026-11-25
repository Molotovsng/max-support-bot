from __future__ import annotations

from typing import Any

from maxbot.models import IncomingEvent


def _extract_user_id(container: dict[str, Any] | None) -> int | None:
    if not isinstance(container, dict):
        return None
    for key in ("user_id", "id"):
        value = container.get(key)
        if type(value) is int and value > 0:
            return value
        if isinstance(value, str) and value.isascii() and value.isdecimal() and int(value) > 0:
            return int(value)
    return None


def _extract_text(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None
    body = message.get("body")
    if isinstance(body, dict):
        text = body.get("text")
        if isinstance(text, str):
            return text
    text = message.get("text")
    if isinstance(text, str):
        return text
    return None


def _extract_reply_to(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None
    candidates: list[dict[str, Any]] = []
    link = message.get("link")
    if isinstance(link, dict):
        if link.get("type") != "reply":
            return None
        candidates.append(link)
        linked_message = link.get("message")
        if isinstance(linked_message, dict):
            candidates.append(linked_message)
    body = message.get("body")
    if isinstance(body, dict):
        body_link = body.get("link")
        if isinstance(body_link, dict):
            if body_link.get("type") != "reply":
                return None
            candidates.append(body_link)
            linked_message = body_link.get("message")
            if isinstance(linked_message, dict):
                candidates.append(linked_message)
        reply_to = body.get("reply_to")
        if isinstance(reply_to, dict) and reply_to.get("type", "reply") == "reply":
            candidates.append(reply_to)
    reply_to = message.get("reply_to")
    if isinstance(reply_to, dict) and reply_to.get("type", "reply") == "reply":
        candidates.append(reply_to)
    for candidate in candidates:
        for key in ("mid", "message_id"):
            value = candidate.get(key)
            if isinstance(value, str) and value.strip():
                return value
    return None


def _extract_message_id(message: dict[str, Any] | None) -> str | None:
    if not isinstance(message, dict):
        return None
    for key in ("mid", "message_id"):
        value = message.get(key)
        if isinstance(value, str):
            return value
    body = message.get("body")
    if isinstance(body, dict):
        for key in ("mid", "message_id"):
            value = body.get(key)
            if isinstance(value, str):
                return value
    return None


def normalize_update(update: dict[str, Any]) -> IncomingEvent:
    update_type = update.get("update_type", "")
    if not isinstance(update_type, str):
        update_type = ""
    timestamp = update.get("timestamp")
    if type(timestamp) is not int:
        timestamp = None
    message = update.get("message") if isinstance(update.get("message"), dict) else {}
    callback = update.get("callback") if isinstance(update.get("callback"), dict) else {}
    user = update.get("user") if isinstance(update.get("user"), dict) else {}

    # The actor depends on the event: a callback's message.sender is the bot,
    # and a top-level user must never impersonate a missing message sender.
    if update_type == "bot_started":
        actor = user
    elif update_type == "message_callback":
        actor = callback.get("user")
    else:
        actor = message.get("sender")
    user_id = _extract_user_id(actor)
    actor_is_bot = isinstance(actor, dict) and actor.get("is_bot") is True

    recipient = message.get("recipient")
    recipient = recipient if isinstance(recipient, dict) else {}
    chat_type = recipient.get("chat_type")
    if not isinstance(chat_type, str) or chat_type not in {"dialog", "chat", "channel"}:
        chat_type = None
    # BotStartedUpdate is defined by MAX as the beginning of a private dialog.
    if update_type == "bot_started" and not recipient:
        chat_type = "dialog"
    top_chat = update.get("chat_id")
    top_chat = top_chat if type(top_chat) is int and top_chat != 0 else None
    message_chat = recipient.get("chat_id")
    message_chat = message_chat if type(message_chat) is int and message_chat != 0 else None
    chat_id = message_chat if message_chat is not None else top_chat
    if top_chat is not None and message_chat is not None and top_chat != message_chat:
        chat_id, chat_type = None, None

    message_id = _extract_message_id(message)

    callback_payload = None
    callback_id = None
    if update_type == "message_callback":
        callback_id = callback.get("callback_id")
        if not isinstance(callback_id, str) or not callback_id.strip():
            callback_id = None
        for key in ("payload", "data"):
            value = callback.get(key)
            if isinstance(value, str):
                callback_payload = value
                break

    reply_to = _extract_reply_to(message)

    return IncomingEvent(
        update_type=update_type,
        timestamp=timestamp,
        user_id=user_id,
        chat_id=chat_id,
        message_id=message_id,
        callback_id=callback_id,
        callback_payload=callback_payload,
        text=_extract_text(message),
        reply_to_message_id=reply_to,
        raw=update,
        chat_type=chat_type,
        actor_is_bot=actor_is_bot,
        reply_type="reply" if reply_to else None,
    )
