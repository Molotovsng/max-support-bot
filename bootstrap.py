"""Windows executable entry point, including a strictly offline self-check."""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
import ssl
import sys


def offline_check() -> None:
    # These imports also exercise the frozen HTTP server dependencies. They do
    # not instantiate a bot, load configuration, open a port or make a request.
    import main
    import uvicorn.lifespan.on
    import uvicorn.loops.asyncio
    import uvicorn.protocols.http.h11_impl
    from maxbot.tls import build_ssl_context

    context = build_ssl_context()
    if not context.check_hostname or context.verify_mode != ssl.CERT_REQUIRED:
        raise RuntimeError("TLS verification must remain enabled")


def run_bot() -> None:
    previous = Path.cwd()
    try:
        if getattr(sys, "frozen", False):
            os.chdir(Path(sys.executable).resolve().parent)
        from main import main
        main()
    finally:
        os.chdir(previous)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="max-support-bot: start the bot or run an offline check.")
    parser.add_argument("--check", action="store_true", help="check bundled libraries and TLS without starting the bot")
    args, unknown = parser.parse_known_args(argv)
    if unknown:
        print("Unknown arguments. Use --help. Configure credentials in .env only.", file=sys.stderr)
        return 2
    if args.check:
        try:
            offline_check()
        except Exception as exc:
            print(json.dumps({"ok": False, "mode": "offline-check", "error_type": type(exc).__name__}))
            return 1
        print(json.dumps({"ok": True, "mode": "offline-check", "bot_started": False}))
        return 0
    try:
        run_bot()
    except KeyboardInterrupt:
        return 0
    except Exception as exc:
        from maxbot.logging_utils import log_failure
        log_failure(logging.getLogger(__name__), "Bot stopped; check configuration and required files", exc)
        print("Bot could not start. Read README.md and bot.log.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
