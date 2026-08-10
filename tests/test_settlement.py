from mahjong.settlement import SessionRules, oka_pool, rank_seats, settle_session


def test_oka_pool():
    r = SessionRules(start_points=25000, return_points=30000)
    assert oka_pool(r) == 20000


def test_rank_and_uma():
    totals = {0: 35000, 1: 30000, 2: 20000, 3: 15000}
    lines = settle_session(totals, SessionRules(), dealer=0)
    assert [ln.seat_index for ln in lines] == [0, 1, 2, 3]
    assert lines[0].oka_share == 20000
    assert lines[0].uma == 15000
    assert lines[0].final == 35000 - 30000 + 15000 + 20000
    assert lines[3].final == 15000 - 30000 + (-15000) + 0


def test_tiebreak_dealer_priority():
    totals = {0: 25000, 1: 25000, 2: 25000, 3: 25000}
    order = rank_seats(totals, dealer=2)
    # dealer 2 first, then 3, 0, 1
    assert order[0] == 2
