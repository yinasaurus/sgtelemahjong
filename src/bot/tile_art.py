"""Render hand photos using real FluffyStuff riichi tile art (CC0)."""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from mahjong.tiles import Suit, Tile

# Display size (source art is scaled down for Telegram)
TW, TH = 110, 150
GAP = 8
PAD = 14
BG = (28, 72, 48)  # felt
INDEX_BG = (25, 25, 25, 210)

# assets/tiles next to project root (…/tele mahjong/assets/tiles)
_TILE_DIR = Path(__file__).resolve().parents[2] / "assets" / "tiles"


def _tile_filename(tile: Tile) -> str | None:
    """FluffyStuff filename, or None for flowers/animals (drawn separately)."""
    if tile.suit == Suit.MAN:
        return f"Man{tile.value}.png"
    if tile.suit == Suit.PIN:
        return f"Pin{tile.value}.png"
    if tile.suit == Suit.SOU:
        return f"Sou{tile.value}.png"
    if tile.suit == Suit.WIND:
        return ("Ton.png", "Nan.png", "Shaa.png", "Pei.png")[tile.value]
    if tile.suit == Suit.DRAGON:
        return ("Haku.png", "Hatsu.png", "Chun.png")[tile.value]
    return None


def _draw_bonus_face(tile: Tile) -> Image.Image:
    """Simple face for flowers / animals (no FluffyStuff art)."""
    front = _load_front().copy().resize((TW, TH), Image.Resampling.LANCZOS)
    d = ImageDraw.Draw(front)
    label = tile.unicode()
    short = tile.label()[:4]
    # big emoji-ish / unicode centre
    try:
        big = ImageFont.truetype(r"C:\Windows\Fonts\seguiemj.ttf", 42)
        small = ImageFont.truetype(r"C:\Windows\Fonts\arialbd.ttf", 14)
    except OSError:
        big = ImageFont.load_default()
        small = big
    bbox = d.textbbox((0, 0), label, font=big)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    d.text(((TW - tw) // 2 - bbox[0], (TH - th) // 2 - bbox[1] - 8), label, font=big, fill=(40, 40, 40, 255))
    sb = d.textbbox((0, 0), short, font=small)
    stw = sb[2] - sb[0]
    d.text(((TW - stw) // 2 - sb[0], TH - 28), short, font=small, fill=(90, 40, 40, 255))
    return front


@lru_cache(maxsize=64)
def _load_front() -> Image.Image:
    path = _TILE_DIR / "Front.png"
    if path.is_file():
        return Image.open(path).convert("RGBA")
    return Image.new("RGBA", (600, 800), (245, 240, 230, 255))


@lru_cache(maxsize=64)
def _load_face(filename: str) -> Image.Image:
    """Compose FluffyStuff symbol layer onto the physical tile front."""
    front = _load_front().copy()
    path = _TILE_DIR / filename
    if path.is_file():
        symbol = Image.open(path).convert("RGBA")
        if symbol.size != front.size:
            symbol = symbol.resize(front.size, Image.Resampling.LANCZOS)
        front.alpha_composite(symbol)
    return front.resize((TW, TH), Image.Resampling.LANCZOS)


def _index_font() -> ImageFont.ImageFont:
    for path in (
        r"C:\Windows\Fonts\arialbd.ttf",
        r"C:\Windows\Fonts\arial.ttf",
        r"C:\Windows\Fonts\segoeui.ttf",
    ):
        try:
            return ImageFont.truetype(path, 15)
        except OSError:
            continue
    return ImageFont.load_default()


def draw_tile(tile: Tile, *, index: int | None = None) -> Image.Image:
    fn = _tile_filename(tile)
    face = _draw_bonus_face(tile) if fn is None else _load_face(fn).copy()
    # Soft drop shadow under the real artwork
    canvas = Image.new("RGBA", (TW + 6, TH + 8), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (TW, TH), (0, 0, 0, 0))
    sd = ImageDraw.Draw(shadow)
    sd.rounded_rectangle((0, 0, TW - 1, TH - 1), radius=10, fill=(0, 0, 0, 70))
    canvas.paste(shadow, (4, 6), shadow)
    canvas.paste(face, (0, 0), face)

    if index is not None:
        d = ImageDraw.Draw(canvas)
        label = str(index + 1)
        font = _index_font()
        # Badge bottom-left so it doesn't cover suit art much
        bx0, by0, bx1, by1 = 4, TH - 22, 26, TH - 4
        d.rounded_rectangle((bx0, by0, bx1, by1), radius=5, fill=INDEX_BG)
        bbox = d.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        x = bx0 + (bx1 - bx0 - tw) // 2 - bbox[0]
        y = by0 + (by1 - by0 - th) // 2 - bbox[1]
        d.text((x, y), label, font=font, fill=(255, 255, 255, 255))

    return canvas


def render_single_tile_png(tile: Tile, *, scale: float = 1.35) -> bytes:
    """One large tile on felt — used when announcing a discard."""
    w = int(TW * scale)
    h = int(TH * scale)
    fn = _tile_filename(tile)
    base = _draw_bonus_face(tile) if fn is None else _load_face(fn)
    face = base.resize((w, h), Image.Resampling.LANCZOS)
    pad = 20
    canvas = Image.new("RGB", (w + pad * 2 + 8, h + pad * 2 + 10), BG)
    shadow = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ImageDraw.Draw(shadow).rounded_rectangle(
        (0, 0, w - 1, h - 1), radius=12, fill=(0, 0, 0, 80)
    )
    canvas.paste(shadow, (pad + 5, pad + 7), shadow)
    canvas.paste(face, (pad, pad), face)
    bio = io.BytesIO()
    canvas.save(bio, format="PNG", optimize=True)
    return bio.getvalue()


def render_hand_png(
    tiles: list[Tile],
    *,
    separate_last: bool = False,
    show_indices: bool = True,
) -> bytes:
    """Return PNG bytes of a hand row (optionally split drawn tile)."""
    cell_w, cell_h = TW + 6, TH + 8
    if not tiles:
        img = Image.new("RGB", (320, cell_h + PAD * 2), BG)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        return bio.getvalue()

    n = len(tiles)
    split = separate_last and n >= 2
    left_n = n - 1 if split else n
    width = PAD * 2 + left_n * cell_w + max(0, left_n - 1) * GAP
    if split:
        width += GAP * 3 + cell_w
    height = PAD * 2 + cell_h

    canvas = Image.new("RGB", (max(width, 200), height), BG)
    # subtle felt grain
    grain = Image.new("RGB", canvas.size, BG)
    gdraw = ImageDraw.Draw(grain)
    for y in range(0, height, 4):
        shade = 24 + (y % 12)
        gdraw.line((0, y, width, y), fill=(28, 72 + shade // 3, 48))
    canvas = Image.blend(canvas, grain, 0.15)

    x = PAD
    for i, t in enumerate(tiles):
        if split and i == left_n:
            x += GAP * 2
        tile_img = draw_tile(t, index=i if show_indices else None)
        canvas.paste(tile_img, (x, PAD), tile_img)
        x += cell_w + GAP

    bio = io.BytesIO()
    canvas.save(bio, format="PNG", optimize=True)
    return bio.getvalue()
