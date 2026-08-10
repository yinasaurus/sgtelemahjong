"""Yaku detection for the Phase-1 subset (see RULES.md)."""

from __future__ import annotations

from dataclasses import dataclass, field

from .hand import (
    Hand,
    Meld,
    MeldType,
    is_chiitoitsu,
    is_kokushi,
    standard_agari_partitions,
)
from .tiles import Suit, Tile, counts_by_tile


@dataclass(frozen=True)
class YakuItem:
    name: str
    han: int
    yakuman: bool = False


@dataclass
class WinContext:
    """Context needed to evaluate yaku for a completed win."""

    hand: Hand
    winning_tile: Tile
    # True if the winning tile is part of concealed (tsumo / ron added already)
    from_ron: bool
    riichi: bool = False
    double_riichi: bool = False
    ippatsu: bool = False
    menzen: bool = True
    seat_wind: int = 0  # 0=E..3=N
    round_wind: int = 0
    tsumo: bool = True
    haitei: bool = False
    houtei: bool = False
    rinshan: bool = False
    chankan: bool = False
    dora_tiles: list[Tile] = field(default_factory=list)  # actual dora tile types
    ura_dora_tiles: list[Tile] = field(default_factory=list)
    aka_count: int = 0


def _suited_values(tiles: list[Tile], suit: Suit) -> list[int]:
    return sorted(t.value for t in tiles if t.suit == suit)


def _all_tiles_for_yaku(ctx: WinContext) -> list[Tile]:
    return ctx.hand.all_tiles()


def _concealed_plus_win(ctx: WinContext) -> list[Tile]:
    return list(ctx.hand.concealed)


def count_dora_hits(tiles: list[Tile], dora_types: list[Tile]) -> int:
    hits = 0
    for t in tiles:
        for d in dora_types:
            if t.same_tile(d):
                hits += 1
    return hits


def count_aka(tiles: list[Tile]) -> int:
    return sum(1 for t in tiles if t.aka)


def _is_tanyao(tiles: list[Tile]) -> bool:
    return all(t.is_simple for t in tiles)


def _yakuhai_hans(ctx: WinContext, tiles: list[Tile], open_melds: list[Meld]) -> list[YakuItem]:
    out: list[YakuItem] = []
    # Count triplets/quads of dragons and seat/round winds
    def has_kotsu(suit: Suit, value: int) -> bool:
        # open melds
        for m in open_melds:
            if m.type in (MeldType.PON, MeldType.MINKAN, MeldType.ANKAN):
                if m.tiles[0].suit == suit and m.tiles[0].value == value:
                    return True
        # closed: look at partitions later — use counts in full hand
        c = counts_by_tile(tiles)
        return c.get((suit, value), 0) >= 3

    for d, name in ((0, "Yakuhai: Haku"), (1, "Yakuhai: Hatsu"), (2, "Yakuhai: Chun")):
        if has_kotsu(Suit.DRAGON, d):
            out.append(YakuItem(name, 1))
    if has_kotsu(Suit.WIND, ctx.seat_wind):
        out.append(YakuItem("Yakuhai: Seat wind", 1))
    if has_kotsu(Suit.WIND, ctx.round_wind):
        # If seat == round (dealer in East round), both apply (2 han)
        out.append(YakuItem("Yakuhai: Round wind", 1))
    return out


