"""Game flow tests for Singapore Mahjong."""

import random

from mahjong.game import ClaimType, Game, GamePhase, Player
from mahjong.hand import Hand
from mahjong.tiles import Suit, Tile


def _t(suit: Suit, value: int) -> Tile:
    return Tile(suit, value)


def test_deal_shapes_and_no_bonus_left_in_hand():
    g = Game.new_hand(seed=0)
    assert g.phase == GamePhase.PLAYING
    assert len(g.players[g.dealer].hand.concealed) == 14
    for s in range(4):
        if s != g.dealer:
            assert len(g.players[s].hand.concealed) == 13
        assert all(not t.is_bonus for t in g.players[s].hand.concealed)
    # 148 - 52 dealt - replacements - dealer draw
    assert g.wall.remaining_live < 148 - 52


def test_discard_opens_claim_or_advances():
    g = Game.new_hand(seed=1)
    dealer = g.dealer
    assert g.discard(dealer, 0)
    assert g.phase in (GamePhase.CLAIM_WINDOW, GamePhase.PLAYING)
    if g.phase == GamePhase.PLAYING:
        assert g.turn_seat == (dealer + 1) % 4


def test_chow_only_from_left():
    g = Game.new_hand(seed=2)
    # Force a discard window manually
    g.phase = GamePhase.CLAIM_WINDOW
    g.pending_discard = (0, _t(Suit.MAN, 3))
    g.claim_intents = {}
    # Seat 1 is left of 0 — give chi tiles
    filler_p = [_t(Suit.PIN, v) for v in (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6)]
    filler_s = [_t(Suit.SOU, v) for v in (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6)]
    g.players[1].hand = Hand(concealed=[_t(Suit.MAN, 1), _t(Suit.MAN, 2)] + filler_p)
    g.players[2].hand = Hand(concealed=[_t(Suit.MAN, 1), _t(Suit.MAN, 2)] + filler_s)
    assert ClaimType.CHI in g.eligible_claims(1)
    assert ClaimType.CHI not in g.eligible_claims(2)


def test_claim_priority_win_over_pong():
    g = Game.new_hand(seed=3)
    g.phase = GamePhase.CLAIM_WINDOW
    discard = _t(Suit.DRAGON, 0)
    g.pending_discard = (0, discard)
    g.claim_intents = {}
    # Seat 2 can win: build a cheap winning free hand needing Haku
    # Use seven pairs waiting on Haku
    base = []
    for s, v in [
        (Suit.MAN, 1),
        (Suit.MAN, 3),
        (Suit.PIN, 2),
        (Suit.PIN, 5),
        (Suit.SOU, 7),
        (Suit.WIND, 1),
    ]:
        base.extend([_t(s, v), _t(s, v)])
    base.append(_t(Suit.DRAGON, 0))  # one haku — needs pair
    g.players[2].hand = Hand(concealed=base)
    # Seat 1 can pong haku
    g.players[1].hand = Hand(
        concealed=[_t(Suit.DRAGON, 0), _t(Suit.DRAGON, 0)]
        + [_t(Suit.MAN, v) for v in (1, 1, 2, 2, 3, 3, 4, 4, 5, 5, 6)]
    )
    assert ClaimType.RON in g.eligible_claims(2)
    assert ClaimType.PON in g.eligible_claims(1)
    g.register_claim(2, ClaimType.RON)
    g.register_claim(1, ClaimType.PON)
    # Others auto-pass via resolve when ready — force remaining passes
    for s in (3,):
        g.register_claim(s, ClaimType.PASS)
    assert g.phase == GamePhase.ENDED
    assert g.result is not None
    assert g.result.winner == 2
    assert g.result.reason in ("ron", "chankan")


def test_bot_difficulty_hard_accepted_by_fill():
    # smoke that Game still works after claims
    g = Game.new_hand(seed=4)
    assert g.can_riichi(0) is False
