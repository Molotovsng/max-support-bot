from __future__ import annotations

STATE_SELECT_USER_TYPE = "select_user_type"
STATE_SELECT_CONTACT_MODE = "select_contact_mode"
STATE_WAITING_MESSAGE = "waiting_message"

# Fictional IDs; replace with your own test chat and specialists before connecting.
DESTINATION_CHAT_ID = -100000000001
SPECIALIST_IDS = {
    9001,
}

USER_TYPES = {
    "employee": "Сотрудник",
    "contractor": "Контрагент",
}

CONTACT_MODES = {
    "anonymous": "Анонимное обращение",
    "identified": "Обращение с обратной связью",
}

BUTTON_USER_EMPLOYEE = "Сотрудник"
BUTTON_USER_CONTRACTOR = "Контрагент"
BUTTON_SEND_ANONYMOUS = "Отправить анонимное обращение"
BUTTON_SEND_IDENTIFIED = "Отправить обращение с обратной связью"
BUTTON_BACK_TO_START = "Вернуться в начало"

WELCOME_TEXT = (
    "👋 *Демонстрационная служба поддержки*\n\n"
    "Сюда можно направить вопрос или описать проблему.\n\n"
    "Сначала выберите свою категорию и удобный режим общения.\n\n"
    "Сначала выберите тип пользователя:"
)

USER_TYPE_PROMPT = "Выберите тип пользователя:"

CONTACT_MODE_PROMPT = (
    "Выберите удобный формат обращения:"
)

MESSAGE_PROMPT_ANONYMOUS = (
    "✍️ *Анонимное обращение*\n\n"
    "Опишите ситуацию одним сообщением. "
    "Не указывайте свои данные, если хотите сохранить анонимность."
)

MESSAGE_PROMPT_IDENTIFIED = (
    "✍️ *Обращение с обратной связью*\n\n"
    "Опишите ситуацию одним сообщением. "
    "Специалист сможет ответить вам в этом чате через бота."
)

FALLBACK_TEXT = (
    "Пожалуйста, выберите тип пользователя и формат обращения кнопками ниже.\n"
    "Если кнопки в MAX не срабатывают, отправьте сообщением: "
    f"«{BUTTON_USER_EMPLOYEE}», «{BUTTON_USER_CONTRACTOR}», "
    f"«{BUTTON_SEND_ANONYMOUS}» или «{BUTTON_SEND_IDENTIFIED}»."
)

DELIVERY_SUCCESS_TEXT = (
    "✅ Сообщение отправлено в службу поддержки."
)

SPECIALIST_REPLY_PREFIX = "Ответ специалиста службы поддержки:"

SPECIALIST_INSTRUCTION = (
    "Инструкция для специалиста:\n"
    "Ответьте конкретно на это сообщение, чтобы бот переслал ответ пользователю."
)
