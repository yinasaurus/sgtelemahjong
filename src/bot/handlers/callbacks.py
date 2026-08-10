"""Inline callback handlers."""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from mahjong.game import ClaimType, GamePhase
from mahjong.tiles import Suit, Tile

from bot import flow, guide, keyboards
from bot.state import TableStatus

log = logging.getLogger(__name__)


async def on_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    q = update.callback_query
    if not q or not q.data or not q.from_user:
        return
    data = q.data
    parts = data.split(":")
    if not parts:
        await q.answer("Bad request.", show_alert=True)
        return
    kind = parts[0]
    try:
        if kind == "m":
            await _menu_cb(q, context, parts)
        elif kind == "t":
            await _table_cb(q, context, parts)
        elif kind == "d":
            await _discard_cb(q, context, parts)
        elif kind == "c":
            await _claim_cb(q, context, parts)
        elif kind == "chi":
            await _chi_cb(q, context, parts)
        elif kind == "a":
            await _action_cb(q, context, parts)
        elif kind == "r":
            await _riichi_discard_cb(q, context, parts)
        elif kind == "k":
            await _kan_cb(q, context, parts)
        else:
            await q.answer("Unknown action.", show_alert=True)
    except Exception:
        log.exception("callback failed data=%s", data)
        await q.answer("Error — try /table or /hand.", show_alert=True)


def _table(context, chat_id: int):
    return flow.mgr(context).get(chat_id)


async def _menu_cb(q, context, parts: list[str]) -> None:
    """Group/private menu buttons: m:chat:new:bots:diff | m:chat:help | m:chat:history"""
    if len(parts) < 3:
        await q.answer("Bad menu.", show_alert=True)
        return
    chat_id = int(parts[1])
    action = parts[2]

    if action in ("help", "howto"):
        await q.answer()
        target = q.message.chat_id if q.message else chat_id
        await context.bot.send_message(
            chat_id=target,
            text=guide.HOWTO,
            reply_markup=guide.howto_keyboard(chat_id or target),
        )
        return

    if action == "rules":
        await q.answer()
        page = int(parts[3]) if len(parts) >= 4 else 0
        text, idx = guide.rules_page(page)
        target = q.message.chat_id if q.message else chat_id
        # Edit in place when paging the same rules message
        if (
            q.message
            and q.message.text
            and q.message.text.startswith("📖 Rules")
            and len(parts) >= 4
        ):
            try:
                await q.edit_message_text(
                    text=text,
                    reply_markup=guide.rules_keyboard(chat_id or target, idx),
                )
                return
            except Exception:
                pass
        await context.bot.send_message(
            chat_id=target,
            text=text,
            reply_markup=guide.rules_keyboard(chat_id or target, idx),
        )
        return

    if action == "menu":
        await q.answer()
        target = q.message.chat_id if q.message else chat_id
        from telegram.constants import ChatType

        has_table = _table(context, chat_id) is not None if chat_id else False
        # Private vs group copy
        if q.message and q.message.chat.type == ChatType.PRIVATE:
            await context.bot.send_message(
                chat_id=target,
                text=guide.START_PRIVATE,
                reply_markup=keyboards.private_start_keyboard(context.bot.username),
            )
        else:
            text = (
                guide.START_GROUP_ACTIVE if has_table else guide.START_GROUP_FRESH
            )
            await context.bot.send_message(
                chat_id=target,
                text=text,
                reply_markup=keyboards.group_menu_keyboard(
                    chat_id or target, has_table=has_table
                ),
            )
        return

    if action == "history":
        from bot import session_ops

        await q.answer()
        target = chat_id if chat_id else (q.message.chat_id if q.message else 0)
        await context.bot.send_message(
            chat_id=q.message.chat_id if q.message else target,
            text=session_ops.history_text(flow.mgr(context).db_path, target),
        )
        return

    if action == "new":
        if len(parts) != 5:
            await q.answer("Bad new-table.", show_alert=True)
            return
        bots = int(parts[3])
        diff = parts[4]
        if q.message and q.message.chat.type == "private":
            await q.answer("Start a table in a group chat.", show_alert=True)
            return
        if _table(context, chat_id) is not None:
            await q.answer("A table is already open.", show_alert=True)
            return
        from mahjong.settlement import SessionRules
        from bot.handlers.commands import _display_name

        settings = context.application.bot_data["settings"]
        result = flow.mgr(context).create(
            chat_id,
            q.from_user.id,
            turn_timeout_s=settings.turn_timeout_s,
            claim_timeout_s=settings.claim_timeout_s,
            bots=bots,
            bot_difficulty=diff,
            session_rules=SessionRules(),
        )
        if isinstance(result, str):
            await q.answer(result, show_alert=True)
            return
        table = result
        err = table.join(q.from_user.id, _display_name(q.from_user))
        if err:
            await q.answer(err, show_alert=True)
            flow.mgr(context).end(chat_id, abandon=True)
            return
        if bots:
            err = table.fill_bots(bots, difficulty=diff)
            if err:
                await q.answer(err, show_alert=True)
                flow.mgr(context).end(chat_id, abandon=True)
                return
        flow.mgr(context).persist(table)
        await q.answer("Table created.")
        from bot import render

        msg = await context.bot.send_message(
            chat_id=chat_id,
            text=render.lobby_text(table),
            reply_markup=keyboards.lobby_keyboard(chat_id),
        )
        table.board_message_id = msg.message_id
        if table.ready_to_deal():
            await flow.deal_and_announce(context, table)
        return

    await q.answer("Unknown menu.", show_alert=True)


