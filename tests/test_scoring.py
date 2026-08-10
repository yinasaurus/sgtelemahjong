from mahjong.hand import Hand
from mahjong.scoring import basic_points_from_han_fu, payments_for_win, score_win
from mahjong.tiles import parse_tiles
from mahjong.yaku import WinContext, evaluate_yaku, total_han


def test_basic_points_mangan():
    bp, name = basic_points_from_han_fu(5, 30)
    assert bp == 2000 and name == "mangan"
    bp, name = basic_points_from_han_fu(4, 40)
    assert bp == 2000 and name == "mangan"


def test_ron_payments():
    # 3 han 30 fu non-dealer ron: basic=30*2^5=960 → 960*4=3840 → ceil each? 
    # payments_for_win ceils the total payment
    pays = payments_for_win(winner=1, dealer=0, basic=960, tsumo=False, ron_from=2)
    assert pays[2] == 3840


def test_tsumo_dealer_payments():
    # dealer tsumo 3/30 basic 960 → each pays 1920
    pays = payments_for_win(winner=0, dealer=0, basic=960, tsumo=True, ron_from=None)
    assert all(v == 1920 for v in pays.values())
    assert len(pays) == 3


def test_tanyao_riichi_score():
    tiles = parse_tiles("234m234p345s22s 66p")  # tanyao, need 14
    # 234m 234p 345s 22s 66p = 3+3+3+2+2=13 — fix
    tiles = parse_tiles("234m234p345567s22s")
    assert len(tiles) == 14
    ctx = WinContext(
        hand=Hand(concealed=list(tiles)),
        winning_tile=tiles[-1],
        from_ron=False,
        riichi=True,
        menzen=True,
        tsumo=True,
        seat_wind=1,
        round_wind=0,
    )
    yaku = evaluate_yaku(ctx)
    names = {y.name for y in yaku}
    assert "Tanyao" in names
    assert "Riichi" in names
    assert "Menzen tsumo" in names
    assert total_han(yaku) >= 3
    result = score_win(ctx, winner=1, dealer=0)
    assert result is not None
    assert result.gain > 0


def test_pinfu_detection():
    # Closed pinfu: ryanmen wait 23p → 1p/4p
    tiles = parse_tiles("123m456m789p23p55s 1p")
    assert len(tiles) == 14
    ctx = WinContext(
        hand=Hand(concealed=list(tiles)),
        winning_tile=parse_tiles("1p")[0],
        from_ron=True,
        menzen=True,
        tsumo=False,
        seat_wind=1,
        round_wind=0,
    )
    yaku = evaluate_yaku(ctx)
    names = {y.name for y in yaku}
    assert "Pinfu" in names
