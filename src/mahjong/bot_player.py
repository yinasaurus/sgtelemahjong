"""
Heuristic bot players for Singapore Mahjong (no Telegram imports).

Difficulties:
  - easy: mostly random legal actions
  - normal: shanten + fan-aware keep + selective calls
  - hard: wait width, defence, smarter pong/chow decisions
"""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import dataclass
from enum import Enum
from typing import Literal

from .game import ClaimType, Game
from .hand import shanten, winning_tile_waits
from .tiles import Suit, Tile


class BotDifficulty(str, Enum):
    EASY = "easy"
    NORMAL = "normal"
    HARD = "hard"


BOT_NAMES = ("Ah Beng", "Ah Seng", "Ah Lian")


@dataclass(frozen=True)
class TurnDecision:
    kind: Literal["tsumo", "discard", "ankan", "shouminkan"]
    discard_index: int | None = None
    kan_tile: Tile | None = None


@dataclass(frozen=True)
class ClaimDecision:
    kind: ClaimType
    chi_tiles: tuple[Tile, Tile] | None = None


def _open_count(game: Game, seat: int) -> int:
    return len(game.players[seat].hand.melds)


def _counts(tiles: list[Tile]) -> Counter[tuple[Suit, int]]:
    return Counter((t.suit, t.value) for t in tiles)


def _visible_count(game: Game, key: tuple[Suit, int], *, seat: int) -> int:
    """How many of this tile are already visible (not in our concealed)."""
    n = 0
    for s, p in enumerate(game.players):
        for t in p.discards:
            if (t.suit, t.value) == key:
                n += 1
        for m in p.hand.melds:
            for t in m.tiles:
                if (t.suit, t.value) == key:
                    n += 1
        if s != seat:
            for t in p.flowers + p.animals:
                if (t.suit, t.value) == key:
                    n += 1
    return n


def _genbutsu(game: Game, seat: int) -> set[tuple[Suit, int]]:
    """Tiles opponents have already discarded (safer to throw late game)."""
    safe: set[tuple[Suit, int]] = set()
    for s, p in enumerate(game.players):
        if s == seat:
            continue
        for t in p.discards:
            safe.add((t.suit, t.value))
    return safe


def _dangerous_tiles(game: Game, seat: int) -> set[tuple[Suit, int]]:
    """Tiles that look hot: recent honors/terminals, visible dragon traps."""
    danger: set[tuple[Suit, int]] = set()
    for s, p in enumerate(game.players):
        if s == seat:
            continue
        for t in p.discards[-8:]:
            if t.is_honor or t.is_terminal:
                danger.add((t.suit, t.value))
        for m in p.hand.melds:
            t0 = m.tiles[0]
            if t0.is_honor:
                danger.add((t0.suit, t0.value))
            # suji-ish: if they ponged 5, 2/8 can be wait — light touch only
            if t0.is_suited and m.type.value == "pon":
                for v in (t0.value - 3, t0.value + 3):
                    if 1 <= v <= 9:
                        danger.add((t0.suit, v))
    return danger


def _majority_suit(tiles: list[Tile], melds_tiles: list[Tile]) -> Suit | None:
    c: Counter[Suit] = Counter()
    for t in tiles + melds_tiles:
        if t.suit in (Suit.MAN, Suit.PIN, Suit.SOU):
            c[t.suit] += 1
    if not c:
        return None
    suit, n = c.most_common(1)[0]
    if n >= 6:
        return suit
    return None


def _keep_value(
    game: Game,
    seat: int,
    tile: Tile,
    hand: list[Tile],
    *,
    maj: Suit | None,
) -> int:
    """Higher = more valuable to keep (subtract when scoring discards)."""
    key = (tile.suit, tile.value)
    ct = _counts(hand)
    n = ct[key]
    seat_w = game.seat_wind(seat)
    round_w = game.round_wind
    v = 0

    if tile.suit == Suit.DRAGON:
        v += 5 + 4 * (n - 1)
    elif tile.suit == Suit.WIND:
        if tile.value == seat_w or tile.value == round_w:
            v += 4 + 3 * (n - 1)
        else:
            v += -2 if n == 1 else 1  # guest wind singleton = trash
    elif tile.is_suited:
        # middle tiles more flexible
        if 3 <= tile.value <= 7:
            v += 2
        elif tile.value in (2, 8):
            v += 1
        # part of pair / potential pong
        if n >= 2:
            v += 3
        if n >= 3:
            v += 4
        # adjacent partners in hand
        for d in (-2, -1, 1, 2):
            if ct.get((tile.suit, tile.value + d), 0):
                v += 2
        # flush push
        if maj is not None:
            if tile.suit == maj:
                v += 3
            else:
                v -= 4
    # dying tile (3+ visible) — less worth keeping
    if _visible_count(game, key, seat=seat) >= 3:
        v -= 3
    return v


