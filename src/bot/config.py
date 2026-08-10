"""Runtime config from environment."""

from __future__ import annotations

import os
from dataclasses import dataclass


def _int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    return int(raw)


@dataclass(frozen=True)
class Settings:
    bot_token: str
    turn_timeout_s: int = 60
    claim_timeout_s: int = 60
    database_path: str = ".data/bot.sqlite"
    default_bot_difficulty: str = "normal"


def load_settings() -> Settings:
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or "").strip()
    if not token:
        raise RuntimeError(
            "TELEGRAM_BOT_TOKEN is not set. Copy .env.example to .env and add your BotFather token."
        )
    diff = (os.getenv("BOT_DIFFICULTY") or "normal").strip().lower()
    if diff not in ("easy", "normal", "hard"):
        diff = "normal"
    return Settings(
        bot_token=token,
        turn_timeout_s=max(10, _int("TURN_TIMEOUT_S", 60)),
        claim_timeout_s=max(10, _int("CLAIM_TIMEOUT_S", 60)),
        database_path=os.getenv("DATABASE_PATH", ".data/bot.sqlite"),
        default_bot_difficulty=diff,
    )
