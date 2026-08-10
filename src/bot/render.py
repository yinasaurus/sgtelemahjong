"""Text rendering for group board and private hands."""

from __future__ import annotations

from mahjong.game import Game, GamePhase
from mahjong.tiles import Tile

from .state import WIND, Table


def fmt_tiles(tiles: list[Tile], *, unicode: bool = True) -> str:
    """Spaced tiles so Telegram renders them larger / more readable."""
    if not tiles:
        return "—"
    if unicode:
        # Wide gaps help emoji scale better on mobile
        return "  ".join(t.unicode() for t in tiles)
    return "  ".join(t.label() for t in tiles)


def fmt_tiles_big(tiles: list[Tile]) -> str:
    """Chunked unicode rows so Telegram draws tiles larger / easier to read."""
    if not tiles:
        return "—"
    chunks: list[str] = []
    # Fewer tiles per line → each emoji renders larger on mobile
    for i in range(0, len(tiles), 5):
        part = tiles[i : i + 5]
        top = "    ".join(t.unicode() for t in part)
        bot = "   ".join(f"{t.label():^4}" for t in part)
        chunks.append(f"{top}\n{bot}")
    return "\n\n".join(chunks)


def fmt_melds(game: Game, seat: int) -> str:
    melds = game.players[seat].hand.melds
    if not melds:
        return "—"
    parts = []
    for m in melds:
        parts.append(f"{m.type.value} {fmt_tiles(list(m.tiles))}")
    return " · ".join(parts)


def lobby_text(table: Table) -> str:
    lines = [
        "🀄 Lobby — start / join here in this group",
        "",
    ]
    for s in table.seats:
        if s.occupied:
            tag = "bot" if s.is_bot else "you/friend"
            lines.append(f"✅ {WIND[s.seat_index]}  {s.display_name}  ({tag})")
        else:
            lines.append(f"⬜ {WIND[s.seat_index]}  empty — friend taps Join")
    lines.append("")
    open_n = sum(1 for s in table.seats if not s.occupied)
    if open_n:
        lines.append(f"Friends: tap ✅ Join seat  ({open_n} open)")
    else:
        lines.append("Table full — dealing now…")
    lines.append("Your secret hand arrives in a private chat with the bot.")
    return "\n".join(lines)


def fmt_pond(discards: list[Tile]) -> str:
    """Readable pond: labels, latest marked [like this]."""
    if not discards:
        return "—"
    recent = discards[-8:]
    parts = [t.label() for t in recent]
    parts[-1] = f"[{parts[-1]}]"
    return "  ".join(parts)


def board_caption(table: Table) -> str:
    """Short caption under the visual board photo."""
    g = table.game
    assert g is not None
    wall = g.wall.remaining_live
    lines = [f"Wall left: {wall}   ·   Hand #{table.hand_number}"]
    if table.last_discard is not None:
        ds, tile = table.last_discard
        lines.append(
            f"Last: {tile.label()} by {table.name_for_seat(ds)}"
        )
    if g.phase == GamePhase.PLAYING and g.has_drawn:
        lines.append(f"Turn → {table.name_for_seat(g.turn_seat)}")
    elif g.phase == GamePhase.CLAIM_WINDOW:
        lines.append("Call window — check DM if you can pon/chi/kan/ron")
    return "\n".join(lines)


