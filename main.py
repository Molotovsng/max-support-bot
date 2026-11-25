from __future__ import annotations

import asyncio
import logging
import secrets
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import httpcore
import httpx
import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request

from config import Settings, load_settings
from constants import DEFAULT_DEPARTMENT_CHAT_IDS
from maxbot.client import MaxClient
from maxbot.instance_lock import InstanceLock
from maxbot.logging_utils import RuntimeEventFilter, RuntimeEventFormatter, log_failure
from maxbot.normalizer import normalize_update
from maxbot.service import BotService
from maxbot.storage import AppealLinkRegistry, UserRegistry

LOG_FORMAT = "%(asctime)s - %(levelname)s - %(message)s"


def configure_logging(log_file: str | Path = "bot.log") -> None:
    formatter = RuntimeEventFormatter(LOG_FORMAT)
    event_filter = RuntimeEventFilter()

    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
        handler.close()

    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(formatter)
    stream_handler.addFilter(event_filter)

    file_handler = RotatingFileHandler(
        log_file, maxBytes=5 * 1024 * 1024, backupCount=5, encoding="utf-8", delay=True,
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(event_filter)

    root_logger.addHandler(stream_handler)
    root_logger.addHandler(file_handler)
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    # Access logs include caller-controlled URLs and query parameters.
    logging.getLogger("uvicorn.access").disabled = True

logger = logging.getLogger(__name__)


def _log_polling_network_warning(settings: Settings, message: str, exc: Exception) -> None:
    if settings.suppress_polling_network_errors:
        return
    error_type = type(exc).__name__
    logger.warning("%s (error_type=%s)", message, error_type, extra={"safe_event": message, "safe_error_type": error_type})


def build_service(settings: Settings) -> BotService:
    client = MaxClient(
        settings.max_bot_token,
        settings.max_api_base,
        trust_env=settings.httpx_trust_env,
        root_ca_path=settings.max_root_ca_path,
    )
    registry = UserRegistry(settings.users_file)
    appeal_links = AppealLinkRegistry(str(Path(settings.users_file).with_name("appeal_links.json")))
    return BotService(
        client, registry, appeal_links,
        department_chat_ids=settings.department_chat_ids,
        department_contacts=settings.department_contacts,
        specialist_ids=settings.specialist_ids,
    )


async def process_update(service: BotService, update: dict) -> None:
    try:
        event = normalize_update(update)
        await service.handle_update(event)
    except Exception as exc:
        log_failure(logger, "Failed to process update", exc)


def create_app(settings: Settings, service: BotService) -> FastAPI:
    if not settings.max_webhook_secret:
        raise ValueError("MAX_WEBHOOK_SECRET is required for the webhook endpoint")

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        if settings.max_webhook_url:
            try:
                await service.client.subscribe_webhook(
                    url=settings.max_webhook_url,
                    secret=settings.max_webhook_secret,
                    update_types=["bot_started", "message_created", "message_callback"],
                )
                logger.info("Webhook subscription ensured")
            except Exception as exc:
                log_failure(logger, "Failed to subscribe webhook", exc)
        try:
            yield
        finally:
            await service.client.aclose()

    app = FastAPI(lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, bool]:
        return {"ok": True}

    @app.post("/webhook/max")
    async def max_webhook(
        request: Request,
        x_max_bot_api_secret: str | None = Header(default=None),
    ) -> dict[str, bool]:
        if not secrets.compare_digest(
            (x_max_bot_api_secret or "").encode("utf-8"),
            settings.max_webhook_secret.encode("utf-8"),
        ):
            raise HTTPException(status_code=403, detail="Invalid MAX webhook secret")
        try:
            update = await request.json()
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid JSON") from None
        if not isinstance(update, dict):
            raise HTTPException(status_code=400, detail="Update must be an object")
        await process_update(service, update)
        return {"ok": True}

    return app


async def run_polling(settings: Settings, service: BotService) -> None:
    marker: int | None = None
    logger.info("MAX bot started in polling mode")
    try:
        while True:
            try:
                payload = await service.client.get_updates(
                    marker=marker,
                    limit=settings.max_polling_limit,
                    timeout=settings.max_polling_timeout,
                    types=[],
                )
                updates = payload.get("updates", [])
                if isinstance(updates, list) and updates:
                    logger.info(
                        "Polling received updates=%s",
                        len(updates),
                    )
                marker = payload.get("marker", marker)
                for update in updates:
                    if isinstance(update, dict):
                        await process_update(service, update)
            except (httpx.ProxyError, httpcore.ProxyError) as exc:
                _log_polling_network_warning(
                    settings,
                    "Polling proxy error, retrying in 15 seconds",
                    exc,
                )
                await asyncio.sleep(15)
            except (
                httpx.ReadTimeout,
                httpx.ConnectTimeout,
                httpcore.ReadTimeout,
            ) as exc:
                _log_polling_network_warning(
                    settings,
                    "Polling timeout, retrying in 5 seconds",
                    exc,
                )
                await asyncio.sleep(5)
            except (
                httpx.ConnectError,
                httpx.NetworkError,
                httpx.RemoteProtocolError,
            ) as exc:
                _log_polling_network_warning(
                    settings,
                    "Polling network error, retrying in 10 seconds",
                    exc,
                )
                await asyncio.sleep(10)
            except httpx.HTTPError as exc:
                log_failure(logger, "Polling HTTP error", exc)
                await asyncio.sleep(10)
            except Exception as exc:
                log_failure(logger, "Polling iteration failed", exc)
                await asyncio.sleep(10)
    finally:
        await service.client.aclose()


def main() -> None:
    configure_logging()
    settings = load_settings()
    if set(settings.department_chat_ids.values()) & set(DEFAULT_DEPARTMENT_CHAT_IDS.values()):
        raise ValueError("Replace the sample department chat IDs before starting")
    service = build_service(settings)
    instance_lock = InstanceLock()
    instance_lock.acquire()
    logger.info("Settings loaded")

    if settings.use_webhook:
        app = create_app(settings, service)
        logger.info("MAX bot started in webhook mode")
        uvicorn.run(app, host=settings.app_host, port=settings.app_port, access_log=False, log_config=None)
        return

    asyncio.run(run_polling(settings, service))


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        log_failure(logger, "Bot stopped; check configuration and required files", exc)
        raise SystemExit(1) from None