def _partition_flags(
    pair: tuple[Suit, int],
    mentsu: list[tuple[str, tuple[tuple[Suit, int], ...]]],
    ctx: WinContext,
) -> dict:
    """Derive pinfu / iipeikou / sanshoku / ittsuu / chanta / etc. flags for one partition."""
    flags = {
        "pinfu": False,
        "iipeikou": 0,
        "ryanpeikou": False,
        "sanshoku": False,
        "ittsuu": False,
        "chanta": False,
        "junchan": False,
        "toitoi": False,
        "sanankou": False,
        "honitsu": False,
        "chinitsu": False,
    }
    # toitoi
    flags["toitoi"] = all(kind == "pon" for kind, _ in mentsu) and all(
        m.type != MeldType.CHI for m in ctx.hand.melds
    )
    # include open pons
    if ctx.hand.melds:
        open_chi = any(m.type == MeldType.CHI for m in ctx.hand.melds)
        open_pons = all(
            m.type in (MeldType.PON, MeldType.MINKAN, MeldType.ANKAN)
            for m in ctx.hand.melds
        )
        flags["toitoi"] = (not open_chi) and all(k == "pon" for k, _ in mentsu) and (
            open_pons or not ctx.hand.melds
        )

    # iipeikou: two identical chi in concealed mentsu
    chis = [keys for kind, keys in mentsu if kind == "chi"]
    dup = 0
    seen: dict[tuple, int] = {}
    for ch in chis:
        seen[ch] = seen.get(ch, 0) + 1
    for n in seen.values():
        if n >= 2:
            dup += n // 2
    flags["iipeikou"] = dup
    flags["ryanpeikou"] = dup >= 2

    # sanshoku doujun
    chi_by_vals: dict[tuple[int, int, int], set[Suit]] = {}
    for kind, keys in mentsu:
        if kind != "chi":
            continue
        vals = tuple(sorted(k[1] for k in keys))
        suit = keys[0][0]
        chi_by_vals.setdefault(vals, set()).add(suit)
    # also open chi melds
    for m in ctx.hand.melds:
        if m.type == MeldType.CHI:
            vals = tuple(sorted(t.value for t in m.tiles))
            chi_by_vals.setdefault(vals, set()).add(m.tiles[0].suit)
    flags["sanshoku"] = any(len(suits) == 3 for suits in chi_by_vals.values())

    # ittsuu: 123 456 789 same suit
    for suit in (Suit.MAN, Suit.PIN, Suit.SOU):
        groups = set()
        for kind, keys in mentsu:
            if kind == "chi" and keys[0][0] == suit:
                start = min(k[1] for k in keys)
                if start in (1, 4, 7):
                    groups.add(start)
        for m in ctx.hand.melds:
            if m.type == MeldType.CHI and m.tiles[0].suit == suit:
                start = min(t.value for t in m.tiles)
                if start in (1, 4, 7):
                    groups.add(start)
        if {1, 4, 7} <= groups:
            flags["ittsuu"] = True

    # chanta / junchan
    def is_chanta_mentsu(kind: str, keys: tuple[tuple[Suit, int], ...]) -> bool:
        tiles_like = keys
        if kind == "chi":
            vals = [k[1] for k in keys]
            return 1 in vals or 9 in vals
        # pon
        suit, val = keys[0]
        if suit in (Suit.WIND, Suit.DRAGON):
            return True
        return val in (1, 9)

    all_mentsu_ok = all(is_chanta_mentsu(k, keys) for k, keys in mentsu)
    for m in ctx.hand.melds:
        if m.type == MeldType.CHI:
            vals = [t.value for t in m.tiles]
            if not (1 in vals or 9 in vals):
                all_mentsu_ok = False
        else:
            t0 = m.tiles[0]
            if not (t0.is_honor or t0.is_terminal):
                all_mentsu_ok = False
    pair_ok = pair[0] in (Suit.WIND, Suit.DRAGON) or pair[1] in (1, 9)
    if all_mentsu_ok and pair_ok and mentsu:
        # honor present?
        tiles = _all_tiles_for_yaku(ctx)
        has_honor = any(t.is_honor for t in tiles)
        has_terminal = any(t.is_terminal for t in tiles)
        if has_honor and has_terminal:
            flags["chanta"] = True
        elif has_terminal and not has_honor:
            flags["junchan"] = True

    # pinfu: menzen, all chi, valueless pair, ryanmen wait
    if ctx.menzen and all(k == "chi" for k, _ in mentsu) and not ctx.hand.melds:
        # valueless pair: not dragon, not seat/round wind
        pair_suit, pair_val = pair
        valued = False
        if pair_suit == Suit.DRAGON:
            valued = True
        if pair_suit == Suit.WIND and pair_val in (ctx.seat_wind, ctx.round_wind):
            valued = True
        if not valued and _is_ryanmen_wait(pair, mentsu, ctx):
            flags["pinfu"] = True

    return flags


def _is_ryanmen_wait(
    pair: tuple[Suit, int],
    mentsu: list[tuple[str, tuple[tuple[Suit, int], ...]]],
    ctx: WinContext,
) -> bool:
    """Winning tile completes a ryanmen (two-sided) sequence wait."""
    wt = ctx.winning_tile
    if not wt.is_suited:
        return False
    # Find a chi in partition that contains winning tile and forms ryanmen
    for kind, keys in mentsu:
        if kind != "chi":
            continue
        if keys[0][0] != wt.suit:
            continue
        vals = sorted(k[1] for k in keys)
        if wt.value not in vals:
            continue
        # sequence vals like 2,3,4 — wait was 2 or 4 for ryanmen on 23/34
        # If win tile is middle → kanchan, not ryanmen
        if wt.value == vals[1]:
            return False
        # penchan: 123 win 3, or 789 win 7
        if vals == [1, 2, 3] and wt.value == 3:
            return False
        if vals == [7, 8, 9] and wt.value == 7:
            return False
        # win on edge of sequence
        if wt.value in (vals[0], vals[2]):
            return True
    return False


