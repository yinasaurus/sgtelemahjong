"""Singapore Mahjong fan evaluation and payouts."""

from __future__ import annotations

from dataclasses import dataclass, field

from .hand import Hand, Meld, MeldType, is_chiitoitsu, is_kokushi, is_winning_hand, standard_agari_partitions
from .tiles import Suit, Tile


@dataclass(frozen=True)
class FanItem:
    name: str
    fan: int = 1


@dataclass
class FanResult:
    items: list[FanItem] = field(default_factory=list)
    special: str | None = None

    @property
    def total(self) -> int:
        return sum(i.fan for i in self.items)

    def capped(self, max_fan: int) -> int:
        return min(self.total, max_fan)


def has_all_dragon_pongs(melds: list[Meld]) -> bool:
    """True if exposed melds include all three dragon pongs/kongs."""
    have = set()
    for m in melds:
        if m.type == MeldType.CHI:
            continue
        if m.tiles and m.tiles[0].suit == Suit.DRAGON:
            have.add(m.tiles[0].value)
    return have >= {0, 1, 2}


def has_all_wind_pongs(melds: list[Meld]) -> bool:
    """True if exposed melds include all four wind pongs/kongs."""
    have = set()
    for m in melds:
        if m.type == MeldType.CHI:
            continue
        if m.tiles and m.tiles[0].suit == Suit.WIND:
            have.add(m.tiles[0].value)
    return have >= {0, 1, 2, 3}


def payout_each(winner: int, amount: int) -> dict[int, int]:
    """Each of the other three pays `amount` to winner."""
    d = {winner: 3 * amount}
    for s in range(4):
        if s != winner:
            d[s] = -amount
    return d


def payout_win(
    fan: int,
    *,
    tsumo: bool,
    discarder: int | None,
    winner: int,
    max_fan: int = 5,
) -> dict[int, int]:
    """
    Simplified SG table payout (points = fan value).
    Self-draw: each loser pays `fan`.
    Discard win: discarder pays `fan` (or 2× if house prefers — we use 1× fan for clarity).
    """
    fan = max(1, min(fan, max_fan if max_fan else fan))
    if tsumo or discarder is None:
        return payout_each(winner, fan)
    d = {winner: fan, discarder: -fan}
    for s in range(4):
        if s not in d:
            d[s] = 0
    return d


def _free_for_win(hand: Hand, win_tile: Tile | None, tsumo: bool) -> list[Tile]:
    """Concealed tiles that should form the remaining sets + pair (incl. winning tile)."""
    free = list(hand.concealed)
    if not tsumo and win_tile is not None:
        free = free + [win_tile]
    return free


def _all_playable(hand: Hand, free: list[Tile]) -> list[Tile]:
    out = list(free)
    for m in hand.melds:
        out.extend(m.tiles)
    return out


def _has_triplet(
    melds: list[Meld],
    mentsu: list[tuple[str, tuple[tuple[Suit, int], ...]]],
    suit: Suit,
    val: int,
) -> bool:
    for m in melds:
        if m.type == MeldType.CHI:
            continue
        if m.tiles and m.tiles[0].suit == suit and m.tiles[0].value == val:
            return True
    return any(k == "pon" and keys[0] == (suit, val) for k, keys in mentsu)