def _shanten_of(game: Game, seat: int, tiles: list[Tile]) -> int:
    return shanten(tiles, _open_count(game, seat))


def choose_discard_index(
    game: Game,
    seat: int,
    *,
    difficulty: BotDifficulty = BotDifficulty.NORMAL,
    rng: random.Random | None = None,
) -> int:
    rng = rng or random.Random()
    tiles = list(game.players[seat].hand.concealed)
    n = len(tiles)
    if n == 0:
        return 0
    if difficulty == BotDifficulty.EASY:
        return rng.randrange(n)

    hard = difficulty == BotDifficulty.HARD
    open_n = _open_count(game, seat)
    meld_tiles = [t for m in game.players[seat].hand.melds for t in m.tiles]
    maj = _majority_suit(tiles, meld_tiles)
    danger = _dangerous_tiles(game, seat)
    gen = _genbutsu(game, seat) if hard else set()
    wall_left = game.wall.remaining_live
    late = wall_left <= 40

    scored: list[tuple[tuple, int]] = []
    for i, t in enumerate(tiles):
        left = tiles[:i] + tiles[i + 1 :]
        sh = shanten(left, open_n)
        wait_w = 0
        if sh <= 0:
            wait_w = len(winning_tile_waits(left, open_n))
        keep = _keep_value(game, seat, t, tiles, maj=maj)
        hot = 1 if (t.suit, t.value) in danger else 0
        if hard and late:
            hot += 0 if (t.suit, t.value) in gen else 2
        # Lower tuple wins. Prefer: low shanten, wide wait, low keep (ok to throw), safe
        key = (
            sh,
            -wait_w,
            hot,
            keep,  # discard low-value tiles first among equal shanten
            0 if t.is_honor and t.suit == Suit.WIND and t.value not in (
                game.seat_wind(seat),
                game.round_wind,
            ) else 1,
            rng.random(),  # tiny jitter only inside equal keys — put last via separate
        )
        # Use deterministic tie-break then rng among equals
        scored.append((key[:-1], i))

    scored.sort(key=lambda x: x[0])
    best = scored[0][0]
    cands = [i for k, i in scored if k == best]
    return rng.choice(cands)


def choose_turn_action(
    game: Game,
    seat: int,
    *,
    difficulty: BotDifficulty = BotDifficulty.NORMAL,
    rng: random.Random | None = None,
) -> TurnDecision:
    rng = rng or random.Random()
    if game.can_tsumo(seat):
        return TurnDecision("tsumo")

    tiles = list(game.players[seat].hand.concealed)
    hard = difficulty == BotDifficulty.HARD

    # Kong: good for replacement + fan; hard avoids killing a strong wait
    open_n = _open_count(game, seat)
    cur_sh = shanten(tiles, open_n)

    def _consider_kan(tile: Tile) -> bool:
        if difficulty == BotDifficulty.EASY:
            return rng.random() < 0.35
        if not hard:
            return True
        # Don't kan if currently tenpai with wide wait unless tile is deadish
        if cur_sh <= 0:
            left = [x for x in tiles if not x.same_tile(tile)]
            # removing 4 of a kind from tenpai hand is messy — only if still tenpai shape after
            return False
        return True

    seen: set[tuple[Suit, int]] = set()
    for t in tiles:
        key = (t.suit, t.value)
        if key in seen:
            continue
        seen.add(key)
        if game.can_ankan(seat, t) and _consider_kan(t):
            return TurnDecision("ankan", kan_tile=t)
        if game.can_shouminkan(seat, t) and _consider_kan(t):
            # shouminkan can be robbed — hard is more careful late
            if hard and game.wall.remaining_live <= 30 and rng.random() < 0.4:
                continue
            return TurnDecision("shouminkan", kan_tile=t)

    idx = choose_discard_index(game, seat, difficulty=difficulty, rng=rng)
    return TurnDecision("discard", discard_index=idx)


def _remove_n(tiles: list[Tile], tile: Tile, n: int) -> list[Tile]:
    left = list(tiles)
    removed = 0
    for t in list(left):
        if t.same_tile(tile) and removed < n:
            left.remove(t)
            removed += 1
    return left


def _shanten_after_call(
    game: Game,
    seat: int,
    *,
    kind: ClaimType,
    discard: Tile,
    chi_tiles: tuple[Tile, Tile] | None = None,
) -> int | None:
    hand = list(game.players[seat].hand.concealed)
    open_n = _open_count(game, seat) + 1
    if kind == ClaimType.PON:
        left = _remove_n(hand, discard, 2)
    elif kind == ClaimType.KAN:
        left = _remove_n(hand, discard, 3)
    elif kind == ClaimType.CHI and chi_tiles:
        left = list(hand)
        for ct in chi_tiles:
            for t in list(left):
                if t.suit == ct.suit and t.value == ct.value:
                    left.remove(t)
                    break
        open_n = _open_count(game, seat) + 1
    else:
        return None
    return shanten(left, open_n)