def evaluate_yaku(ctx: WinContext) -> list[YakuItem]:
    """
    Return list of yaku (including dora as YakuItem name Dora/Ura/Aka).
    Yakuman stops stacking with normal yaku (kokushi only in this subset).
    """
    tiles = _all_tiles_for_yaku(ctx)
    items: list[YakuItem] = []

    if is_kokushi(tiles):
        items.append(YakuItem("Kokushi musou", 13, yakuman=True))
        # dora still count in some rules; we count dora separately below for points
        # Standard: yakuman ignores dora for han display; we follow that.
        return items

    # Menzen tsumo
    if ctx.menzen and ctx.tsumo:
        items.append(YakuItem("Menzen tsumo", 1))

    if ctx.riichi:
        items.append(YakuItem("Riichi", 1))
    if ctx.double_riichi:
        items.append(YakuItem("Double riichi", 1))
    if ctx.ippatsu:
        items.append(YakuItem("Ippatsu", 1))
    if ctx.haitei:
        items.append(YakuItem("Haitei", 1))
    if ctx.houtei:
        items.append(YakuItem("Houtei", 1))
    if ctx.rinshan:
        items.append(YakuItem("Rinshan kaihou", 1))
    if ctx.chankan:
        items.append(YakuItem("Chankan", 1))

    if _is_tanyao(tiles):
        items.append(YakuItem("Tanyao", 1))

    if is_chiitoitsu(tiles):
        items.append(YakuItem("Chiitoitsu", 2))
        # chiitoitsu-specific: honitsu/chinitsu/honroutou etc.
        suits = {t.suit for t in tiles if t.is_suited}
        honors = any(t.is_honor for t in tiles)
        if len(suits) == 1 and not honors:
            items.append(YakuItem("Chinitsu", 6 if ctx.menzen else 5))
        elif len(suits) == 1 and honors:
            items.append(YakuItem("Honitsu", 3 if ctx.menzen else 2))
        # dora
        items.extend(_dora_items(ctx, tiles))
        return _finalize(items)

    # Standard hand — evaluate best partition for max han from partition-dependent yaku
    free = list(ctx.hand.concealed)
    # Open melds already formed; free tiles must form remaining mentsu + pair
    partitions = standard_agari_partitions(free)
    if not partitions:
        # might still be win via open melds only if free forms correctly — already checked
        items.extend(_dora_items(ctx, tiles))
        return _finalize(items)

    best_extra: list[YakuItem] = []
    best_han = -1
    yakuhai = _yakuhai_hans(ctx, tiles, ctx.hand.melds)

    for pair, mentsu in partitions:
        flags = _partition_flags(pair, mentsu, ctx)
        extra: list[YakuItem] = []
        if flags["pinfu"]:
            extra.append(YakuItem("Pinfu", 1))
        if flags["ryanpeikou"] and ctx.menzen:
            extra.append(YakuItem("Ryanpeikou", 3))
        elif flags["iipeikou"] and ctx.menzen:
            extra.append(YakuItem("Iipeikou", 1))
        if flags["sanshoku"]:
            extra.append(YakuItem("Sanshoku doujun", 2 if ctx.menzen else 1))
        if flags["ittsuu"]:
            extra.append(YakuItem("Ittsuu", 2 if ctx.menzen else 1))
        if flags["junchan"]:
            extra.append(YakuItem("Junchan", 3 if ctx.menzen else 2))
        elif flags["chanta"]:
            extra.append(YakuItem("Chanta", 2 if ctx.menzen else 1))
        if flags["toitoi"]:
            extra.append(YakuItem("Toitoi", 2))

        # honitsu / chinitsu
        suits = {t.suit for t in tiles if t.is_suited}
        honors = any(t.is_honor for t in tiles)
        if len(suits) == 1 and not honors:
            extra.append(YakuItem("Chinitsu", 6 if ctx.menzen else 5))
        elif len(suits) == 1 and honors:
            extra.append(YakuItem("Honitsu", 3 if ctx.menzen else 2))

        han = sum(y.han for y in extra) + sum(y.han for y in yakuhai)
        if han > best_han:
            best_han = han
            best_extra = extra

    items.extend(yakuhai)
    items.extend(best_extra)
    items.extend(_dora_items(ctx, tiles))
    return _finalize(items)


def _dora_items(ctx: WinContext, tiles: list[Tile]) -> list[YakuItem]:
    out: list[YakuItem] = []
    dora = count_dora_hits(tiles, ctx.dora_tiles)
    if dora:
        out.append(YakuItem("Dora", dora))
    if ctx.riichi or ctx.double_riichi:
        ura = count_dora_hits(tiles, ctx.ura_dora_tiles)
        if ura:
            out.append(YakuItem("Ura-dora", ura))
    aka = ctx.aka_count if ctx.aka_count else count_aka(tiles)
    if aka:
        out.append(YakuItem("Aka-dora", aka))
    return out


def _finalize(items: list[YakuItem]) -> list[YakuItem]:
    # Must have at least one non-dora yaku
    real = [y for y in items if y.name not in ("Dora", "Ura-dora", "Aka-dora")]
    if not real:
        return []
    return items


def total_han(items: list[YakuItem]) -> int:
    if any(y.yakuman for y in items):
        return sum(y.han for y in items if y.yakuman)
    return sum(y.han for y in items)
