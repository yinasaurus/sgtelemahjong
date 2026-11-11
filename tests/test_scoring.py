"""Fan / scoring tests for Singapore Mahjong."""

from mahjong.fan import evaluate_fan, payout_win
from mahjong.hand import Hand
from mahjong.tiles import Suit, Tile


def _t(suit: Suit, value: int) -> Tile:
    return Tile(suit, value)


def _ping_wu_hand() -> Hand:
    h = Hand()
    h.concealed = [
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
    return h


def test_evaluate_fan_chicken_with_flower():
    h = Hand()
    # mixed chow + pong-ish: use ping wu base then claim only chicken path via flowers
    h.concealed = _ping_wu_hand().concealed
    fr = evaluate_fan(
        h,
        flowers=[_t(Suit.FLOWER, 0)],
        animals=[],
        tsumo=False,
        seat_wind=1,
        round_wind=0,
        min_fan=1,
    )
    assert fr is not None
    assert fr.total >= 1
    names = [i.name for i in fr.items]
    assert "All Chow" in names or "Chicken Hand" in names or "Flower 1" in names


def test_evaluate_fan_all_chow_ping_wu_self_draw():
    fr = evaluate_fan(
        _ping_wu_hand(),
        flowers=[],
        animals=[],
        tsumo=True,
        seat_wind=0,
        round_wind=0,
        min_fan=1,
    )
    assert fr is not None
    names = {i.name for i in fr.items}
    assert "Self-draw" in names
    assert "All Chow" in names
    assert "Ping Wu" in names
    assert fr.total >= 3


def test_evaluate_fan_rejects_non_win():
    h = Hand()
    # 14 unrelated singles — not a win shape
    h.concealed = [
        _t(Suit.MAN, 1),
        _t(Suit.MAN, 3),
        _t(Suit.MAN, 5),
        _t(Suit.MAN, 7),
        _t(Suit.PIN, 2),
        _t(Suit.PIN, 4),
        _t(Suit.PIN, 6),
        _t(Suit.PIN, 8),
        _t(Suit.SOU, 1),
        _t(Suit.SOU, 3),
        _t(Suit.SOU, 5),
        _t(Suit.SOU, 9),
        _t(Suit.WIND, 0),
        _t(Suit.DRAGON, 1),
    ]
    assert evaluate_fan(h, flowers=[], animals=[], tsumo=True, min_fan=1) is None


def test_payout_win_self_draw_and_discard():
    d = payout_win(2, tsumo=True, discarder=None, winner=0, max_fan=5)
    assert d[0] == 6 and d[1] == -2
    d2 = payout_win(3, tsumo=False, discarder=2, winner=1, max_fan=5)
    assert d2[1] == 3 and d2[2] == -3