async def _table_cb(q, context, parts: list[str]) -> None:
    if len(parts) != 3:
        await q.answer("Bad request.", show_alert=True)
        return
    chat_id = int(parts[1])
    action = parts[2]
    table = _table(context, chat_id)
    uid = q.from_user.id
    if action == "join":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        from bot.handlers.commands import _display_name

        err = table.join(uid, _display_name(q.from_user))
        if err:
            await q.answer(err, show_alert=True)
            return
        await q.answer("Joined.")
        flow.mgr(context).persist(table)
        await flow.refresh_board(context, table)
        if table.ready_to_deal():
            await flow.deal_and_announce(context, table)
        return
    if action == "leave":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        err = table.leave(uid)
        if err:
            await q.answer(err, show_alert=True)
            return
        await q.answer("Left.")
        if table.human_count() == 0:
            flow.mgr(context).end(chat_id)
            await context.bot.send_message(chat_id=chat_id, text="Table closed (empty).")
            return
        flow.mgr(context).persist(table)
        await flow.refresh_board(context, table)
        return
    if action == "table":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        await q.answer()
        await flow.refresh_board(context, table)
        return
    if action == "hand":
        if table is None or table.game is None:
            await q.answer("No active hand.", show_alert=True)
            return
        seat = table.seat_of_user(uid)
        if seat is None:
            await q.answer("You're not seated.", show_alert=True)
            return
        await q.answer("Sent to DM.")
        await flow.send_hand_dm(context, table, seat.seat_index, force_new=True)
        return
    if action == "nexthand":
        if table is None or table.game is None:
            await q.answer("No table.", show_alert=True)
            return
        if table.seat_of_user(uid) is None:
            await q.answer("Only seated players.", show_alert=True)
            return
        if table.game.phase != GamePhase.ENDED:
            await q.answer("Hand still in progress.", show_alert=True)
            return
        await q.answer("Dealing…")
        old = table.game
        dealer = old.dealer
        round_wind = old.round_wind
        honba = old.honba
        sticks = old.riichi_sticks
        if old.result:
            if old.result.winner is None or old.result.winner == old.dealer:
                honba += 1
            else:
                honba = 0
                dealer = (old.dealer + 1) % 4
                if dealer == 0:
                    round_wind = (old.round_wind + 1) % 4
        from mahjong.game import Game

        table.game = Game.new_hand(
            dealer=dealer,
            round_wind=round_wind,
            honba=honba,
            riichi_sticks=sticks,
        )
        table.status = TableStatus.ACTIVE
        table.hand_number += 1
        table.timer_token += 1
        table.hand_message_ids.clear()
        table.board_message_id = None
        table.board_is_photo = False  # type: ignore[attr-defined]
        table.discard_message_id = None  # type: ignore[attr-defined]
        table.result_recorded = False
        table.last_discard = None
        table._last_ping_key = None  # type: ignore[attr-defined]
        if hasattr(table, "_dm_warn_users"):
            table._dm_warn_users.clear()  # type: ignore[attr-defined]
        flow.mgr(context).persist(table)
        # Single board refresh — no extra "Dealing…" spam
        await flow.after_game_action(context, table, force_new_hands=True)
        return
    if action == "end":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        await q.answer("Ended.")
        flow.timers(context).cancel(chat_id)
        flow.mgr(context).end(chat_id, abandon=True)
        await context.bot.send_message(chat_id=chat_id, text="Table abandoned.")
        return
    if action == "endsession":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        if table.seat_of_user(uid) is None and uid != table.host_user_id:
            await q.answer("Only seated players.", show_alert=True)
            return
        from bot import session_ops

        await q.answer("Settling…")
        flow.timers(context).cancel(chat_id)
        text = session_ops.end_session_text(flow.mgr(context).db_path, table)
        flow.mgr(context).tables.pop(chat_id, None)
        await context.bot.send_message(chat_id=chat_id, text=text)
        return
    if action == "standings":
        if table is None:
            await q.answer("No table.", show_alert=True)
            return
        from bot import session_ops

        await q.answer()
        await context.bot.send_message(
            chat_id=chat_id,
            text=session_ops.standings_text(flow.mgr(context).db_path, table),
        )
        return
    await q.answer("Unknown.", show_alert=True)