def evaluate_fan(
    hand: Hand,
    *,
    flowers: list[Tile],
    animals: list[Tile],
    win_tile: Tile | None = None,
    tsumo: bool = False,
    seat_wind: int = 0,
    round_wind: int = 0,
    replacement_win: bool = False,
    last_tile_win: bool = False,
    rob_kong: bool = False,
    min_fan: int = 1,
    max_fan: int = 5,
) -> FanResult | None:
    """
    Score a completed SG hand. Returns None if not a legal win / below min fan.
    For tsumo, winning tile is already in hand.concealed.
    For ron/chankan, pass win_tile (not yet in hand).
    """
    free = _free_for_win(hand, win_tile, tsumo)
    # Strip any leftover bonus tiles (should already be flushed)
    free = [t for t in free if not t.is_bonus]
    if not is_winning_hand(free):
        return None

    items: list[FanItem] = []
    special: str | None = None
    all_tiles = _all_playable(hand, free)
    menzen = hand.is_menzen()

    # --- Thirteen wonders ---
    if len(free) == 14 and is_kokushi(free):
        items.append(FanItem("Thirteen Wonders", 8))
        special = "thirteen_wonders"
        # still add flowers/animals
        items.extend(_bonus_items(flowers, animals, seat_wind))
        if tsumo:
            items.append(FanItem("Self-draw", 1))
        fr = FanResult(items=items, special=special)
        if fr.total < min_fan:
            return None
        return fr

    # --- Seven pairs (optional house rule — enabled) ---
    if len(free) == 14 and is_chiitoitsu(free):
        items.append(FanItem("Seven Pairs", 4))

    # Bonus tiles
    items.extend(_bonus_items(flowers, animals, seat_wind))

    if tsumo:
        items.append(FanItem("Self-draw", 1))
    if menzen and not any(m.type == MeldType.ANKAN for m in hand.melds):
        # Fully concealed (no open melds; ankan still counts as concealed in SG often)
        pass
    if menzen:
        items.append(FanItem("Fully Concealed", 1))
    if rob_kong:
        items.append(FanItem("Robbing a Kong", 1))
    if replacement_win:
        items.append(FanItem("Winning on Replacement", 1))
    if last_tile_win:
        items.append(FanItem("Last Tile", 1))

    parts = standard_agari_partitions(free)
    best: list[FanItem] = []

    for pair, mentsu in parts:
        local: list[FanItem] = []
        meld_chi = sum(1 for m in hand.melds if m.type == MeldType.CHI)
        meld_pon = sum(
            1
            for m in hand.melds
            if m.type in (MeldType.PON, MeldType.MINKAN, MeldType.ANKAN)
        )
        free_chi = sum(1 for k, _ in mentsu if k == "chi")
        free_pon = sum(1 for k, _ in mentsu if k == "pon")
        total_chi = free_chi + meld_chi
        total_pon = free_pon + meld_pon

        if total_chi + total_pon == 4:
            if total_chi == 4:
                local.append(FanItem("All Chow", 1))
                if menzen and pair[0] in (Suit.MAN, Suit.PIN, Suit.SOU):
                    local.append(FanItem("Ping Wu", 1))
            if total_pon == 4:
                local.append(FanItem("All Pong", 3))
                if tsumo and menzen:
                    local.append(FanItem("Hidden Treasure", 4))

        # Dragons
        drag = sum(1 for d in range(3) if _has_triplet(hand.melds, mentsu, Suit.DRAGON, d))
        if drag == 1:
            local.append(FanItem("Dragon Pong", 1))
        elif drag == 2:
            local.append(FanItem("Two Dragon Pongs", 3))
        elif drag == 3:
            local.append(FanItem("Three Dragon Pongs", 8))

        # Winds
        winds = sum(1 for w in range(4) if _has_triplet(hand.melds, mentsu, Suit.WIND, w))
        if _has_triplet(hand.melds, mentsu, Suit.WIND, seat_wind):
            local.append(FanItem("Seat Wind", 1))
        if _has_triplet(hand.melds, mentsu, Suit.WIND, round_wind) and round_wind != seat_wind:
            local.append(FanItem("Prevailing Wind", 1))
        if winds == 3:
            local.append(FanItem("Three Winds", 3))
        elif winds == 4:
            local.append(FanItem("Four Winds", 8))

        if sum(i.fan for i in local) > sum(i.fan for i in best):
            best = local

    items.extend(best)

    # Colour / terminal patterns
    number_suits = {t.suit for t in all_tiles if t.suit in (Suit.MAN, Suit.PIN, Suit.SOU)}
    has_honor = any(t.is_honor for t in all_tiles)
    if len(number_suits) == 1 and not has_honor:
        items.append(FanItem("Flush", 6))
    elif len(number_suits) == 1 and has_honor:
        items.append(FanItem("Half Flush", 3))

    if all(t.is_terminal_or_honor for t in all_tiles):
        if all(t.is_terminal for t in all_tiles):
            items.append(FanItem("All Terminals", 8))
        else:
            items.append(FanItem("All Terminals and Honours", 4))

    # Dedupe by name (keep first)
    seen: set[str] = set()
    deduped: list[FanItem] = []
    for it in items:
        if it.name in seen:
            continue
        seen.add(it.name)
        deduped.append(it)
    items = deduped

    # Chicken hand if no "real" structural fan beyond chicken itself
    structural_names = {
        "All Chow",
        "Ping Wu",
        "All Pong",
        "Hidden Treasure",
        "Dragon Pong",
        "Two Dragon Pongs",
        "Three Dragon Pongs",
        "Seat Wind",
        "Prevailing Wind",
        "Three Winds",
        "Four Winds",
        "Flush",
        "Half Flush",
        "All Terminals",
        "All Terminals and Honours",
        "Seven Pairs",
        "Thirteen Wonders",
    }
    has_structural = any(i.name in structural_names for i in items)
    # Flowers/animals count toward min fan in many SG tables
    bonus_fan = sum(
        i.fan
        for i in items
        if i.name.startswith("Flower")
        or i.name.startswith("Animal")
        or i.name
        in (
            "All 4 Flowers",
            "All 4 Animals",
            "Seat Flower",
            "Self-draw",
            "Fully Concealed",
            "Robbing a Kong",
            "Winning on Replacement",
            "Last Tile",
        )
    )
    if not has_structural:
        items.append(FanItem("Chicken Hand", 1))

    fr = FanResult(items=items, special=special)
    if fr.total < min_fan:
        return None
    return fr


def _bonus_items(flowers: list[Tile], animals: list[Tile], seat_wind: int) -> list[FanItem]:
    items: list[FanItem] = []
    seasons = [t for t in flowers if t.is_season_set]
    flo = [t for t in flowers if t.is_flower_set]
    if len(seasons) == 4:
        items.append(FanItem("All 4 Seasons", 2))
    else:
        for t in seasons:
            items.append(FanItem(f"Flower {t.value + 1}", 1))
    if len(flo) == 4:
        items.append(FanItem("All 4 Flowers", 2))
    else:
        for t in flo:
            items.append(FanItem(f"Flower {t.value - 3}", 1))
    if len(animals) == 4:
        items.append(FanItem("All 4 Animals", 2))
    else:
        for a in animals:
            items.append(FanItem(f"Animal {a.value + 1}", 1))
    if any(t.flower_wind == seat_wind for t in flowers):
        items.append(FanItem("Seat Flower", 1))
    return items
