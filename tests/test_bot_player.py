"""Bot decision tests for Singapore Mahjong."""

import random

from mahjong.bot_player import (
    BotDifficulty,
    ClaimDecision,
    choose_claim_action,
    choose_discard_index,
    choose_turn_action,
)
from mahjong.game import ClaimType, Game, GamePhase
from mahjong.hand import Hand
from mahjong.tiles import Suit, Tile


def _t(suit: Suit, value: int) -> Tile:
    return Tile(suit, value)


def test_bot_normal_always_takes_ron():
    g = Game.new_hand(seed=10)
    g.phase = GamePhase.CLAIM_WINDOW
    g.pending_discard = (0, _t(Suit.SOU, 4))
    # Seat 1 tenpai on 4s with closed chow hand minus one 4s
    tiles = [
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
    ]
    g.players[1].hand = Hand(concealed=tiles)
    assert ClaimType.RON in g.eligible_claims(1)
    d = choose_claim_action(g, 1, difficulty=BotDifficulty.NORMAL, rng=random.Random(0))
    assert d.kind == ClaimType.RON


def test_choose_discard_index_in_range():
    g = Game.new_hand(seed=11)
    seat = g.turn_seat
    idx = choose_discard_index(g, seat, difficulty=BotDifficulty.HARD, rng=random.Random(1))
    assert 0 <= idx < len(g.players[seat].hand.concealed)


def test_choose_turn_tsumo_when_possible(monkeypatch):
    g = Game.new_hand(seed=12)
    seat = g.turn_seat

    def _yes(_seat: int) -> bool:
        return True

    monkeypatch.setattr(g, "can_tsumo", _yes)
    d = choose_turn_action(g, seat, difficulty=BotDifficulty.NORMAL, rng=random.Random(0))
    assert d.kind == "tsumo"