async def _discard_cb(q, context, parts: list[str]) -> None:
    # d:chat:seat:idx
    if len(parts) != 4:
        await q.answer("Bad discard.", show_alert=True)
        return
    chat_id, seat, idx = int(parts[1]), int(parts[2]), int(parts[3])
    table = _table(context, chat_id)
    if table is None or table.game is None:
        await q.answer("No game.", show_alert=True)
        return
    if not _auth_seat(table, q.from_user.id, seat):
        await q.answer("Not your seat.", show_alert=True)
        return
    g = table.game
    if g.phase != GamePhase.PLAYING or g.turn_seat != seat or not g.has_drawn:
        await q.answer(
            "Not your turn (or old buttons). Opening a fresh hand…",
            show_alert=True,
        )
        # Stale DM keyboard from an earlier message — refresh
        await flow.send_hand_dm(context, table, seat, force_new=True)
        return
    tile = (
        g.players[seat].hand.concealed[idx]
        if 0 <= idx < len(g.players[seat].hand.concealed)
        else None
    )
    if not g.discard(seat, idx):
        await q.answer(g.last_error or "Illegal discard.", show_alert=True)
        await flow.send_hand_dm(context, table, seat, force_new=True)
        return
    if tile is not None:
        await q.answer(f"Threw {tile.unicode()} {tile.label()} ✓")
        await flow.announce_discard(context, table, seat, tile, with_photo=True)
    else:
        await q.answer("Threw ✓")
    await flow.after_game_action(context, table)


async def _claim_cb(q, context, parts: list[str]) -> None:
    # c:chat:seat:kind
    if len(parts) != 4:
        await q.answer("Bad claim.", show_alert=True)
        return
    chat_id, seat = int(parts[1]), int(parts[2])
    kind_s = parts[3]
    table = _table(context, chat_id)
    if table is None or table.game is None:
        await q.answer("No game.", show_alert=True)
        return
    if not _auth_seat(table, q.from_user.id, seat):
        await q.answer("Not your seat.", show_alert=True)
        return
    g = table.game
    if kind_s == "pass":
        kind = ClaimType.PASS
    elif kind_s == "chi":
        await q.answer("Pick a Chi option below.", show_alert=True)
        return
    else:
        try:
            kind = ClaimType(kind_s)
        except ValueError:
            await q.answer("Bad claim.", show_alert=True)
            return
    if not g.register_claim(seat, kind):
        await q.answer(g.last_error or "Cannot claim.", show_alert=True)
        return
    await q.answer(f"{kind.value} registered.")
    await flow.after_game_action(context, table, force_new_hands=True)


