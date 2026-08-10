"""Slash commands for Phase 2."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.constants import ChatType
from telegram.ext import CommandHandler, ContextTypes

from bot import flow, guide, keyboards, render

log = logging.getLogger(__name__)


def _display_name(user) -> str:
    if user.username:
        return f"@{user.username}"
    return (user.full_name or str(user.id))[:32]


async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Friendly button menu (also used by /menu)."""
    if not update.message or not update.effective_chat:
        return
    chat = update.effective_chat
    if chat.type == ChatType.PRIVATE:
        uid = update.effective_user.id if update.effective_user else None
        # Deep-link /start rules|howto
        args = context.args or []
        if args and args[0].lower() in ("rules", "rule"):
            text, idx = guide.rules_page(0)
            await update.message.reply_text(
                text, reply_markup=guide.rules_keyboard(0, idx)
            )
            return
        if args and args[0].lower() in ("howto", "help", "guide"):
            await update.message.reply_text(
                guide.HOWTO, reply_markup=guide.howto_keyboard(0)
            )
            return
        # If already in a hand, just refresh the photo — don't spam the welcome wall
        if uid is not None:
            for t in flow.mgr(context).tables.values():
                seat = t.seat_of_user(uid)
                if seat is not None and t.game is not None:
                    await flow.send_hand_dm(
                        context, t, seat.seat_index, force_new=True
                    )
                    return
        uname = context.bot.username
        await update.message.reply_text(
            guide.START_PRIVATE,
            reply_markup=keyboards.private_start_keyboard(uname),
        )
        return
    table = flow.mgr(context).get(chat.id)
    text = (
        guide.START_GROUP_ACTIVE if table is not None else guide.START_GROUP_FRESH
    )
    await update.message.reply_text(
        text,
        reply_markup=keyboards.group_menu_keyboard(chat.id, has_table=table is not None),
    )


