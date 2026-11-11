"""Shared play flow: refresh board/hands, deal, timeouts, bot loop."""

from __future__ import annotations

import asyncio
import logging
import random

from telegram.ext import ContextTypes

from mahjong.bot_player import (
    BotDifficulty,
    apply_claim_decision,
    apply_turn_decision,
    choose_claim_action,
    choose_turn_action,
)
from mahjong.game import ClaimType, GamePhase
from mahjong.tiles import Suit, Tile

from . import keyboards, render
from .state import Table, TableManager
from .timers import TimerHub

log = logging.getLogger(__name__)


def mgr(context: ContextTypes.DEFAULT_TYPE) -> TableManager:
    return context.application.bot_data["tables"]


def timers(context: ContextTypes.DEFAULT_TYPE) -> TimerHub:
    return context.application.bot_data["timers"]


async def _tg_call(coro):
    """Await a Telegram API call; honour RetryAfter once."""
    from telegram.error import RetryAfter

    try:
        return await coro
    except RetryAfter as e:
        wait = float(getattr(e, "retry_after", 1)) + 0.25
        log.warning("Telegram RetryAfter — sleeping %.1fs", wait)
        await asyncio.sleep(wait)
        return await coro


async def refresh_board(
    context: ContextTypes.DEFAULT_TYPE, table: Table, *, reply_markup=None
) -> None:
    from io import BytesIO

    from telegram import InputMediaPhoto
    from telegram.error import BadRequest

    from .board_art import render_board_png

    if reply_markup is None:
        if table.game is None:
            reply_markup = keyboards.lobby_keyboard(table.chat_id)
        elif table.game.phase == GamePhase.ENDED:
            reply_markup = keyboards.after_hand_keyboard(table.chat_id)

    # Lobby stays text; active hand = visual felt board
    if table.game is None:
        text = render.lobby_text(table)
        try:
            if table.board_message_id is None:
                msg = await _tg_call(
                    context.bot.send_message(
                        chat_id=table.chat_id, text=text, reply_markup=reply_markup
                    )
                )
                table.board_message_id = msg.message_id
                table.board_is_photo = False  # type: ignore[attr-defined]
            else:
                if getattr(table, "board_is_photo", False):
                    msg = await context.bot.send_message(
                        chat_id=table.chat_id, text=text, reply_markup=reply_markup
                    )
                    table.board_message_id = msg.message_id
                    table.board_is_photo = False  # type: ignore[attr-defined]
                else:
                    await context.bot.edit_message_text(
                        chat_id=table.chat_id,
                        message_id=table.board_message_id,
                        text=text,
                        reply_markup=reply_markup,
                    )
        except BadRequest as e:
            if "message is not modified" in str(e).lower():
                return
            msg = await context.bot.send_message(
                chat_id=table.chat_id, text=text, reply_markup=reply_markup
            )
            table.board_message_id = msg.message_id
            table.board_is_photo = False  # type: ignore[attr-defined]
        return

    caption = render.board_caption(table)
    png = render_board_png(table)
    try:
        if table.board_message_id is None or not getattr(table, "board_is_photo", False):
            msg = await _tg_call(
                context.bot.send_photo(
                    chat_id=table.chat_id,
                    photo=BytesIO(png),
                    caption=caption,
                    reply_markup=reply_markup,
                )
            )
            table.board_message_id = msg.message_id
            table.board_is_photo = True  # type: ignore[attr-defined]
            await _pin_board(context, table)
        else:
            await context.bot.edit_message_media(
                chat_id=table.chat_id,
                message_id=table.board_message_id,
                media=InputMediaPhoto(media=BytesIO(png), caption=caption),
                reply_markup=reply_markup,
            )
    except BadRequest as e:
        if "message is not modified" in str(e).lower():
            return
        log.warning("board photo refresh failed: %s", e)
        try:
            msg = await context.bot.send_photo(
                chat_id=table.chat_id,
                photo=BytesIO(png),
                caption=caption,
                reply_markup=reply_markup,
            )
            table.board_message_id = msg.message_id
            table.board_is_photo = True  # type: ignore[attr-defined]
            await _pin_board(context, table)
        except Exception:
            log.warning("board send failed chat_id=%s", table.chat_id)
    except Exception as e:  # noqa: BLE001
        log.warning("board refresh failed: %s", type(e).__name__)