async def _chi_cb(q, context, parts: list[str]) -> None:
    # chi:chat:seat:s1:v1:a1:s2:v2:a2
    if len(parts) != 9:
        await q.answer("Bad chi.", show_alert=True)
        return
    chat_id = int(parts[1])
    seat = int(parts[2])
    a = Tile(Suit(int(parts[3])), int(parts[4]), aka=bool(int(parts[5])))
    b = Tile(Suit(int(parts[6])), int(parts[7]), aka=bool(int(parts[8])))
    table = _table(context, chat_id)
    if table is None or table.game is None:
        await q.answer("No game.", show_alert=True)
        return
    if not _auth_seat(table, q.from_user.id, seat):
        await q.answer("Not your seat.", show_alert=True)
        return
    g = table.game
    if not g.register_claim(seat, ClaimType.CHI, chi_tiles=(a, b)):
        await q.answer(g.last_error or "Cannot chi.", show_alert=True)
        return
    await q.answer("Chi registered.")
    await flow.after_game_action(context, table, force_new_hands=True)


async def _action_cb(q, context, parts: list[str]) -> None:
    # a:chat:seat:action
    if len(parts) != 4:
        await q.answer("Bad action.", show_alert=True)
        return
    chat_id, seat = int(parts[1]), int(parts[2])
    action = parts[3]
    table = _table(context, chat_id)
    if table is None or table.game is None:
        await q.answer("No game.", show_alert=True)
        return
    if not _auth_seat(table, q.from_user.id, seat):
        await q.answer("Not your seat.", show_alert=True)
        return
    g = table.game
    uid = q.from_user.id
    if action == "tsumo":
        if not g.declare_tsumo(seat):
            await q.answer(g.last_error or "Cannot win.", show_alert=True)
            return
        await q.answer("Self-draw!")
        await flow.after_game_action(context, table)
        return
    if action == "riichi_mode":
        await q.answer("No riichi in Singapore Mahjong.", show_alert=True)
        return
    if action == "cancel_riichi":
        await q.answer("Cancelled.")
        await flow.send_hand_dm(context, table, seat, force_new=True)
        return
    await q.answer("Unknown action.", show_alert=True)


async def _riichi_discard_cb(q, context, parts: list[str]) -> None:
    await q.answer("No riichi in Singapore Mahjong.", show_alert=True)


async def _kan_cb(q, context, parts: list[str]) -> None:
    # k:chat:seat:ankan|shou:suit:value
    if len(parts) != 6:
        await q.answer("Bad kan.", show_alert=True)
        return
    chat_id, seat = int(parts[1]), int(parts[2])
    mode = parts[3]
    tile = Tile(Suit(int(parts[4])), int(parts[5]))
    table = _table(context, chat_id)
    if table is None or table.game is None:
        await q.answer("No game.", show_alert=True)
        return
    if not _auth_seat(table, q.from_user.id, seat):
        await q.answer("Not your seat.", show_alert=True)
        return
    g = table.game
    if mode == "ankan":
        ok = g.declare_ankan(seat, tile)
    elif mode == "shou":
        ok = g.declare_shouminkan(seat, tile)
    else:
        await q.answer("Bad kan.", show_alert=True)
        return
    if not ok:
        await q.answer(g.last_error or "Cannot kan.", show_alert=True)
        return
    await q.answer("Kan!")
    await context.bot.send_message(
        chat_id=chat_id, text=f"{table.name_for_seat(seat)} declared kan."
    )
    await flow.after_game_action(context, table)


def _auth_seat(table, user_id: int, seat: int) -> bool:
    s = table.seat_of_user(user_id)
    return s is not None and s.seat_index == seat


def register_callback_handlers(app) -> None:
    app.add_handler(CallbackQueryHandler(on_callback))
