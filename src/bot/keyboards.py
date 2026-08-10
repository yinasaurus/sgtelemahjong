"""Inline keyboards for discard / claims / actions."""

from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from mahjong.game import ClaimType, Game, GamePhase

from .state import Table


def private_start_keyboard(bot_username: str | None) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    if bot_username:
        rows.append(
            [
                InlineKeyboardButton(
                    "1️⃣ Add me to a group",
                    url=f"https://t.me/{bot_username}?startgroup=true",
                )
            ]
        )
    rows.append(
        [
            InlineKeyboardButton("❓ How to start", callback_data="m:0:howto"),
            InlineKeyboardButton("📖 Rules book", callback_data="m:0:rules:0"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def group_menu_keyboard(chat_id: int, *, has_table: bool) -> InlineKeyboardMarkup:
    if has_table:
        return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton("✅ Join", callback_data=f"t:{chat_id}:join"),
                    InlineKeyboardButton("🚪 Leave", callback_data=f"t:{chat_id}:leave"),
                ],
                [
                    InlineKeyboardButton("🀄 Board", callback_data=f"t:{chat_id}:table"),
                    InlineKeyboardButton(
                        "📊 Scores", callback_data=f"t:{chat_id}:standings"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🃏 My hand", callback_data=f"t:{chat_id}:hand"
                    ),
                    InlineKeyboardButton(
                        "📜 History", callback_data=f"m:{chat_id}:history"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "🏁 End session", callback_data=f"t:{chat_id}:endsession"
                    ),
                ],
                [
                    InlineKeyboardButton(
                        "❓ How to start", callback_data=f"m:{chat_id}:howto"
                    ),
                    InlineKeyboardButton(
                        "📖 Rules", callback_data=f"m:{chat_id}:rules:0"
                    ),
                ],
            ]
        )
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    "▶️ Play solo (3 easy bots)",
                    callback_data=f"m:{chat_id}:new:3:easy",
                )
            ],
            [
                InlineKeyboardButton(
                    "▶️ Play solo (3 normal bots)",
                    callback_data=f"m:{chat_id}:new:3:normal",
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 3 people + 1 bot",
                    callback_data=f"m:{chat_id}:new:1:easy",
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 2 people + 2 bots",
                    callback_data=f"m:{chat_id}:new:2:easy",
                )
            ],
            [
                InlineKeyboardButton(
                    "👥 4 people (no bots)",
                    callback_data=f"m:{chat_id}:new:0:easy",
                )
            ],
            [
                InlineKeyboardButton(
                    "❓ How to start", callback_data=f"m:{chat_id}:howto"
                ),
                InlineKeyboardButton(
                    "📖 Rules book", callback_data=f"m:{chat_id}:rules:0"
                ),
            ],
            [
                InlineKeyboardButton("📜 History", callback_data=f"m:{chat_id}:history"),
            ],
        ]
    )


def lobby_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Join seat", callback_data=f"t:{chat_id}:join"),
                InlineKeyboardButton("🚪 Leave", callback_data=f"t:{chat_id}:leave"),
            ],
            [
                InlineKeyboardButton("🔄 Refresh", callback_data=f"t:{chat_id}:table"),
                InlineKeyboardButton(
                    "📊 Scores", callback_data=f"t:{chat_id}:standings"
                ),
            ],
            [
                InlineKeyboardButton(
                    "🏁 End session", callback_data=f"t:{chat_id}:endsession"
                ),
            ],
        ]
    )


def discard_keyboard(table: Table, seat: int) -> InlineKeyboardMarkup:
    g = table.game
    assert g is not None
    tiles = g.players[seat].hand.concealed
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, t in enumerate(tiles):
        # Number matches the badge on the hand photo
        row.append(
            InlineKeyboardButton(
                f"{i + 1}·{t.label()}",
                callback_data=f"d:{table.chat_id}:{seat}:{i}",
            )
        )
        if len(row) == 4:
            rows.append(row)
            row = []
    if row:
        rows.append(row)

    actions: list[InlineKeyboardButton] = []
    if g.can_tsumo(seat):
        actions.append(
            InlineKeyboardButton(
                "WIN (self-draw)", callback_data=f"a:{table.chat_id}:{seat}:tsumo"
            )
        )
    # ankan options
    seen: set[tuple] = set()
    for t in tiles:
        key = (t.suit, t.value)
        if key in seen:
            continue
        seen.add(key)
        if g.can_ankan(seat, t):
            actions.append(
                InlineKeyboardButton(
                    f"Closed kan {t.label()}",
                    callback_data=f"k:{table.chat_id}:{seat}:ankan:{t.suit}:{t.value}",
                )
            )
        if g.can_shouminkan(seat, t):
            actions.append(
                InlineKeyboardButton(
                    f"Add kan {t.label()}",
                    callback_data=f"k:{table.chat_id}:{seat}:shou:{t.suit}:{t.value}",
                )
            )
    if actions:
        # chunk actions
        for i in range(0, len(actions), 3):
            rows.append(actions[i : i + 3])
    return InlineKeyboardMarkup(rows)