async def _pin_board(context: ContextTypes.DEFAULT_TYPE, table: Table) -> None:
    """Keep the board at the top of the group so it doesn’t scroll away."""
    if table.board_message_id is None:
        return
    try:
        await context.bot.pin_chat_message(
            chat_id=table.chat_id,
            message_id=table.board_message_id,
            disable_notification=True,
        )
    except Exception:
        # Needs pin permission — ignore if bot isn’t admin
        log.debug("pin board failed chat_id=%s", table.chat_id)


async def send_hand_dm(
    context: ContextTypes.DEFAULT_TYPE, table: Table, seat: int, *, force_new: bool = False
) -> None:
    from io import BytesIO

    from telegram import InputMediaPhoto
    from telegram.error import BadRequest

    from .table_view import render_dm_view_png

    user_id = table.seats[seat].user_id
    if user_id is None or table.seats[seat].is_bot:
        return
    g = table.game
    if g is None:
        return
    tiles = list(g.players[seat].hand.concealed)
    separate = (
        g.phase == GamePhase.PLAYING
        and g.turn_seat == seat
        and g.has_drawn
        and len(tiles) == 14
    )
    png = render_dm_view_png(table, seat, separate_last=separate)
    caption = render.hand_dm_caption(table, seat)
    markup = keyboards.action_keyboard_for(table, user_id)
    mid = table.hand_message_ids.get(user_id)

    async def _send_new() -> None:
        msg = await context.bot.send_photo(
            chat_id=user_id,
            photo=BytesIO(png),
            caption=caption,
            reply_markup=markup,
        )
        table.hand_message_ids[user_id] = msg.message_id

    try:
        if mid is None or force_new:
            await _send_new()
        else:
            try:
                await context.bot.edit_message_media(
                    chat_id=user_id,
                    message_id=mid,
                    media=InputMediaPhoto(media=BytesIO(png), caption=caption),
                    reply_markup=markup,
                )
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    if markup is not None:
                        try:
                            await context.bot.edit_message_reply_markup(
                                chat_id=user_id,
                                message_id=mid,
                                reply_markup=markup,
                            )
                        except BadRequest:
                            pass
                    return
                # Old text message or missing — send a fresh photo
                await _send_new()
    except Exception as e:  # noqa: BLE001
        log.warning("hand DM failed user=%s: %s", user_id, type(e).__name__)
        # Fallback: text hand (emoji) if photo path fails
        try:
            await context.bot.send_message(
                chat_id=user_id,
                text=render.hand_dm_text(table, seat),
                reply_markup=markup,
            )
            return
        except Exception:
            pass
        warned = getattr(table, "_dm_warn_users", None)
        if warned is None:
            table._dm_warn_users = set()  # type: ignore[attr-defined]
            warned = table._dm_warn_users
        if user_id in warned:
            return
        warned.add(user_id)
        uname = context.bot.username
        try:
            from telegram import InlineKeyboardButton, InlineKeyboardMarkup

            rows = []
            if uname:
                rows.append(
                    [
                        InlineKeyboardButton(
                            "📱 Open private chat",
                            url=render.dm_link_button_url(uname),
                        )
                    ]
                )
            await context.bot.send_message(
                chat_id=table.chat_id,
                text=(
                    f"{table.seats[seat].display_name}: I can’t send your hand yet.\n"
                    "Tap the button once (opens private chat) — then tap My hand."
                ),
                reply_markup=InlineKeyboardMarkup(rows) if rows else None,
            )
        except Exception:
            pass


async def refresh_all_hands(
    context: ContextTypes.DEFAULT_TYPE, table: Table, *, force_new: bool = False
) -> None:
    if table.game is None:
        return
    for seat in range(4):
        await send_hand_dm(context, table, seat, force_new=force_new)


