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
)
from telegram.ext import Application

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
    BotCommand("endsession", "End table + uma/oka"),
]


async def _post_init(app: Application) -> None:
    # Default alone often only shows in private — set group scope too
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeDefault())
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeAllPrivateChats())
    await app.bot.set_my_commands(_COMMANDS, scope=BotCommandScopeAllGroupChats())
    log.info("Bot commands registered (private + groups)")


def main() -> None:
    settings = load_settings()
    app = (
        Application.builder()
        .token(settings.bot_token)
        .concurrent_updates(True)
        .post_init(_post_init)
        .build()
    )
    app.bot_data["settings"] = settings
    app.bot_data["tables"] = TableManager(settings.database_path)
    app.bot_data["timers"] = TimerHub()
    register_handlers(app)
    log.info(
        "Starting Singapore Mahjong bot (turn=%ss claim=%ss)",
        settings.turn_timeout_s,
        settings.claim_timeout_s,
    )
    app.run_polling(allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    main()
