from __future__ import annotations

import logging
import time
from typing import Any

from constants import (
    BUTTON_BACK_TO_START,
    BUTTON_SEND_ANONYMOUS,
    BUTTON_SEND_IDENTIFIED,
    BUTTON_USER_CONTRACTOR,
    BUTTON_USER_EMPLOYEE,
    BUTTON_USER_INDIVIDUAL,
    CONTACT_MODE_PROMPT,
    CONTACT_MODES,
    DELIVERY_SUCCESS_TEXT,
    DEFAULT_DEPARTMENT_CHAT_IDS,
    DEPARTMENTS,
    FALLBACK_TEXT,
    MESSAGE_PROMPT_ANONYMOUS,
    MESSAGE_PROMPT_IDENTIFIED,
    SPECIALIST_INSTRUCTION,
    SPECIALIST_IDS,
    SPECIALIST_REPLY_PREFIX,
    STATE_SELECT_CONTACT_MODE,
    STATE_SELECT_DEPARTMENT,
    STATE_SELECT_USER_TYPE,
    STATE_WAITING_MESSAGE,
    USER_TYPES,
    USER_TYPE_PROMPT,
    WELCOME_TEXT,
)
from maxbot.keyboards import back_to_menu_keyboard, contact_mode_keyboard, department_keyboard, user_type_keyboard
from maxbot.callbacks import CallbackResponder
from maxbot.models import IncomingEvent, UserSession
from maxbot.logging_utils import log_failure
from maxbot.storage import AppealLinkRegistry, UserRegistry

logger = logging.getLogger(__name__)


def _normalize_button_text(text: str) -> str:
    return " ".join(text.strip().casefold().split())


BUTTON_TEXT_TO_PAYLOAD = {
    **{_normalize_button_text(label): f"department:{key}" for key, label in DEPARTMENTS.items()},
    _normalize_button_text(BUTTON_USER_EMPLOYEE): "user_type:employee",
    _normalize_button_text(BUTTON_USER_CONTRACTOR): "user_type:contractor",
    _normalize_button_text(BUTTON_USER_INDIVIDUAL): "user_type:individual",
    _normalize_button_text(BUTTON_SEND_ANONYMOUS): "contact_mode:anonymous",
    _normalize_button_text(BUTTON_SEND_IDENTIFIED): "contact_mode:identified",
    _normalize_button_text(BUTTON_BACK_TO_START): "menu:main",
}