async def cmd_menu(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await cmd_start(update, context)


async def cmd_howto(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    await update.message.reply_text(
        guide.HOWTO, reply_markup=guide.howto_keyboard(chat_id)
    )


async def cmd_rules(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    chat_id = update.effective_chat.id
    text, idx = guide.rules_page(0)
    await update.message.reply_text(
        text, reply_markup=guide.rules_keyboard(chat_id, idx)
    )


def _parse_newtable_args(args: list[str]):
    from mahjong.settlement import SessionRules

    bots = 0
    diff = "easy"
    uma = (15000, 5000, -5000, -15000)
    length = "hanchan"
    for a in args:
        al = a.lower().strip()
        if al.startswith("bots="):
            try:
                bots = int(al.split("=", 1)[1])
            except ValueError:
                return "Invalid bots= value (use 0–3)."
        elif al.startswith("diff="):
            diff = al.split("=", 1)[1]
            if diff not in ("easy", "normal"):
                return "diff must be easy or normal."
        elif al.startswith("uma="):
            parts = al.split("=", 1)[1].split("/")
            if len(parts) != 4:
                return "uma must be like uma=15/5/-5/-15 (thousands)."
            try:
                uma = tuple(int(p) * 1000 for p in parts)  # type: ignore[assignment]
            except ValueError:
                return "Invalid uma values."
        elif al.startswith("length="):
            length = al.split("=", 1)[1]
            if length not in ("tonpuusen", "hanchan"):
                return "length must be tonpuusen or hanchan."
        elif al.isdigit():
            bots = int(al)
        else:
            return f"Unknown arg '{a}'."
    if not 0 <= bots <= 3:
        return "bots must be 0–3 (need ≥1 human)."
    rules = SessionRules(uma=uma, length=length)  # type: ignore[arg-type]
    return bots, diff, rules


async def cmd_newtable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    chat = update.effective_chat
    if chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
        await update.message.reply_text("Start a table in a group chat.")
        return
    parsed = _parse_newtable_args(context.args or [])
    if isinstance(parsed, str):
        await update.message.reply_text(parsed)
        return
    bots, diff, session_rules = parsed
    settings = context.application.bot_data["settings"]
    result = flow.mgr(context).create(
        chat.id,
        update.effective_user.id,
        turn_timeout_s=settings.turn_timeout_s,
        claim_timeout_s=settings.claim_timeout_s,
        bots=bots,
        bot_difficulty=diff,
        session_rules=session_rules,
    )
    if isinstance(result, str):
        await update.message.reply_text(result)
        return
    table = result
    # Host auto-joins first
    err = table.join(update.effective_user.id, _display_name(update.effective_user))
    if err:
        await update.message.reply_text(err)
        return
    if bots:
        err = table.fill_bots(bots, difficulty=diff)
        if err:
            await update.message.reply_text(err)
            flow.mgr(context).end(chat.id)
            return
    flow.mgr(context).persist(table)
    msg = await update.message.reply_text(
        render.lobby_text(table),
        reply_markup=keyboards.lobby_keyboard(table.chat_id),
    )
    table.board_message_id = msg.message_id
    if table.ready_to_deal():
        await flow.deal_and_announce(context, table)


async def cmd_join(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No table — /newtable first.")
        return
    err = table.join(update.effective_user.id, _display_name(update.effective_user))
    if err:
        await update.message.reply_text(err)
        return
    flow.mgr(context).persist(table)
    await update.message.reply_text(f"{_display_name(update.effective_user)} joined.")
    await flow.refresh_board(context, table)
    if table.ready_to_deal():
        await flow.deal_and_announce(context, table)


async def cmd_leave(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No table here.")
        return
    err = table.leave(update.effective_user.id)
    if err:
        await update.message.reply_text(err)
        return
    # Empty lobby → end table
    if table.human_count() == 0:
        flow.mgr(context).end(table.chat_id)
        await update.message.reply_text("Left. Table closed (empty).")
        return
    flow.mgr(context).persist(table)
    await update.message.reply_text("Left the table.")
    await flow.refresh_board(context, table)


async def cmd_table(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No active table. /newtable")
        return
    table.board_message_id = None
    await flow.refresh_board(context, table)


async def cmd_endtable(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No table.")
        return
    uid = update.effective_user.id
    if table.host_user_id not in (None, uid) and table.seat_of_user(uid) is None:
        await update.message.reply_text("Only the host or a seated player can end the table.")
        return
    flow.timers(context).cancel(table.chat_id)
    flow.mgr(context).end(table.chat_id, abandon=True)
    await update.message.reply_text(
        "Table closed (no uma settlement). Use /endsession to settle properly."
    )


async def cmd_standings(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    from bot import session_ops

    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No active session.")
        return
    await update.message.reply_text(
        session_ops.standings_text(flow.mgr(context).db_path, table)
    )


async def cmd_endsession(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    from bot import session_ops

    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None:
        await update.message.reply_text("No active session.")
        return
    uid = update.effective_user.id
    if table.seat_of_user(uid) is None and uid != table.host_user_id:
        await update.message.reply_text("Only seated players can end the session.")
        return
    flow.timers(context).cancel(table.chat_id)
    text = session_ops.end_session_text(flow.mgr(context).db_path, table)
    flow.mgr(context).tables.pop(table.chat_id, None)
    await update.message.reply_text(text)


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat:
        return
    from bot import session_ops

    await update.message.reply_text(
        session_ops.history_text(
            flow.mgr(context).db_path, update.effective_chat.id
        )
    )


async def cmd_undo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.message or not update.effective_chat or not update.effective_user:
        return
    from db import models as db

    table = flow.mgr(context).get(update.effective_chat.id)
    if table is None or table.db_table_id is None:
        await update.message.reply_text("No active session.")
        return
    uid = update.effective_user.id
    if table.seat_of_user(uid) is None and uid != table.host_user_id:
        await update.message.reply_text("Only seated players can undo.")
        return
    undone = db.undo_last_hand(flow.mgr(context).db_path, table.db_table_id)
    if undone is None:
        await update.message.reply_text("Nothing to undo.")
        return
    table.result_recorded = False
    from bot import session_ops

    await update.message.reply_text(
        f"Undid hand #{undone['hand_number']} ({undone['reason']}).\n\n"
        + session_ops.standings_text(flow.mgr(context).db_path, table)
    )


async def cmd_hand(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Re-send private hand DM (helpful if keyboard was lost)."""
    if not update.message or not update.effective_user:
        return
    uid = update.effective_user.id
    # Find a table where this user is seated
    tables: dict = flow.mgr(context).tables
    found = None
    for t in tables.values():
        if t.seat_of_user(uid) and t.game is not None:
            found = t
            break
    if found is None:
        await update.message.reply_text("No active hand for you.")
        return
    seat = found.seat_of_user(uid)
    assert seat is not None
    await flow.send_hand_dm(context, found, seat.seat_index, force_new=True)
    if update.effective_chat and update.effective_chat.type != "private":
        await update.message.reply_text("Hand sent to your DM.")


def register_command_handlers(app) -> None:
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("menu", cmd_menu))
    app.add_handler(CommandHandler("howto", cmd_howto))
    app.add_handler(CommandHandler("help", cmd_howto))
    app.add_handler(CommandHandler("rules", cmd_rules))
    app.add_handler(CommandHandler("newtable", cmd_newtable))
    app.add_handler(CommandHandler("join", cmd_join))
    app.add_handler(CommandHandler("leave", cmd_leave))
    app.add_handler(CommandHandler("table", cmd_table))
    app.add_handler(CommandHandler("standings", cmd_standings))
    app.add_handler(CommandHandler("endsession", cmd_endsession))
    app.add_handler(CommandHandler("history", cmd_history))
    app.add_handler(CommandHandler("undo", cmd_undo))
    app.add_handler(CommandHandler("endtable", cmd_endtable))
    app.add_handler(CommandHandler("hand", cmd_hand))
