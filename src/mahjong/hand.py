"""Hand / meld structures and win-shape detection."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterable, Iterator

from .tiles import Suit, Tile, counts_by_tile


class MeldType(str, Enum):
    CHI = "chi"
    PON = "pon"
    MINKAN = "minkan"  # open kan (daiminkan / shouminkan treated as open)
    ANKAN = "ankan"


@dataclass(frozen=True)
class Meld:
    type: MeldType
    tiles: tuple[Tile, ...]
    called_from: int | None = None  # seat index relative, or absolute — game sets
    # For chi/pon/kan from discard: which tile was the called one
    called_tile: Tile | None = None

    @property
    def is_open(self) -> bool:
        return self.type != MeldType.ANKAN

    @property
    def is_kan(self) -> bool:
        return self.type in (MeldType.MINKAN, MeldType.ANKAN)

    @property
    def is_concealed_kan(self) -> bool:
        return self.type == MeldType.ANKAN


@dataclass
class Hand:
    concealed: list[Tile] = field(default_factory=list)
    melds: list[Meld] = field(default_factory=list)

    def all_tiles(self) -> list[Tile]:
        out = list(self.concealed)
        for m in self.melds:
            out.extend(m.tiles)
        return out

    def is_menzen(self) -> bool:
        """Fully concealed for yaku purposes (ankan allowed)."""
        return all(m.type == MeldType.ANKAN for m in self.melds)

    def sort(self) -> None:
        self.concealed.sort(key=lambda t: t.key())


def _copy_counts(c: dict[tuple[Suit, int], int]) -> dict[tuple[Suit, int], int]:
    return dict(c)


def _iter_keys(c: dict[tuple[Suit, int], int]) -> Iterator[tuple[Suit, int]]:
    for k, n in c.items():
        if n > 0:
            yield k


def is_chiitoitsu(tiles: list[Tile]) -> bool:
    if len(tiles) != 14:
        return False
    c = counts_by_tile(tiles)
    if len(c) != 7:
        return False
    return all(n == 2 for n in c.values())


def is_kokushi(tiles: list[Tile]) -> bool:
    if len(tiles) != 14:
        return False
    terminals = {
        (Suit.MAN, 1),
        (Suit.MAN, 9),
        (Suit.PIN, 1),
        (Suit.PIN, 9),
        (Suit.SOU, 1),
        (Suit.SOU, 9),
        (Suit.WIND, 0),
        (Suit.WIND, 1),
        (Suit.WIND, 2),
        (Suit.WIND, 3),
        (Suit.DRAGON, 0),
        (Suit.DRAGON, 1),
        (Suit.DRAGON, 2),
    }
    c = counts_by_tile(tiles)
    if set(c) - terminals:
        return False
    if not terminals <= set(c):
        return False
    # Exactly one pair among the 13 types
    pairs = [k for k, n in c.items() if n == 2]
    singles = [k for k, n in c.items() if n == 1]
    return len(pairs) == 1 and len(singles) == 12 and sum(c.values()) == 14


def _remove(c: dict[tuple[Suit, int], int], key: tuple[Suit, int], n: int) -> bool:
    if c.get(key, 0) < n:
        return False
    c[key] -= n
    if c[key] == 0:
        del c[key]
    return True


def _try_mentsu(c: dict[tuple[Suit, int], int]) -> bool:
    """True if remaining counts can be partitioned into mentsu only."""
    if not c:
        return True
    # pick smallest key for determinism
    suit, val = min(c.keys(), key=lambda k: (int(k[0]), k[1]))
    # pon/kan-as-pon (4 = pon + isolated impossible here if exact)
    if c[(suit, val)] >= 3:
        c2 = _copy_counts(c)
        _remove(c2, (suit, val), 3)
        if _try_mentsu(c2):
            return True
    # chi
    if suit in (Suit.MAN, Suit.PIN, Suit.SOU) and val <= 7:
        if (
            c.get((suit, val), 0) >= 1
            and c.get((suit, val + 1), 0) >= 1
            and c.get((suit, val + 2), 0) >= 1
        ):
            c2 = _copy_counts(c)
            _remove(c2, (suit, val), 1)
            _remove(c2, (suit, val + 1), 1)
            _remove(c2, (suit, val + 2), 1)
            if _try_mentsu(c2):
                return True
    return False


def standard_agari_partitions(
    tiles: list[Tile],
) -> list[tuple[tuple[Suit, int], list[tuple[str, tuple[tuple[Suit, int], ...]]]]]:
    """
    Return all standard 4-mentsu + pair partitions of a 14-tile closed hand
    (or fewer if open melds already account for some mentsu — pass only free tiles
    that should form remaining mentsu + pair).

    Each item: (pair_key, [(mentsu_kind, keys...), ...])
    mentsu_kind in {'chi','pon'}
    """
    need_mentsu = len(tiles) // 3
    if len(tiles) % 3 != 2:
        return []
    c0 = counts_by_tile(tiles)
    results: list[
        tuple[tuple[Suit, int], list[tuple[str, tuple[tuple[Suit, int], ...]]]]
    ] = []

    def search(
        c: dict[tuple[Suit, int], int],
        pair: tuple[Suit, int] | None,
        mentsu: list[tuple[str, tuple[tuple[Suit, int], ...]]],
    ) -> None:
        if pair is None:
            keys = sorted(c.keys(), key=lambda k: (int(k[0]), k[1]))
            for k in keys:
                if c.get(k, 0) >= 2:
                    c2 = _copy_counts(c)
                    _remove(c2, k, 2)
                    search(c2, k, mentsu)
            return
        if not c:
            if len(mentsu) == need_mentsu:
                results.append((pair, list(mentsu)))
            return
        suit, val = min(c.keys(), key=lambda k: (int(k[0]), k[1]))
        # koutsu
        if c[(suit, val)] >= 3:
            c2 = _copy_counts(c)
            _remove(c2, (suit, val), 3)
            mentsu.append(("pon", ((suit, val), (suit, val), (suit, val))))
            search(c2, pair, mentsu)
            mentsu.pop()
        # shuntsu
        if suit in (Suit.MAN, Suit.PIN, Suit.SOU) and val <= 7:
            if (
                c.get((suit, val), 0)
                and c.get((suit, val + 1), 0)
                and c.get((suit, val + 2), 0)
            ):
                c2 = _copy_counts(c)
                _remove(c2, (suit, val), 1)
                _remove(c2, (suit, val + 1), 1)
                _remove(c2, (suit, val + 2), 1)
                mentsu.append(
                    (
                        "chi",
                        (
                            (suit, val),
                            (suit, val + 1),
                            (suit, val + 2),
                        ),
                    )
                )
                search(c2, pair, mentsu)
                mentsu.pop()

    search(c0, None, [])
    # dedupe
    uniq: list[
        tuple[tuple[Suit, int], list[tuple[str, tuple[tuple[Suit, int], ...]]]]
    ] = []
    seen: set[object] = set()
    for pair, mentsu in results:
        key = (pair, tuple(sorted(mentsu)))
        if key not in seen:
            seen.add(key)
            uniq.append((pair, mentsu))
    return uniq


def is_standard_win(tiles: list[Tile]) -> bool:
    return bool(standard_agari_partitions(tiles))


def is_winning_hand(tiles: list[Tile]) -> bool:
    """True if free tiles form a complete hand (14 closed, or 14-3n with open melds)."""
    if len(tiles) % 3 != 2 or len(tiles) < 2 or len(tiles) > 14:
        return False
    if len(tiles) == 14:
        return is_kokushi(tiles) or is_chiitoitsu(tiles) or is_standard_win(tiles)
    # Open hand: only standard shape on remaining free tiles
    return is_standard_win(tiles)


def winning_tile_waits(tiles: list[Tile], open_meld_count: int = 0) -> list[Tile]:
    """Tiles that complete a waiting hand (unique by suit/value)."""
    expect = 13 - 3 * open_meld_count
    if len(tiles) != expect:
        return []
    waits: list[Tile] = []
    seen: set[tuple[Suit, int]] = set()
    candidates: list[Tile] = []
    for suit in (Suit.MAN, Suit.PIN, Suit.SOU):
        for v in range(1, 10):
            candidates.append(Tile(suit, v))
    for w in range(4):
        candidates.append(Tile(Suit.WIND, w))
    for d in range(3):
        candidates.append(Tile(Suit.DRAGON, d))
    for t in candidates:
        k = (t.suit, t.value)
        if k in seen:
            continue
        if is_winning_hand(tiles + [t]):
            seen.add(k)
            waits.append(t)
    return waits


def is_tenpai(tiles: list[Tile], open_meld_count: int = 0) -> bool:
    return bool(winning_tile_waits(tiles, open_meld_count))


# --- Minimal shanten (standard hand only; used later by bots) ---


def shanten_standard(tiles: list[Tile], open_meld_count: int = 0) -> int:
    """
    Approximate standard-hand shanten (0 = tenpai).
    open_meld_count: already-completed open/closed melds outside `tiles`.
    """
    n = len(tiles)
    if n > 14:
        return 8
    open_meld_count = max(0, min(4, open_meld_count))
    need_mentsu = 4 - open_meld_count
    # Closed baseline uses 8 - 2M - T - H; each open meld removes 2 from that budget
    base = 8 - 2 * open_meld_count
    c = counts_by_tile(tiles)
    best = 8

    def dfs(
        counts: dict[tuple[Suit, int], int],
        mentsu: int,
        taatsu: int,
        head: bool,
    ) -> None:
        nonlocal best
        if mentsu > need_mentsu:
            return
        if not counts:
            s = base - 2 * mentsu - taatsu - (1 if head else 0)
            best = min(best, max(s, -1))
            return
        suit, val = min(counts.keys(), key=lambda k: (int(k[0]), k[1]))
        # take koutsu
        if counts[(suit, val)] >= 3:
            c2 = _copy_counts(counts)
            _remove(c2, (suit, val), 3)
            dfs(c2, mentsu + 1, taatsu, head)
        # take shuntsu
        if suit in (Suit.MAN, Suit.PIN, Suit.SOU) and val <= 7:
            if (
                counts.get((suit, val), 0)
                and counts.get((suit, val + 1), 0)
                and counts.get((suit, val + 2), 0)
            ):
                c2 = _copy_counts(counts)
                _remove(c2, (suit, val), 1)
                _remove(c2, (suit, val + 1), 1)
                _remove(c2, (suit, val + 2), 1)
                dfs(c2, mentsu + 1, taatsu, head)
        # head
        if not head and counts[(suit, val)] >= 2:
            c2 = _copy_counts(counts)
            _remove(c2, (suit, val), 2)
            dfs(c2, mentsu, taatsu, True)
        # taatsu: pair (toitoi proto), ryanmen/kanchan/penchan
        if counts[(suit, val)] >= 2:
            c2 = _copy_counts(counts)
            _remove(c2, (suit, val), 2)
            dfs(c2, mentsu, taatsu + 1, head)
        if suit in (Suit.MAN, Suit.PIN, Suit.SOU):
            # adjacent
            if val <= 8 and counts.get((suit, val + 1), 0):
                c2 = _copy_counts(counts)
                _remove(c2, (suit, val), 1)
                _remove(c2, (suit, val + 1), 1)
                dfs(c2, mentsu, taatsu + 1, head)
            # kanchan
            if val <= 7 and counts.get((suit, val + 2), 0) and not counts.get(
                (suit, val + 1), 0
            ):
                c2 = _copy_counts(counts)
                _remove(c2, (suit, val), 1)
                _remove(c2, (suit, val + 2), 1)
                dfs(c2, mentsu, taatsu + 1, head)
        # isolate discard this tile group
        c2 = _copy_counts(counts)
        _remove(c2, (suit, val), 1)
        dfs(c2, mentsu, taatsu, head)

    dfs(c, 0, 0, False)
    if open_meld_count == 0:
        # chiitoitsu / kokushi only for closed hands
        pairs = sum(1 for n in c.values() if n >= 2)
        kinds = len(c)
        chii_sh = 6 - pairs + max(0, 7 - kinds)
        kokushi_types = {
            (Suit.MAN, 1),
            (Suit.MAN, 9),
            (Suit.PIN, 1),
            (Suit.PIN, 9),
            (Suit.SOU, 1),
            (Suit.SOU, 9),
            *((Suit.WIND, w) for w in range(4)),
            *((Suit.DRAGON, d) for d in range(3)),
        }
        have = sum(1 for k in kokushi_types if c.get(k, 0) > 0)
        has_pair = any(c.get(k, 0) >= 2 for k in kokushi_types)
        kok_sh = 13 - have - (1 if has_pair else 0)
        return min(best, chii_sh, kok_sh)
    return best


def shanten(tiles: list[Tile], open_meld_count: int = 0) -> int:
    return shanten_standard(tiles, open_meld_count)
