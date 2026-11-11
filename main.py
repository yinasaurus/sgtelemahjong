"""Entry point: Singapore Mahjong Telegram bot."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "src"))

load_dotenv(ROOT / ".env")

from telegram import (
    BotCommand,
    BotCommandScopeAllGroupChats,
    BotCommandScopeAllPrivateChats,
    BotCommandScopeDefault,
    Update,
)
from telegram.ext import Application, ContextTypes

from bot.config import load_settings
from bot.handlers import register_handlers
from bot.state import TableManager
from bot.timers import TimerHub


logging.basicConfig(
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    level=logging.INFO,
)
log = logging.getLogger("main")

_COMMANDS = [
    BotCommand("start", "Start here — how to play"),
    BotCommand("menu", "Open play menu"),
    BotCommand("howto", "How to start a game"),
    BotCommand("rules", "Singapore Mahjong rules book"),
    BotCommand("hand", "Resend your private hand"),
    BotCommand("standings", "Session scores"),
    BotCommand("endsession", "End table + settle scores"),
]


async def _post_init(app: Application) -> None:
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeDefault())
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeAllGroupChats())
    log.info("Bot commands registered (private + groups)")
    tables: TableManager = app.bot_data["tables"]
    if getattr(tables, "startup_abandoned", 0):
        log.warning(
            "Abandoned %s active/setup DB table(s) from a previous process "
            "(live hands are memory-only — start a new table in Telegram)",
            tables.startup_abandoned,
        )


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    log.exception("Unhandled error update=%s", update)
    if isinstance(update, Update) and update.effective_chat:
        try:
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text="Something went wrong — try /menu or /hand.",
            )
        except Exception:
            pass


def main() -> None:
    settings = load_settings()
    tables = TableManager(settings.database_path)
    app = (
        Application.builder()
        .token(settings.bot_token)
        .concurrent_updates(True)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["tables"] = tables
    app.bot_data["timers"] = TimerHub()
    register_handlers(app)
    app.add_error_handler(_on_error)
    log.info(
        "Starting Singapore Mahjong bot (turn=%ss claim=%ss)",
        settings.turn_timeout_s,
        settings.claim_timeout_s,
    )
    # Only one process may poll — stop local copies before deploying
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