async def schedule_phase_timer(
    context: ContextTypes.DEFAULT_TYPE, table: Table
) -> None:
    g = table.game
    if g is None:
        timers(context).cancel(table.chat_id)
        return
    table.timer_token += 1
    if g.phase == GamePhase.PLAYING and g.has_drawn:
        # Never AFK-timeout bots — only humans
        if table.seats[g.turn_seat].is_bot:
            timers(context).cancel(table.chat_id)
            return
        timers(context).schedule(
            table, context, table.turn_timeout_s, on_turn_timeout
        )
    elif g.phase == GamePhase.CLAIM_WINDOW:
        timers(context).schedule(
            table, context, table.claim_timeout_s, on_claim_timeout
        )
    else:
        timers(context).cancel(table.chat_id)


async def announce_discard(
    context: ContextTypes.DEFAULT_TYPE,
    table: Table,
    seat: int,
    tile: Tile,
    *,
    with_photo: bool = True,
) -> None:
    """Record last throw and update one sticky discard photo (humans + bots)."""
    from io import BytesIO

    from telegram import InputMediaPhoto
    from telegram.error import BadRequest

    from .tile_art import render_single_tile_png

    table.last_discard = (seat, tile)
    if not with_photo:
        return
    name = table.name_for_seat(seat)
    caption = f"➡️ {name} threw  {tile.unicode()}  {tile.label()}"
    png = render_single_tile_png(tile)
    mid = getattr(table, "discard_message_id", None)
    try:
        if mid is None:
            msg = await context.bot.send_photo(
                chat_id=table.chat_id,
                photo=BytesIO(png),
                caption=caption,
            )
            table.discard_message_id = msg.message_id  # type: ignore[attr-defined]
        else:
            try:
                await context.bot.edit_message_media(
                    chat_id=table.chat_id,
                    message_id=mid,
                    media=InputMediaPhoto(media=BytesIO(png), caption=caption),
                )
            except BadRequest as e:
                if "message is not modified" in str(e).lower():
                    return
                msg = await context.bot.send_photo(
                    chat_id=table.chat_id,
                    photo=BytesIO(png),
                    caption=caption,
                )
                table.discard_message_id = msg.message_id  # type: ignore[attr-defined]
    except Exception:
        log.warning("announce_discard failed", exc_info=True)


async def ping_turn(context: ContextTypes.DEFAULT_TYPE, table: Table) -> None:
    """@ the human whose turn it is (or who can call) so phones notice."""
    import html

    from telegram.constants import ParseMode

    g = table.game
    if g is None:
        return

    async def _ping(user_id: int, display: str, reason: str) -> None:
        key = (user_id, reason, g.claim_window_id if reason == "call" else g.turn_seat)
        if getattr(table, "_last_ping_key", None) == key:
            return
        table._last_ping_key = key  # type: ignore[attr-defined]
        if display.startswith("@"):
            body = f"{display}"
        else:
            body = f'<a href="tg://user?id={user_id}">{html.escape(display)}</a>'
        try:
            await context.bot.send_message(
                chat_id=table.chat_id,
                text=f"👉 {body} — {reason} (open private chat with the bot)",
                parse_mode=ParseMode.HTML,
            )
        except Exception:
            try:
                await context.bot.send_message(
                    chat_id=table.chat_id,
                    text=f"👉 {display} — {reason} (private chat)",
                )
            except Exception:
                pass

    if g.phase == GamePhase.CLAIM_WINDOW:
        for s in table.seats:
            if s.is_bot or s.user_id is None:
                continue
            if g.pending_discard and s.seat_index == g.pending_discard[0]:
                continue
            if g.eligible_claims(s.seat_index):
                await _ping(s.user_id, s.display_name, "you can CALL (pon/chi/kan/ron)")
        return

    if g.phase == GamePhase.PLAYING and g.has_drawn:
        s = table.seats[g.turn_seat]
        if not s.is_bot and s.user_id is not None:
            await _ping(s.user_id, s.display_name, "your TURN to discard")


