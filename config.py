from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from constants import DEFAULT_DEPARTMENT_CHAT_IDS, DEPARTMENTS
from maxbot.tls import DEFAULT_API_BASE, validate_api_base


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "y", "on"}:
        return True
    if normalized in {"0", "false", "no", "n", "off"}:
        return False
    raise ValueError(f"{name} must be a boolean")


def _env_int(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except ValueError:
        raise ValueError(f"{name} must be an integer") from None


@dataclass(slots=True)
class Settings:
    max_bot_token: str = field(repr=False)
    max_api_base: str = DEFAULT_API_BASE
    max_root_ca_path: str | None = None
    httpx_trust_env: bool = False
    suppress_polling_network_errors: bool = False
    max_webhook_secret: str | None = field(default=None, repr=False)
    max_webhook_url: str | None = field(default=None, repr=False)
    max_transport: str = "polling"
    max_polling_timeout: int = 30
    max_polling_limit: int = 100
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    users_file: str = "bot_users.json"
    bot_platform: str = "max"
    department_chat_ids: dict[str, int] = field(default_factory=DEFAULT_DEPARTMENT_CHAT_IDS.copy)
    department_contacts: dict[str, str] = field(default_factory=dict)
    specialist_ids: set[int] | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if (
            not self.max_bot_token.strip()
            or self.max_bot_token.strip().lower() in {"replace_me", "your_token", "your_bot_token"}
            or any(character.isspace() for character in self.max_bot_token)
        ):
            raise ValueError("MAX_BOT_TOKEN must contain a non-placeholder token without whitespace")
        self.max_api_base = validate_api_base(self.max_api_base)
        self.max_transport = self.max_transport.strip().lower()
        if self.max_transport not in {"polling", "webhook"}:
            raise ValueError("MAX_TRANSPORT must be polling or webhook")
        for name, value, minimum, maximum in (
            ("MAX_POLLING_TIMEOUT", self.max_polling_timeout, 0, 90),
            ("MAX_POLLING_LIMIT", self.max_polling_limit, 1, 1000),
            ("APP_PORT", self.app_port, 1, 65535),
        ):
            if type(value) is not int or not minimum <= value <= maximum:
                raise ValueError(f"{name} must be an integer from {minimum} to {maximum}")
        if not self.users_file.strip() or not self.app_host.strip():
            raise ValueError("USERS_FILE and APP_HOST must not be empty")
        if self.department_chat_ids.keys() != DEPARTMENTS.keys() or any(
            type(chat_id) is not int or chat_id == 0 for chat_id in self.department_chat_ids.values()
        ):
            raise ValueError("Every department requires a nonzero integer chat ID")
        if self.specialist_ids is not None and any(type(user_id) is not int or user_id <= 0 for user_id in self.specialist_ids):
            raise ValueError("SPECIALIST_IDS must contain positive integer user IDs")
        if self.use_webhook:
            if (
                not self.max_webhook_secret
                or self.max_webhook_secret.lower() in {"replace_me", "your_secret"}
                or re.fullmatch(r"[A-Za-z0-9_-]{5,256}", self.max_webhook_secret) is None
            ):
                raise ValueError("Webhook mode requires a non-placeholder MAX_WEBHOOK_SECRET (5-256 ASCII letters, digits, _ or -)")
            try:
                webhook = urlsplit(self.max_webhook_url or "")
                valid = (
                    webhook.scheme == "https" and bool(webhook.hostname)
                    and webhook.port in {None, 443} and webhook.username is None
                    and webhook.password is None and not webhook.query and not webhook.fragment
                    and not any(character.isspace() for character in (self.max_webhook_url or ""))
                )
            except ValueError:
                valid = False
            if not valid:
                raise ValueError("Webhook mode requires MAX_WEBHOOK_URL using HTTPS on port 443 without credentials or parameters")

    @property
    def use_webhook(self) -> bool:
        return self.max_transport.lower() == "webhook"


def load_settings() -> Settings:
    # Existing environment variables take precedence; the file is never modified.
    directory = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
    load_dotenv(dotenv_path=directory / ".env", override=False)
    token = os.getenv("MAX_BOT_TOKEN", "").strip()
    if not token:
        raise RuntimeError("MAX_BOT_TOKEN is required")

    proxy_default = _env_bool("MAX_USE_ENV_PROXY", False) if "HTTPX_TRUST_ENV" not in os.environ else False
    try:
        specialist_ids = {int(value) for value in os.getenv("SPECIALIST_IDS", "").split(",") if value.strip()}
    except ValueError:
        raise ValueError("SPECIALIST_IDS must contain comma-separated integer user IDs") from None
    return Settings(
        max_bot_token=token,
        max_api_base=os.getenv("MAX_API_BASE", DEFAULT_API_BASE).strip(),
        max_root_ca_path=os.getenv("MAX_ROOT_CA_PATH", "").strip() or None,
        httpx_trust_env=_env_bool("HTTPX_TRUST_ENV", proxy_default),
        suppress_polling_network_errors=_env_bool("SUPPRESS_POLLING_NETWORK_ERRORS", False),
        max_webhook_secret=os.getenv("MAX_WEBHOOK_SECRET", "").strip() or None,
        max_webhook_url=os.getenv("MAX_WEBHOOK_URL", "").strip() or None,
        max_transport=os.getenv("MAX_TRANSPORT", "polling").strip() or "polling",
        max_polling_timeout=_env_int("MAX_POLLING_TIMEOUT", 30),
        max_polling_limit=_env_int("MAX_POLLING_LIMIT", 100),
        app_host=os.getenv("APP_HOST", "0.0.0.0"),
        app_port=_env_int("APP_PORT", 8000),
        users_file=os.getenv("USERS_FILE", "bot_users.json"),
        bot_platform=os.getenv("BOT_PLATFORM", "max"),
        department_chat_ids={
            key: _env_int(f"DEPARTMENT_CHAT_ID_{key.upper()}", default)
            for key, default in DEFAULT_DEPARTMENT_CHAT_IDS.items()
        },
        department_contacts={key: os.getenv(f"DEPARTMENT_CONTACT_{key.upper()}", "").strip() for key in DEPARTMENTS},
        specialist_ids=specialist_ids,
    )
