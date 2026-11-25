from __future__ import annotations

STATE_SELECT_DEPARTMENT = "select_department"
STATE_SELECT_USER_TYPE = "select_user_type"
STATE_SELECT_CONTACT_MODE = "select_contact_mode"
STATE_WAITING_MESSAGE = "waiting_message"

# Fictional fixtures; configure real test chats and specialists in .env.
DEPARTMENTS = {
    "economic_security": "Экономическая безопасность",
    "store_security": "Безопасность магазинов",
    "logistics_security": "Безопасность складов и логистики",
    "information_security": "Информационная безопасность",
    "security_management": "Руководство службы безопасности",
}
DEFAULT_DEPARTMENT_CHAT_IDS = dict(zip(DEPARTMENTS, range(-100000000001, -100000000006, -1)))
DESTINATION_CHAT_ID = DEFAULT_DEPARTMENT_CHAT_IDS["economic_security"]
SPECIALIST_IDS = {
    9001,
}

USER_TYPES = {
    "employee": "Сотрудник",
    "contractor": "Контрагент",
    "individual": "Частное лицо",
}

CONTACT_MODES = {
    "anonymous": "Анонимное обращение",
    "identified": "Обращение с обратной связью",
}

BUTTON_USER_EMPLOYEE = "Сотрудник"
BUTTON_USER_CONTRACTOR = "Контрагент"
BUTTON_USER_INDIVIDUAL = "Частное лицо"
BUTTON_SEND_ANONYMOUS = "Отправить анонимное обращение"
BUTTON_SEND_IDENTIFIED = "Отправить обращение с обратной связью"
BUTTON_BACK_TO_START = "Вернуться в начало"

WELCOME_TEXT = (
    "*Приём обращений в службу безопасности*\n\n"
    "Выберите направление, в которое хотите отправить обращение."
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

FALLBACK_TEXT = "Продолжите с помощью кнопок ниже. Название кнопки можно отправить текстом."

DELIVERY_SUCCESS_TEXT = (
    "✅ Сообщение отправлено в службу поддержки."
)

SPECIALIST_REPLY_PREFIX = "Ответ специалиста службы поддержки:"

SPECIALIST_INSTRUCTION = (
    "Инструкция для специалиста:\n"
    "Ответьте конкретно на это сообщение, чтобы бот переслал ответ пользователю."
)