def riichi_discard_keyboard(table: Table, seat: int) -> InlineKeyboardMarkup:
    """After tapping Riichi — choose which tile to discard with the declaration."""
    g = table.game
    assert g is not None
    from mahjong.hand import is_tenpai

    tiles = g.players[seat].hand.concealed
    rows: list[list[InlineKeyboardButton]] = []
    row: list[InlineKeyboardButton] = []
    for i, t in enumerate(tiles):
        left = tiles[:i] + tiles[i + 1 :]
        if not is_tenpai(left):
            continue
        row.append(
            InlineKeyboardButton(
                f"★{i + 1}·{t.label()}",
                callback_data=f"r:{table.chat_id}:{seat}:{i}",
            )
        )
        if len(row) == 3:
            rows.append(row)
            row = []
    if row:
        rows.append(row)
    rows.append(
        [
            InlineKeyboardButton(
                "Cancel", callback_data=f"a:{table.chat_id}:{seat}:cancel_riichi"
            )
        ]
    )
    return InlineKeyboardMarkup(rows)


def claim_keyboard(table: Table, seat: int) -> InlineKeyboardMarkup:
    g = table.game
    assert g is not None
    elig = g.eligible_claims(seat)
    tile_u = ""
    if g.pending_discard:
        tile_u = f" {g.pending_discard[1].unicode()}"
    elif g.pending_chankan:
        tile_u = f" {g.pending_chankan[1].unicode()}"
    rows: list[list[InlineKeyboardButton]] = []
    btns: list[InlineKeyboardButton] = []
    labels = {
        ClaimType.RON: f"WIN (game){tile_u}",
        ClaimType.KAN: f"KONG{tile_u}",
        ClaimType.PON: f"PONG{tile_u}",
        ClaimType.CHI: f"CHOW{tile_u}",
    }
    for kind in (ClaimType.RON, ClaimType.KAN, ClaimType.PON, ClaimType.CHI):
        if kind in elig:
            btns.append(
                InlineKeyboardButton(
                    labels[kind],
                    callback_data=f"c:{table.chat_id}:{seat}:{kind.value}",
                )
            )
    btns.append(
        InlineKeyboardButton(
            "Skip call", callback_data=f"c:{table.chat_id}:{seat}:pass"
        )
    )
    rows.append(btns)
    if ClaimType.CHI in elig and g.pending_discard:
        _, tile = g.pending_discard
        for a, b in g.chi_options(seat, tile):
            rows.append(
                [
                    InlineKeyboardButton(
                        f"Chow {a.unicode()}{b.unicode()} {a.label()}+{b.label()}",
                        callback_data=(
                            f"chi:{table.chat_id}:{seat}:"
                            f"{int(a.suit)}:{a.value}:{int(a.aka)}:"
                            f"{int(b.suit)}:{b.value}:{int(b.aka)}"
                        ),
                    )
                ]
            )
    return InlineKeyboardMarkup(rows)


def after_hand_keyboard(chat_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("Next hand", callback_data=f"t:{chat_id}:nexthand"),
                InlineKeyboardButton(
                    "End session", callback_data=f"t:{chat_id}:endsession"
                ),
            ],
            [
                InlineKeyboardButton("Standings", callback_data=f"t:{chat_id}:standings"),
            ],
        ]
    )


def action_keyboard_for(table: Table, user_id: int) -> InlineKeyboardMarkup | None:
    g = table.game
    if g is None:
        return lobby_keyboard(table.chat_id)
    seat_obj = table.seat_of_user(user_id)
    if seat_obj is None:
        return None
    seat = seat_obj.seat_index
    if g.phase == GamePhase.CLAIM_WINDOW:
        if g.eligible_claims(seat) or (
            g.pending_discard and seat != g.pending_discard[0]
        ) or (g.pending_chankan and seat != g.pending_chankan[0]):
            # always offer pass during claim window if not discarder
            if (g.pending_discard and seat != g.pending_discard[0]) or (
                g.pending_chankan and seat != g.pending_chankan[0]
            ):
                return claim_keyboard(table, seat)
    if g.phase == GamePhase.PLAYING and g.turn_seat == seat and g.has_drawn:
        return discard_keyboard(table, seat)
    if g.phase == GamePhase.ENDED:
        return after_hand_keyboard(table.chat_id)
    return None
