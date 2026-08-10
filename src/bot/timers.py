"""Turn / claim timeout tasks."""

from __future__ import annotations

import asyncio
import logging
from typing import Awaitable, Callable, TYPE_CHECKING

if TYPE_CHECKING:
    from telegram.ext import ContextTypes

    from .state import Table, TableManager

log = logging.getLogger(__name__)

OnTimeout = Callable[["Table", "ContextTypes.DEFAULT_TYPE"], Awaitable[None]]


class TimerHub:
    def __init__(self) -> None:
        self._tasks: dict[int, asyncio.Task] = {}

    def cancel(self, chat_id: int) -> None:
        t = self._tasks.pop(chat_id, None)
        if t and not t.done():
            t.cancel()

    def schedule(
        self,
        table: Table,
        context: ContextTypes.DEFAULT_TYPE,
        seconds: int,
        callback: OnTimeout,
    ) -> None:
        self.cancel(table.chat_id)
        token = table.timer_token
        chat_id = table.chat_id

        async def _run() -> None:
            try:
                await asyncio.sleep(seconds)
            except asyncio.CancelledError:
                return
            mgr: TableManager | None = context.application.bot_data.get("tables")
            if mgr is None:
                return
            t = mgr.get(chat_id)
            if t is None or t.timer_token != token:
                return
            try:
                await callback(t, context)
            except Exception:
                log.exception("timeout handler failed chat_id=%s", chat_id)

        self._tasks[chat_id] = asyncio.create_task(_run())
