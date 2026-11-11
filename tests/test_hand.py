"""Hand / win-shape tests for Singapore Mahjong."""

from mahjong.hand import (
    Hand,
    Meld,
    MeldType,
    is_chiitoitsu,
    is_kokushi,
    is_tenpai,
    is_winning_hand,
    shanten,
    winning_tile_waits,
)
from mahjong.tiles import Suit, Tile


def _t(suit: Suit, value: int) -> Tile:
    return Tile(suit, value)


def _closed_chow_hand() -> list[Tile]:
    # 123m 456m 789m 123p 44s
    return [
        _t(Suit.MAN, 1),
        _t(Suit.MAN, 2),
        _t(Suit.MAN, 3),
        _t(Suit.MAN, 4),
        _t(Suit.MAN, 5),
        _t(Suit.MAN, 6),
        _t(Suit.MAN, 7),
        _t(Suit.MAN, 8),
        _t(Suit.MAN, 9),
        _t(Suit.PIN, 1),
        _t(Suit.PIN, 2),
        _t(Suit.PIN, 3),
        _t(Suit.SOU, 4),
        _t(Suit.SOU, 4),
    ]


def test_standard_closed_win():
    tiles = _closed_chow_hand()
    assert is_winning_hand(tiles)


def test_open_hand_win_after_pong():
    # free tiles: 123m 456m 789m 44s (11 tiles) + open pong of 1p
    free = [
        _t(Suit.MAN, 1),
        _t(Suit.MAN, 2),
        _t(Suit.MAN, 3),
        _t(Suit.MAN, 4),
        _t(Suit.MAN, 5),
        _t(Suit.MAN, 6),
        _t(Suit.MAN, 7),
        _t(Suit.MAN, 8),
        _t(Suit.MAN, 9),
        _t(Suit.SOU, 4),
        _t(Suit.SOU, 4),
    ]
    assert is_winning_hand(free)


def test_seven_pairs_and_kokushi_shapes():
    pairs = []
    for i, (s, v) in enumerate(
        [
            (Suit.MAN, 1),
            (Suit.MAN, 2),
            (Suit.PIN, 3),
            (Suit.PIN, 5),
            (Suit.SOU, 7),
            (Suit.WIND, 0),
            (Suit.DRAGON, 1),
        ]
    ):
        pairs.extend([_t(s, v), _t(s, v)])
    assert is_chiitoitsu(pairs)
    assert is_winning_hand(pairs)

    terminals = [
        _t(Suit.MAN, 1),
        _t(Suit.MAN, 9),
        _t(Suit.PIN, 1),
        _t(Suit.PIN, 9),
        _t(Suit.SOU, 1),
        _t(Suit.SOU, 9),
        _t(Suit.WIND, 0),
        _t(Suit.WIND, 1),
        _t(Suit.WIND, 2),
        _t(Suit.WIND, 3),
        _t(Suit.DRAGON, 0),
        _t(Suit.DRAGON, 1),
        _t(Suit.DRAGON, 2),
        _t(Suit.DRAGON, 2),
    ]
    assert is_kokushi(terminals)
    assert is_winning_hand(terminals)


def test_tenpai_and_shanten_closed():
    tiles13 = _closed_chow_hand()[:-1]  # drop one 4s
    assert len(tiles13) == 13
    assert is_tenpai(tiles13)
    waits = winning_tile_waits(tiles13)
    assert any(w.suit == Suit.SOU and w.value == 4 for w in waits)
    assert shanten(tiles13) == 0


def test_shanten_open_meld_count():
    # 10 free tiles after one open meld, roughly closer than closed junk
    free = [
        _t(Suit.MAN, 1),
        _t(Suit.MAN, 2),
        _t(Suit.MAN, 3),
        _t(Suit.MAN, 4),
        _t(Suit.MAN, 5),
        _t(Suit.MAN, 6),
        _t(Suit.PIN, 2),
        _t(Suit.PIN, 3),
        _t(Suit.SOU, 4),
        _t(Suit.SOU, 4),
    ]
    assert shanten(free, open_meld_count=1) <= shanten(free, open_meld_count=0)
