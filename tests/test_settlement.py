from mahjong.settlement import SessionRules, oka_pool, rank_seats, settle_session


def test_oka_pool_sg_defaults_zero():
    r = SessionRules()
    assert oka_pool(r) == 0


def test_oka_pool_optional_classic():
    r = SessionRules(start_points=25000, return_points=30000)
    assert oka_pool(r) == 20000


def test_rank_sg_fan_points_no_uma():
    totals = {0: 12, 1: 4, 2: -3, 3: -13}
    lines = settle_session(totals, SessionRules(), dealer=0)
    assert [ln.seat_index for ln in lines] == [0, 1, 2, 3]
    assert lines[0].oka_share == 0
    assert lines[0].uma == 0
    assert lines[0].final == 12  # raw - 0 return + 0 uma + 0 oka


def test_rank_and_uma_classic_optional():
    rules = SessionRules(
        start_points=25000,
        return_points=30000,
        uma=(15000, 5000, -5000, -15000),
    )
    totals = {0: 35000, 1: 30000, 2: 20000, 3: 15000}
    lines = settle_session(totals, rules, dealer=0)
    assert lines[0].oka_share == 20000
    assert lines[0].uma == 15000
    assert lines[0].final == 35000 - 30000 + 15000 + 20000


def test_tiebreak_dealer_priority():
    totals = {0: 0, 1: 0, 2: 0, 3: 0}
    order = rank_seats(totals, dealer=2)
    assert order[0] == 2
