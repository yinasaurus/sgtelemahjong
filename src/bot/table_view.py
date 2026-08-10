"""Shared table overview for group board + private DM (melds, ponds, counts)."""

from __future__ import annotations

import io

from PIL import Image, ImageDraw, ImageFont

from mahjong.game import GamePhase
from mahjong.tiles import Tile

from .state import WIND, Table
from .tile_art import TW, TH, BG, draw_tile, _load_face, _tile_filename, render_hand_png

FELT = BG
FELT_DARK = (20, 52, 36)
INK = (245, 245, 240)
INK_DIM = (180, 200, 185)
GOLD = (255, 220, 120)


def _font(size: int, *, bold: bool = False) -> ImageFont.ImageFont:
    candidates = [
        r"C:\Windows\Fonts\segoeuib.ttf" if bold else r"C:\Windows\Fonts\segoeui.ttf",
        r"C:\Windows\Fonts\arialbd.ttf" if bold else r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\msyh.ttc",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size=size)
        except OSError:
            continue
    return ImageFont.load_default()


def mini_tile(tile: Tile, w: int = 34, h: int = 46) -> Image.Image:
    fn = _tile_filename(tile)
    if fn is None:
        return draw_tile(tile).resize((w, h), Image.Resampling.LANCZOS)
    return _load_face(fn).resize((w, h), Image.Resampling.LANCZOS)


def _paste_row(
    canvas: Image.Image,
    tiles: list[Tile],
    x: int,
    y: int,
    *,
    tw: int = 34,
    th: int = 46,
    gap: int = 4,
    highlight_last: bool = False,
) -> int:
    """Paste a row of mini tiles; return x after last tile."""
    d = ImageDraw.Draw(canvas)
    for i, t in enumerate(tiles):
        mt = mini_tile(t, tw, th)
        canvas.paste(mt, (x, y), mt)
        if highlight_last and i == len(tiles) - 1:
            d.rectangle((x - 1, y - 1, x + tw, y + th), outline=GOLD, width=2)
        x += tw + gap
    return x


def render_board_png(table: Table) -> bytes:
    """Group board: wall, last throw, all ponds + melds + hand sizes."""
    g = table.game
    assert g is not None

    W, H = 960, 820
    img = Image.new("RGB", (W, H), FELT)
    d = ImageDraw.Draw(img)
    for y in range(0, H, 6):
        d.line((0, y, W, y), fill=FELT_DARK)

    font_lg = _font(26, bold=True)
    font_md = _font(18, bold=True)
    font_sm = _font(15)
    font_xs = _font(13)

    d.text(
        (20, 12),
        f"Hand #{table.hand_number}  ·  Singapore  ·  {WIND[g.round_wind]} round",
        font=font_lg,
        fill=INK,
    )
    d.text((20, 46), f"Wall left: {g.wall.remaining_live}", font=font_lg, fill=GOLD)
    d.text(
        (280, 50),
        f"Dealer {table.name_for_seat(g.dealer)}",
        font=font_sm,
        fill=INK_DIM,
    )
    d.text((20, 88), "Flowers & animals expose for fan (no dora)", font=font_sm, fill=INK_DIM)

    if table.last_discard is not None:
        ds, tile = table.last_discard
        d.text((720, 12), "LAST THROW", font=font_md, fill=GOLD)
        big = draw_tile(tile).resize((100, 134), Image.Resampling.LANCZOS)
        img.paste(big, (740, 40), big)
        d.text((720, 180), table.name_for_seat(ds)[:20], font=font_xs, fill=INK)

    # Seat blocks — taller for melds + pond
    y0 = 200
    row_h = 140
    for seat in range(4):
        y = y0 + seat * row_h
        p = g.players[seat]
        is_turn = (
            seat == g.turn_seat and g.phase == GamePhase.PLAYING and g.has_drawn
        )
        bar = (40, 95, 58) if is_turn else (24, 58, 40)
        d.rounded_rectangle((12, y, W - 12, y + row_h - 10), radius=12, fill=bar)

        n_hid = len(p.hand.concealed)
        mark = "👉 " if is_turn else ""
        title = (
            f"{mark}{WIND[seat]}  {table.seats[seat].display_name}"
            f"   ·   {n_hid} in hand"
        )
        d.text((24, y + 6), title, font=font_md, fill=GOLD if is_turn else INK)
        bonus_bits = []
        if p.flowers:
            bonus_bits.append("F:" + "".join(t.unicode() for t in p.flowers))
        if p.animals:
            bonus_bits.append("A:" + "".join(t.unicode() for t in p.animals))
        if bonus_bits:
            d.text((24, y + 24), "  ".join(bonus_bits), font=font_xs, fill=GOLD)

        # Melds as real tiles
        mx = 24
        my = y + 36
        if p.hand.melds:
            d.text((mx, my), "Calls:", font=font_xs, fill=INK_DIM)
            mx = 78
            for m in p.hand.melds:
                d.text((mx, my + 12), m.type.value[:3], font=font_xs, fill=INK_DIM)
                mx += 28
                mx = _paste_row(img, list(m.tiles), mx, my, tw=28, th=38, gap=2)
                mx += 10
        else:
            d.text((24, my + 8), "Calls: none", font=font_xs, fill=INK_DIM)

        # Pond
        pond = p.discards[-12:]
        d.text((24, y + 84), "Thrown:", font=font_xs, fill=INK_DIM)
        if pond:
            hi = bool(
                table.last_discard
                and table.last_discard[0] == seat
            )
            _paste_row(
                img,
                pond,
                90,
                y + 78,
                tw=30,
                th=40,
                gap=3,
                highlight_last=hi,
            )
        else:
            d.text((90, y + 88), "—", font=font_xs, fill=INK_DIM)

    fy = H - 40
    if g.phase == GamePhase.CLAIM_WINDOW and g.pending_discard:
        ds, tile = g.pending_discard
        msg = f"Call on {tile.label()} by {table.name_for_seat(ds)} — check DM"
    elif g.phase == GamePhase.PLAYING:
        msg = f"Turn: {table.name_for_seat(g.turn_seat)}"
    elif g.phase == GamePhase.ENDED:
        msg = "Hand over"
    else:
        msg = ""
    d.text((20, fy), msg, font=font_md, fill=GOLD)

    bio = io.BytesIO()
    img.save(bio, format="PNG", optimize=True)
    return bio.getvalue()


def render_dm_view_png(
    table: Table,
    seat: int,
    *,
    separate_last: bool = False,
) -> bytes:
    """
    Private view: table summary (everyone's throws/calls/hand size)
    + your own hand with numbers.
    """
    g = table.game
    assert g is not None

    # Overview strip
    ov_h = 340
    W = 920
    overview = Image.new("RGB", (W, ov_h), FELT)
    d = ImageDraw.Draw(overview)
    for y in range(0, ov_h, 6):
        d.line((0, y, W, y), fill=FELT_DARK)

    font_md = _font(17, bold=True)
    font_sm = _font(14)
    font_xs = _font(12)

    d.text((16, 8), "TABLE (what everyone has)", font=font_md, fill=GOLD)
    d.text(
        (320, 10),
        f"Wall {g.wall.remaining_live} left",
        font=font_sm,
        fill=INK,
    )

    if table.last_discard is not None:
        ds, tile = table.last_discard
        d.text((520, 8), "Just thrown →", font=font_sm, fill=GOLD)
        big = draw_tile(tile).resize((56, 76), Image.Resampling.LANCZOS)
        overview.paste(big, (640, 4), big)
        d.text((710, 30), f"{table.name_for_seat(ds)}", font=font_xs, fill=INK)
        d.text((710, 48), tile.label(), font=font_md, fill=GOLD)

    y = 70
    for s in range(4):
        p = g.players[s]
        you = " (YOU)" if s == seat else ""
        n_hid = len(p.hand.concealed)
        line = f"{WIND[s]} {table.seats[s].display_name}{you}  ·  {n_hid} tiles"
        if p.flowers or p.animals:
            line += "  " + "".join(t.unicode() for t in p.flowers + p.animals)
        d.text((16, y), line, font=font_sm, fill=GOLD if s == seat else INK)

        mx = 16
        my = y + 22
        if p.hand.melds:
            for m in p.hand.melds:
                d.text((mx, my + 8), m.type.value[:3], font=font_xs, fill=INK_DIM)
                mx += 26
                mx = _paste_row(
                    overview, list(m.tiles), mx, my, tw=26, th=36, gap=1
                )
                mx += 8
        else:
            d.text((mx, my + 8), "no calls", font=font_xs, fill=INK_DIM)
            mx = 100

        pond = p.discards[-8:]
        d.text((mx + 8, my + 8), "discards:", font=font_xs, fill=INK_DIM)
        if pond:
            _paste_row(
                overview,
                pond,
                mx + 70,
                my,
                tw=26,
                th=36,
                gap=2,
                highlight_last=bool(
                    table.last_discard and table.last_discard[0] == s
                ),
            )
        y += 66

    # Own hand
    tiles = list(g.players[seat].hand.concealed)
    hand_bytes = render_hand_png(
        tiles, separate_last=separate_last, show_indices=True
    )
    hand_img = Image.open(io.BytesIO(hand_bytes)).convert("RGB")

    # Label strip between
    label_h = 36
    total_h = ov_h + label_h + hand_img.height
    total_w = max(W, hand_img.width)
    out = Image.new("RGB", (total_w, total_h), FELT)
    out.paste(overview, (0, 0))
    ld = ImageDraw.Draw(out)
    ld.text(
        (16, ov_h + 6),
        "YOUR HAND (secret) — tap button with same number",
        font=_font(16, bold=True),
        fill=GOLD,
    )
    out.paste(hand_img, ((total_w - hand_img.width) // 2, ov_h + label_h))

    bio = io.BytesIO()
    out.save(bio, format="PNG", optimize=True)
    return bio.getvalue()