async def on_turn_timeout(table: Table, context: ContextTypes.DEFAULT_TYPE) -> None:
    g = table.game
    if g is None or g.phase != GamePhase.PLAYING or not g.has_drawn:
        return
    seat = g.turn_seat
    # Bot seats should never hit this — drive them instead of AFK-discard
    if table.seats[seat].is_bot:
        await after_game_action(context, table)
        return
    # Auto-discard last drawn tile, else last tile
    idx = g._index_of_last_draw(seat)
    if idx is None:
        idx = len(g.players[seat].hand.concealed) - 1
    if idx < 0:
        return
    tile = g.players[seat].hand.concealed[idx]
    ok = g.discard(seat, idx)
    if not ok:
        log.warning("timeout discard failed: %s", g.last_error)
        return
    table.last_discard = (seat, tile)
    try:
        await context.bot.send_message(
            chat_id=table.chat_id,
            text=(
                f"⏱ Timeout — {table.name_for_seat(seat)} auto-threw "
                f"{tile.unicode()} {tile.label()}"
            ),
        )
    except Exception:
        log.warning("timeout announce failed", exc_info=True)
    await after_game_action(context, table)


async def on_claim_timeout(table: Table, context: ContextTypes.DEFAULT_TYPE) -> None:
    g = table.game
    if g is None or g.phase != GamePhase.CLAIM_WINDOW:
        return
    g.force_timeout_passes()
    await context.bot.send_message(
        chat_id=table.chat_id,
        text="⏱ Claim timeout — AFK seats passed.",
    )
    await after_game_action(context, table)


async def deal_and_announce(context: ContextTypes.DEFAULT_TYPE, table: Table) -> None:
    table.deal_hand()
    if hasattr(table, "_dm_warn_users"):
        table._dm_warn_users.clear()  # type: ignore[attr-defined]
    mgr(context).persist(table)
    # One board update only — avoid spam "dealing..." + board + bot lines
    await after_game_action(context, table, force_new_hands=True)
    uname = context.bot.username
    if uname:
        from telegram import InlineKeyboardButton, InlineKeyboardMarkup
        from .render import dm_link_button_url

        await context.bot.send_message(
            chat_id=table.chat_id,
            text=(
                f"Hand #{table.hand_number} started.\n"
                "First time only: open the private chat and press Start once.\n"
                "After that, use My hand — no /start spam."
            ),
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "📱 Open private chat",
                            url=dm_link_button_url(uname),
                        )
                    ],
                    [
                        InlineKeyboardButton(
                            "🃏 My hand",
                            callback_data=f"t:{table.chat_id}:hand",
                        )
                    ],
                ]
            ),
        )


