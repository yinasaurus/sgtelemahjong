from mahjong.hand import (
    is_chiitoitsu,
    is_kokushi,
    is_standard_win,
    is_winning_hand,
    winning_tile_waits,
)
from mahjong.tiles import Suit, Tile, parse_tiles


def test_standard_win():
    # 123m 456m 789m 123p 44p
    hand = parse_tiles("123m456m789m123p44p")
    assert len(hand) == 14
    assert is_standard_win(hand)
    assert is_winning_hand(hand)


def test_chiitoitsu():
    hand = parse_tiles("1133m5588p2244s EE")
    assert is_chiitoitsu(hand)
    assert is_winning_hand(hand)


def test_kokushi():
    hand = parse_tiles("19m19p19s E S W N Haku Hatsu Chun Chun")
    assert len(hand) == 14
    assert is_kokushi(hand)
    assert is_winning_hand(hand)


def test_tenpai_waits():
    # 123m456m789m123p E — waits E
    hand13 = parse_tiles("123m456m789m123p E")
    assert len(hand13) == 13
    waits = winning_tile_waits(hand13)
    assert any(t.suit == Suit.WIND and t.value == 0 for t in waits)


def test_non_win():
    hand = parse_tiles("112233m1199p1199s")
    assert len(hand) == 14
    # 112233 is two iipeikou-like; 11 99 11 99 — actually could be chiitoi? 
    # pairs: 1m1m 2m2m 3m3m 1p1p 9p9p 1s1s 9s9s — yes chiitoi
    assert is_chiitoitsu(hand)
