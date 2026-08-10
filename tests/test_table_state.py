from pathlib import Path

from bot.state import Table, TableManager, TableStatus


def test_join_leave_and_full(tmp_path: Path):
    mgr = TableManager(str(tmp_path / "t.sqlite"))
    t = mgr.create(100, host_user_id=1, turn_timeout_s=60, claim_timeout_s=60)
    assert isinstance(t, Table)
    assert t.join(1, "Alice") is None
    assert t.join(2, "Bob") is None
    assert t.join(3, "Carol") is None
    assert t.join(1, "Alice") == "You're already seated."
    assert not t.ready_to_deal()
    assert t.join(4, "Dave") is None
    assert t.ready_to_deal()
    t.deal_hand()
    assert t.status == TableStatus.ACTIVE
    assert t.game is not None
    assert t.leave(2) is not None  # can't leave mid-hand


def test_leave_in_lobby(tmp_path: Path):
    mgr = TableManager(str(tmp_path / "t2.sqlite"))
    t = mgr.create(101, host_user_id=1, turn_timeout_s=30, claim_timeout_s=30)
    assert isinstance(t, Table)
    t.join(1, "A")
    t.join(2, "B")
    assert t.leave(2) is None
    assert t.human_count() == 1


def test_bots_fill_and_solo_ready(tmp_path: Path):
    mgr = TableManager(str(tmp_path / "t3.sqlite"))
    t = mgr.create(
        102,
        host_user_id=1,
        turn_timeout_s=60,
        claim_timeout_s=60,
        bots=3,
        bot_difficulty="easy",
    )
    assert isinstance(t, Table)
    assert t.join(1, "Solo") is None
    assert t.fill_bots(3, difficulty="easy") is None
    assert t.bot_count() == 3
    assert t.human_count() == 1
    assert t.ready_to_deal()