async def run_bot_loop(context: ContextTypes.DEFAULT_TYPE, table: Table) -> None:
    """Let bot seats act until a human must respond or the hand ends."""
    g = table.game
    if g is None:
        return
    rng = random.Random()
    for _ in range(64):
        if g.phase == GamePhase.ENDED:
            return
        if g.phase == GamePhase.CLAIM_WINDOW:
            bot_seats = [
                s.seat_index
                for s in table.seats
                if s.is_bot and s.seat_index not in g.claim_intents
            ]
            if g.pending_discard:
                bot_seats = [s for s in bot_seats if s != g.pending_discard[0]]
            if g.pending_chankan:
                bot_seats = [s for s in bot_seats if s != g.pending_chankan[0]]
            if not bot_seats:
                # Waiting on a human claim (or already resolved) — stop
                return
            for seat in list(bot_seats):
                if g.phase != GamePhase.CLAIM_WINDOW:
                    break
                if seat in g.claim_intents:
                    continue
                await asyncio.sleep(rng.uniform(0.15, 0.45))
                diff = BotDifficulty(
                    table.seats[seat].bot_difficulty or table.bot_difficulty
                )
                try:
                    decision = choose_claim_action(
                        g, seat, difficulty=diff, rng=rng
                    )
                    apply_claim_decision(g, seat, decision)
                except Exception:
                    log.exception("bot claim failed seat=%s", seat)
                    try:
                        g.register_claim(seat, ClaimType.PASS)
                    except Exception:
                        pass
            continue

        if (
            g.phase == GamePhase.PLAYING
            and g.has_drawn
            and table.seats[g.turn_seat].is_bot
        ):
            seat = g.turn_seat
            await asyncio.sleep(rng.uniform(0.2, 0.55))
            diff = BotDifficulty(
                table.seats[seat].bot_difficulty or table.bot_difficulty
            )
            try:
                decision = choose_turn_action(g, seat, difficulty=diff, rng=rng)
                label = apply_turn_decision(g, seat, decision)
            except Exception:
                log.exception("bot turn failed seat=%s — force discard", seat)
                hand = g.players[seat].hand.concealed
                idx = g._index_of_last_draw(seat)
                if idx is None:
                    idx = len(hand) - 1
                if idx >= 0 and g.discard(seat, idx):
                    label = "discard"
                else:
                    return
            if label in ("discard",) and g.players[seat].discards:
                thrown = g.players[seat].discards[-1]
                table.last_discard = (seat, thrown)
                await announce_discard(
                    context, table, seat, thrown, with_photo=True
                )
            elif label == "tsumo":
                try:
                    await context.bot.send_message(
                        chat_id=table.chat_id,
                        text=f"🏆 Self-draw — {table.name_for_seat(seat)}",
                    )
                except Exception:
                    pass
            continue

        return


async def after_game_action(
    context: ContextTypes.DEFAULT_TYPE,
    table: Table,
    *,
    force_new_hands: bool = False,
    already_locked: bool = False,
) -> None:
    """Call after any engine mutation that may change phase."""
    if already_locked:
        await _after_game_action_body(
            context, table, force_new_hands=force_new_hands
        )
        return
    async with mgr(context).lock_for(table.chat_id):
        await _after_game_action_body(
            context, table, force_new_hands=force_new_hands
        )


async def _after_game_action_body(
    context: ContextTypes.DEFAULT_TYPE,
    table: Table,
    *,
    force_new_hands: bool = False,
) -> None:
    g = table.game
    if g is None:
        return
    try:
        await run_bot_loop(context, table)
    except Exception:
        log.exception("run_bot_loop crashed chat_id=%s", table.chat_id)
    g = table.game
    if g is None:
        return
    mgr(context).persist(table)
    try:
        await refresh_board(context, table)
    except Exception:
        log.exception("refresh_board failed")
    try:
        await refresh_all_hands(context, table, force_new=force_new_hands)
    except Exception:
        log.exception("refresh_all_hands failed")
    if g.phase == GamePhase.ENDED:
        timers(context).cancel(table.chat_id)
        await announce_result(context, table)
        return
    try:
        await ping_turn(context, table)
    except Exception:
        log.exception("ping_turn failed")
    await schedule_phase_timer(context, table)


async def announce_result(context: ContextTypes.DEFAULT_TYPE, table: Table) -> None:
    from . import session_ops

    g = table.game
    if g is None or g.result is None:
        return
    r = g.result
    totals = session_ops.record_finished_hand(mgr(context).db_path, table)
    if r.winner is None:
        text = "Hand over — exhaustive draw."
    else:
        sc = r.score
        yaku = ", ".join(y.name for y in sc.yaku) if sc else "?"
        text = (
            f"Hand over — {table.name_for_seat(r.winner)} wins ({r.reason})!\n"
            f"{yaku}\n"
            f"{sc.han} fan · +{sc.gain}" if sc else yaku
        )
    if totals is not None:
        text += "\n\n" + session_ops.standings_text(mgr(context).db_path, table)
    await context.bot.send_message(
        chat_id=table.chat_id,
        text=text,
        reply_markup=keyboards.after_hand_keyboard(table.chat_id),
    )


def parse_tile_from_cb(suit_i: int, value: int, aka_i: int) -> Tile:
    return Tile(Suit(suit_i), value, aka=bool(aka_i))
