from __future__ import annotations

import logging
from copy import copy


_INFO_EVENTS = {
    (name, message): text
    for name, message, text in (
        ("main", "MAX bot started in polling mode", "Бот запущен (polling)"),
        ("main", "MAX bot started in webhook mode", "Бот запущен (webhook)"),
        ("__main__", "MAX bot started in polling mode", "Бот запущен (polling)"),
        ("__main__", "MAX bot started in webhook mode", "Бот запущен (webhook)"),
        ("maxbot.service", "Appeal delivered to specialist chat", "Обращение отправлено"),
        ("maxbot.service", "Specialist reply delivered to user", "Ответ на обращение отправлен"),
    )
}
_NETWORK_ERRORS = {
    "Polling proxy error, retrying in 15 seconds": "Ошибка прокси при получении обновлений",
    "Polling timeout, retrying in 5 seconds": "Тайм-аут получения обновлений",
    "Polling network error, retrying in 10 seconds": "Ошибка сети при получении обновлений",
}
_ERROR_EVENTS = {
    "Failed to process update": "Ошибка обработки обращения",
    "Failed to subscribe webhook": "Ошибка регистрации webhook",
    "Polling iteration failed": "Ошибка получения обновлений",
    "Polling HTTP error": "Ошибка запроса к MAX API",
    "Failed to answer callback": "Ошибка подтверждения кнопки",
    "Bot stopped; check configuration and required files": "Бот остановлен. Проверьте настройки и файлы приложения",
}


def _event_text(record: logging.LogRecord) -> str | None:
    message = getattr(record, "safe_event", record.msg)
    message = message if isinstance(message, str) else ""
    if record.levelno == logging.INFO:
        return _INFO_EVENTS.get((record.name, message))
    if record.name in {"main", "__main__"} and record.levelno == logging.WARNING:
        return _NETWORK_ERRORS.get(message)
    if record.levelno >= logging.ERROR:
        if record.name == "maxbot.client" or record.name.startswith(("httpx", "httpcore")):
            return "Ошибка запроса к MAX API"
        return _NETWORK_ERRORS.get(message) or _ERROR_EVENTS.get(message, "Ошибка в работе бота")
    return None


def _error_type(record: logging.LogRecord) -> str | None:
    if record.exc_info and record.exc_info[0]:
        return record.exc_info[0].__name__
    if isinstance(record.args, tuple):
        for value in record.args:
            if isinstance(value, BaseException):
                return type(value).__name__
    value = getattr(record, "safe_error_type", None)
    return value if isinstance(value, str) and value.isidentifier() and len(value) <= 128 else None


class RuntimeEventFilter(logging.Filter):
    """Keep only startup, successful deliveries and errors, for every handler."""

    def filter(self, record: logging.LogRecord) -> bool:
        return _event_text(record) is not None


class RuntimeEventFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        safe = copy(record)
        safe.msg = _event_text(record) or "Служебное событие"
        if record.levelno >= logging.WARNING:
            error_type = _error_type(record)
            if error_type:
                safe.msg += f" ({error_type})"
            safe.levelno, safe.levelname = logging.ERROR, "ERROR"
        safe.args = ()
        safe.exc_info = safe.exc_text = safe.stack_info = None
        return super().format(safe)


class PrivateExceptionFormatter(logging.Formatter):
    """Exception values, chained exceptions and source lines may contain user data."""

    def format(self, record: logging.LogRecord) -> str:
        # Another handler may already have cached a full traceback on this record.
        private_record = copy(record)
        private_record.exc_text = None
        return super().format(private_record)

    def formatException(self, exc_info) -> str:
        return f"Exception type: {exc_info[0].__name__} (details omitted)"

    def formatStack(self, stack_info: str) -> str:
        return "Stack details omitted"


def log_failure(logger: logging.Logger, message: str, exc: Exception) -> None:
    """Call only with a static message; never log the exception value or payload."""
    error_type = type(exc).__name__
    logger.error("%s (error_type=%s)", message, error_type, extra={"safe_event": message, "safe_error_type": error_type})