class BotService:
    def __init__(
        self, client: Any, user_registry: UserRegistry, appeal_links: AppealLinkRegistry,
        *, department_chat_ids: dict[str, int] | None = None,
        department_contacts: dict[str, str] | None = None, specialist_ids: set[int] | None = None,
    ) -> None:
        self.client = client
        self.user_registry = user_registry
        self.appeal_links = appeal_links
        self.department_chat_ids = dict(department_chat_ids or DEFAULT_DEPARTMENT_CHAT_IDS)
        self.department_contacts = dict(department_contacts or {})
        self.service_chat_ids = set(self.department_chat_ids.values())
        self.specialist_ids = SPECIALIST_IDS if specialist_ids is None else specialist_ids
        self.sessions: dict[int, UserSession] = {}
        self._last_start_at: dict[int, float] = {}
        self._processed_start_events: set[tuple[Any, ...]] = set()
        self._callback_responder = CallbackResponder()

    def _session_for(self, user_id: int) -> UserSession:
        return self.sessions.setdefault(
            user_id,
            UserSession(user_id=user_id, state=STATE_SELECT_DEPARTMENT),
        )

    def _reset_user_session(self, user_id: int) -> UserSession:
        if self.user_registry.add(user_id):
            logger.info("User registered")
        session = UserSession(user_id=user_id, state=STATE_SELECT_DEPARTMENT)
        self.sessions[user_id] = session
        return session

    def _message_target(self, event: IncomingEvent) -> tuple[str, int]:
        if event.chat_id is not None:
            return "chat", event.chat_id
        if event.user_id is not None:
            return "user", event.user_id
        raise ValueError("Event does not contain chat_id or user_id")

    def _start_event_key(self, event: IncomingEvent) -> tuple[Any, ...]:
        return (
            event.update_type,
            event.timestamp,
            event.user_id,
            event.chat_id,
            event.message_id,
            event.text,
            event.callback_payload,
        )

    def _is_duplicate_start_event(self, event: IncomingEvent) -> bool:
        key = self._start_event_key(event)
        if key in self._processed_start_events:
            return True
        self._processed_start_events.add(key)
        return False

    def _should_skip_duplicate_start(self, user_id: int, cooldown_seconds: float = 3.0) -> bool:
        now = time.monotonic()
        last_seen = self._last_start_at.get(user_id)
        self._last_start_at[user_id] = now
        return last_seen is not None and (now - last_seen) < cooldown_seconds

    def _payload_from_event(self, event: IncomingEvent) -> str | None:
        if event.update_type == "message_callback":
            return event.callback_payload
        if event.text:
            return BUTTON_TEXT_TO_PAYLOAD.get(_normalize_button_text(event.text))
        return None

    def _is_start_command(self, text: str | None) -> bool:
        if not text or not text.strip():
            return False
        command = text.strip().split(maxsplit=1)[0].lower()
        return command == "/start" or command.startswith("/start@")

    def _is_service_chat(self, chat_id: int | None) -> bool:
        return chat_id in self.service_chat_ids

    def _is_private_event(self, event: IncomingEvent) -> bool:
        return (
            event.chat_type == "dialog"
            and type(event.user_id) is int and event.user_id > 0
            and not event.actor_is_bot
            and not self._is_service_chat(event.chat_id)
        )

    def _should_handle_as_specialist_reply(self, event: IncomingEvent) -> bool:
        return (
            event.update_type == "message_created"
            and self._is_service_chat(event.chat_id)
            and event.chat_type in ("chat", "channel")
            and type(event.user_id) is int and event.user_id in self.specialist_ids
            and not event.actor_is_bot
            and event.reply_type == "reply"
            and bool(event.reply_to_message_id)
            and bool((event.text or "").strip())
        )

    def _message_prompt(self, session: UserSession) -> str:
        return MESSAGE_PROMPT_ANONYMOUS if session.is_anonymous else MESSAGE_PROMPT_IDENTIFIED

    def _keyboard_for_state(self, state: str) -> list[dict[str, Any]]:
        if state == STATE_SELECT_DEPARTMENT:
            return department_keyboard()
        if state == STATE_SELECT_USER_TYPE:
            return user_type_keyboard()
        if state == STATE_SELECT_CONTACT_MODE:
            return contact_mode_keyboard()
        return back_to_menu_keyboard()

    def _extract_sent_message_id(self, response: dict[str, Any]) -> str | None:
        message = response.get("message")
        if not isinstance(message, dict):
            return None
        body = message.get("body")
        if isinstance(body, dict):
            mid = body.get("mid")
            if isinstance(mid, str):
                return mid
        mid = message.get("mid")
        if isinstance(mid, str):
            return mid
        return None

    async def _send_to_event(
        self,
        event: IncomingEvent,
        text: str,
        *,
        attachments: list[dict[str, Any]] | None = None,
    ) -> None:
        target_type, target_id = self._message_target(event)
        if target_type == "user":
            await self.client.send_message(user_id=target_id, text=text, attachments=attachments)
        else:
            await self.client.send_message(chat_id=target_id, text=text, attachments=attachments)

    async def handle_update(self, event: IncomingEvent) -> None:
        logger.info("Update received")
        if event.update_type not in {"bot_started", "message_callback", "message_created"}:
            logger.info("Update type has no dedicated handler")
            return
        if event.update_type == "message_callback":
            await self.handle_callback(event)
            return
        if self._is_service_chat(event.chat_id):
            if self._should_handle_as_specialist_reply(event):
                logger.info("Routing specialist reply")
                await self.handle_specialist_reply(event)
            else:
                logger.info("Service chat event ignored")
            return
        if not self._is_private_event(event):
            logger.info("Event outside private dialog ignored")
            return
        if event.update_type == "bot_started" or self._is_start_command(event.text):
            await self.handle_start(event)
            return
        await self.handle_message(event)

    async def handle_start(self, event: IncomingEvent) -> None:
        if not self._is_private_event(event):
            return
        if self._is_duplicate_start_event(event):
            logger.info("Skipping duplicate start event")
            return
        if self._should_skip_duplicate_start(event.user_id):
            logger.info("Skipping repeated start")
            return
        self._reset_user_session(event.user_id)
        await self._send_to_event(event, WELCOME_TEXT, attachments=department_keyboard())

    async def handle_callback(self, event: IncomingEvent) -> None:
        if (
            event.update_type != "message_callback"
            or type(event.user_id) is not int or event.user_id <= 0
            or event.actor_is_bot or not event.callback_id
        ):
            return
        private = self._is_private_event(event)
        if event.callback_id:
            key = ("dialog", event.user_id) if private or event.chat_id is None else ("chat", event.chat_id)
            try:
                await self._callback_responder.answer(
                    self.client, key, event.callback_id,
                    "Действие принято" if private else "Используйте кнопки в личном диалоге с ботом.",
                )
            except Exception as exc:
                log_failure(logger, "Failed to answer callback", exc)
        if not private:
            logger.info("Callback outside private dialog ignored")
            return
        payload = self._payload_from_event(event)
        logger.info("Button callback received")
        if payload:
            await self._handle_payload(event, payload)

    async def handle_message(self, event: IncomingEvent) -> None:
        if not self._is_private_event(event) or not event.text:
            return
        payload = self._payload_from_event(event)
        if payload:
            logger.info("Button message received")
            await self._handle_payload(event, payload)
            return

        session = self._session_for(event.user_id)
        if session.state == STATE_WAITING_MESSAGE:
            await self._deliver_user_message(event, session, event.text.strip())
            return

        await self._send_to_event(event, FALLBACK_TEXT, attachments=self._keyboard_for_state(session.state))

    async def _handle_payload(self, event: IncomingEvent, payload: str) -> None:
        if not self._is_private_event(event):
            return
        session = self._session_for(event.user_id)
        logger.info("Processing button action")

        action, _, value = payload.partition(":")
        if payload == "menu:main":
            self._reset_user_session(event.user_id)
            await self._send_to_event(event, WELCOME_TEXT, attachments=department_keyboard())
            return

        if action == "department" and value in self.department_chat_ids:
            session = self._reset_user_session(event.user_id)
            session.department_key = value
            session.user_type = None
            session.state = STATE_SELECT_USER_TYPE
            selection = f"Выбрано направление: {DEPARTMENTS[value]}"
            if contact := self.department_contacts.get(value):
                selection += f"\nКонтакт подразделения: {contact}"
            await self._send_to_event(event, f"{selection}\n\n{USER_TYPE_PROMPT}", attachments=user_type_keyboard())
            return

        if action == "user_type" and value in USER_TYPES and session.state == STATE_SELECT_USER_TYPE:
            session.user_type = value
            session.state = STATE_SELECT_CONTACT_MODE
            await self._send_to_event(
                event,
                f"Выбрано: {USER_TYPES[value]}\n\n{CONTACT_MODE_PROMPT}",
                attachments=contact_mode_keyboard(),
            )
            return

        if action == "contact_mode" and value in CONTACT_MODES and session.state == STATE_SELECT_CONTACT_MODE:
            session.pending_text = None
            session.is_anonymous = value == "anonymous"
            session.state = STATE_WAITING_MESSAGE
            await self._send_to_event(
                event,
                f"{self._message_prompt(session)}\n\nДля возврата в начало отправьте: {BUTTON_BACK_TO_START}",
                attachments=back_to_menu_keyboard(),
            )
            return

        await self._send_to_event(event, FALLBACK_TEXT, attachments=self._keyboard_for_state(session.state))

    def _format_specialist_message(self, session: UserSession, message_text: str) -> str:
        anonymous_text = "Да" if session.is_anonymous else "Нет"
        parts = [
            "Новое обращение в службу поддержки",
            f"Подразделение: {DEPARTMENTS[session.department_key]}",
            "",
            f"Тип пользователя: {USER_TYPES.get(session.user_type or 'employee', 'Сотрудник')}",
            f"Анонимно: {anonymous_text}",
            "",
            "Текст обращения:",
            message_text,
        ]
        if not session.is_anonymous:
            parts.extend(["", SPECIALIST_INSTRUCTION])
        return "\n".join(parts)

    async def _deliver_user_message(self, event: IncomingEvent, session: UserSession, message_text: str) -> None:
        if not self._is_private_event(event) or session.department_key not in self.department_chat_ids:
            return
        # Do not re-read a mutable mode after an API await: another event may
        # change the session while this particular appeal is being delivered.
        anonymous = session.is_anonymous
        text = self._format_specialist_message(session, message_text)
        chat_id = self.department_chat_ids[session.department_key]
        result = await self.client.send_message(chat_id=chat_id, text=text)
        if not anonymous:
            sent_message_id = self._extract_sent_message_id(result)
            if sent_message_id:
                self.appeal_links.save_link(f"{chat_id}:{sent_message_id}", event.user_id)
        logger.info("Appeal delivered to specialist chat")
        if self.sessions.get(event.user_id) is session:
            self._reset_user_session(event.user_id)
        await self._send_to_event(event, DELIVERY_SUCCESS_TEXT, attachments=department_keyboard())

    async def handle_specialist_reply(self, event: IncomingEvent) -> None:
        # Repeat authorization here so direct handler calls cannot bypass it.
        if not self._should_handle_as_specialist_reply(event):
            logger.info("Specialist reply rejected")
            return
        logger.info("Processing specialist reply")

        # Only this local registry, populated after an identified appeal is sent,
        # authorizes delivery. Message bodies and quoted messages are untrusted.
        user_id = self.appeal_links.get_user_id(f"{event.chat_id}:{event.reply_to_message_id}")
        if user_id is None and event.chat_id == self.department_chat_ids["economic_security"]:
            # Legacy single-chat releases saved unscoped links in the first chat.
            user_id = self.appeal_links.get_user_id(event.reply_to_message_id)
        if type(user_id) is not int or user_id <= 0:
            await self._send_to_event(
                event,
                "Ответ не отправлен. Выберите исходное обращение с обратной связью.",
            )
            return

        reply_text = event.text.strip()
        await self.client.send_message(
            user_id=user_id,
            text=f"{SPECIALIST_REPLY_PREFIX}\n\n{reply_text}",
        )
        logger.info("Specialist reply delivered")
