from __future__ import annotations

import logging
from copy import copy


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
    logger.error("%s (error_type=%s)", message, type(exc).__name__)
