from pathlib import Path

from bot.session_ops import end_session_text, standings_text
from bot.state import TableManager
from db import models as db
from mahjong.settlement import SessionRules


def test_record_hand_and_undo(tmp_path: Path):
    path = str(tmp_path / "s.sqlite")
    mgr = TableManager(path)
    t = mgr.create(
        1,
        10,
        turn_timeout_s=60,
        claim_timeout_s=60,
        session_rules=SessionRules(),
    )
    assert not isinstance(t, str)
    t.join(10, "Host")
    t.fill_bots(3)
    mgr.persist(t)
    assert t.db_table_id is not None
    scores = db.get_scores(path, t.db_table_id)
    assert scores[0] == 25000

    db.record_hand(
        path,
        table_id=t.db_table_id,
        hand_number=1,
        winner_seat_index=0,
        loser_seat_index=1,
        dealer_seat_index=0,
        han=3,
        fu=30,
        points=3900,
        yaku_list=["Riichi", "Tanyao"],
        reason="ron",
        deltas={0: 3900, 1: -3900, 2: 0, 3: 0},
    )
    scores = db.get_scores(path, t.db_table_id)
    assert scores[0] == 28900
    assert scores[1] == 21100

    undone = db.undo_last_hand(path, t.db_table_id)
    assert undone is not None
    scores = db.get_scores(path, t.db_table_id)
    assert scores[0] == 25000


def test_endsession_settlement(tmp_path: Path):
    path = str(tmp_path / "s2.sqlite")
    mgr = TableManager(path)
    t = mgr.create(2, 10, turn_timeout_s=60, claim_timeout_s=60)
    assert not isinstance(t, str)
    t.join(10, "H")
    t.fill_bots(3)
    mgr.persist(t)
    assert t.db_table_id is not None
    for seat, total in [(0, 40000), (1, 30000), (2, 20000), (3, 10000)]:
        # set scores directly
        with db.connect(path) as conn:
            conn.execute(
                "UPDATE session_scores SET running_total=? WHERE table_id=? AND seat_index=?",
                (total, t.db_table_id, seat),
            )
            conn.commit()
    text = end_session_text(path, t)
    assert "Session ended" in text
    hist = db.list_history(path, 2)
    assert len(hist) == 1
    assert hist[0]["final"]["settlement"][0]["rank"] == 1