def board_text(table: Table) -> str:
    g = table.game
    if g is None:
        return lobby_text(table)
    lines = [
        f"🀄 Hand #{table.hand_number}   ·   {WIND[g.round_wind]} round",
        f"Dealer {table.name_for_seat(g.dealer)}   ·   Wall {g.wall.remaining_live}",
        "(Singapore Mahjong · flowers & animals)",
    ]
    if table.last_discard is not None:
        ds, tile = table.last_discard
        lines.append(
            f"➡️ Last throw  {tile.unicode()} {tile.label()}  ·  {table.name_for_seat(ds)}"
        )
    lines.append("")
    for seat in range(4):
        p = g.players[seat]
        turn = "👉 " if seat == g.turn_seat and g.phase == GamePhase.PLAYING else "   "
        riichi = ""
        lines.append(f"{turn}{WIND[seat]}  {table.seats[seat].display_name}{riichi}")
        bonus = []
        if p.flowers:
            bonus.append("🌸" + "".join(t.unicode() for t in p.flowers))
        if p.animals:
            bonus.append("".join(t.unicode() for t in p.animals))
        if bonus:
            lines.append("   " + "  ".join(bonus))
        pts = getattr(p, "points", 0)
        if pts:
            lines.append(f"   pts {pts:+d}")
        if p.hand.melds:
            lines.append(f"      Melds  {fmt_melds(g, seat)}")
        lines.append(f"      Pond   {fmt_pond(p.discards)}")
    lines.append("")
    if g.phase == GamePhase.CLAIM_WINDOW and g.pending_discard:
        ds, tile = g.pending_discard
        lines.append(
            f"🔔 Just thrown  {tile.unicode()}  {tile.label()}  by {table.name_for_seat(ds)}"
        )
        lines.append("Call? Check private chat buttons — or wait.")
    elif g.phase == GamePhase.CLAIM_WINDOW and g.pending_chankan:
        ks, tile = g.pending_chankan
        lines.append(f"🔔 Kan add  {tile.unicode()}  — rob? (DM)")
    elif g.phase == GamePhase.PLAYING:
        lines.append(f"Turn: {table.name_for_seat(g.turn_seat)}")
        if table.seats[g.turn_seat].is_bot:
            lines.append("Bot is thinking…")
        else:
            lines.append("Your move is in the private chat ↓")
    elif g.phase == GamePhase.ENDED and g.result:
        r = g.result
        if r.winner is None:
            lines.append("Draw — no winner.")
        else:
            sc = r.score
            yaku = ", ".join(y.name for y in sc.yaku) if sc else "?"
            lines.append(f"🏆 {table.name_for_seat(r.winner)} wins — {yaku}")
            if sc:
                lines.append(f"{sc.han} fan · +{sc.gain}")
    return "\n".join(lines)


def hand_dm_caption(table: Table, seat: int) -> str:
    """Short caption under the DM photo (overview + your hand are in the image)."""
    g = table.game
    assert g is not None
    p = g.players[seat]
    lines = [
        f"Table + your hand  ·  {WIND[seat]}  ·  Hand #{table.hand_number}",
        f"Wall left: {g.wall.remaining_live}",
    ]
    # Compact text backup of others (in case image is small on phone)
    bits = []
    for s in range(4):
        pl = g.players[s]
        tag = "you" if s == seat else table.seats[s].display_name[:12]
        n = len(pl.hand.concealed)
        calls = len(pl.hand.melds)
        bits.append(f"{WIND[s]} {tag}:{n}t/{calls}c")
    lines.append(" · ".join(bits))
    if table.last_discard is not None:
        ds, tile = table.last_discard
        who = "you" if ds == seat else table.name_for_seat(ds)
        lines.append(f"Last throw: {tile.label()} ({who})")
    if g.phase == GamePhase.PLAYING and g.turn_seat == seat and g.has_drawn:
        lines.append("Your turn — tap a number button below.")
    elif g.phase == GamePhase.CLAIM_WINDOW:
        elig = g.eligible_claims(seat)
        if elig:
            lines.append(
                "You can call: "
                + ", ".join(sorted(c.value.upper() for c in elig))
                + " — buttons below."
            )
        else:
            lines.append("Waiting…")
    else:
        lines.append("Waiting for your turn…")
    if p.flowers or p.animals:
        bits = []
        if p.flowers:
            bits.append("🌸" + "".join(t.unicode() for t in p.flowers))
        if p.animals:
            bits.append("".join(t.unicode() for t in p.animals))
        lines.append("Bonus: " + " ".join(bits))
    if g.is_furiten(seat):
        lines.append("⚠ Missed a win — cannot Game on that tile type now.")
    return "\n".join(lines)


def hand_dm_text(table: Table, seat: int) -> str:
    """Fallback text if photo send fails."""
    g = table.game
    assert g is not None
    p = g.players[seat]
    tiles = list(p.hand.concealed)
    return hand_dm_caption(table, seat) + "\n\n" + fmt_tiles_big(tiles)


def dm_link_button_url(bot_username: str) -> str:
    # Plain profile link opens the chat WITHOUT re-sending /start.
    # (?start=…) would spam /start every tap — only needed the very first time,
    # and Telegram already shows a Start button for brand-new users.
    return f"https://t.me/{bot_username}"