def _is_value_tile(game: Game, seat: int, tile: Tile) -> bool:
    if tile.suit == Suit.DRAGON:
        return True
    if tile.suit == Suit.WIND and tile.value in (
        game.seat_wind(seat),
        game.round_wind,
    ):
        return True
    return False


def _bonus_fan_bank(game: Game, seat: int) -> int:
    p = game.players[seat]
    return len(p.flowers) + len(p.animals)


def choose_claim_action(
    game: Game,
    seat: int,
    *,
    difficulty: BotDifficulty = BotDifficulty.NORMAL,
    rng: random.Random | None = None,
) -> ClaimDecision:
    rng = rng or random.Random()
    elig = game.eligible_claims(seat)
    if not elig:
        return ClaimDecision(ClaimType.PASS)

    # Always take the win
    if ClaimType.RON in elig:
        return ClaimDecision(ClaimType.RON)

    if difficulty == BotDifficulty.EASY:
        opts = [c for c in elig if c != ClaimType.PASS]
        opts.append(ClaimType.PASS)
        kind = rng.choice(opts)
        chi = None
        if kind == ClaimType.CHI and game.pending_discard:
            chi_opts = game.chi_options(seat, game.pending_discard[1])
            if not chi_opts:
                return ClaimDecision(ClaimType.PASS)
            chi = rng.choice(chi_opts)
        return ClaimDecision(kind, chi_tiles=chi)

    hard = difficulty == BotDifficulty.HARD
    hand = list(game.players[seat].hand.concealed)
    before = _shanten_of(game, seat, hand)
    discard = game.pending_discard[1] if game.pending_discard else None
    if discard is None:
        return ClaimDecision(ClaimType.PASS)

    # Kong / pong value tiles aggressively
    if ClaimType.KAN in elig and (
        _is_value_tile(game, seat, discard) or before >= 2 or _bonus_fan_bank(game, seat)
    ):
        after = _shanten_after_call(game, seat, kind=ClaimType.KAN, discard=discard)
        if after is not None and after <= before:
            return ClaimDecision(ClaimType.KAN)

    if ClaimType.PON in elig:
        after = _shanten_after_call(game, seat, kind=ClaimType.PON, discard=discard)
        value = _is_value_tile(game, seat, discard)
        improves = after is not None and after < before
        same = after is not None and after <= before
        # Pong dragons/winds even if shanten flat; else only if improves
        if value and same:
            return ClaimDecision(ClaimType.PON)
        if improves and (before <= 3 or not hard):
            return ClaimDecision(ClaimType.PON)
        if improves and hard and after <= 2:
            return ClaimDecision(ClaimType.PON)

    if ClaimType.CHI in elig:
        # Avoid opening a clean flush for a random chow unless it helps a lot
        meld_tiles = [t for m in game.players[seat].hand.melds for t in m.tiles]
        maj = _majority_suit(hand, meld_tiles)
        if maj is not None and discard.suit != maj and hard and before <= 2:
            return ClaimDecision(ClaimType.PASS)

        best_pair: tuple[Tile, Tile] | None = None
        best_after = before
        for pair in game.chi_options(seat, discard):
            after = _shanten_after_call(
                game, seat, kind=ClaimType.CHI, discard=discard, chi_tiles=pair
            )
            if after is not None and after < best_after:
                best_after = after
                best_pair = pair
        if best_pair is not None and best_after < before:
            if before <= 4:
                return ClaimDecision(ClaimType.CHI, chi_tiles=best_pair)

    return ClaimDecision(ClaimType.PASS)


def apply_turn_decision(game: Game, seat: int, decision: TurnDecision) -> str:
    if decision.kind == "tsumo":
        game.declare_tsumo(seat)
        return "tsumo"
    if decision.kind == "ankan":
        assert decision.kan_tile is not None
        game.declare_ankan(seat, decision.kan_tile)
        return "ankan"
    if decision.kind == "shouminkan":
        assert decision.kan_tile is not None
        game.declare_shouminkan(seat, decision.kan_tile)
        return "shouminkan"
    assert decision.discard_index is not None
    game.discard(seat, decision.discard_index)
    return "discard"


def apply_claim_decision(game: Game, seat: int, decision: ClaimDecision) -> bool:
    return game.register_claim(seat, decision.kind, chi_tiles=decision.chi_tiles)
