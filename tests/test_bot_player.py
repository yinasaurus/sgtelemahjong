"""Bot decision engine tests (easy first, plus normal sanity)."""

from __future__ import annotations

import random

from mahjong.bot_player import (
    BotDifficulty,
    ClaimDecision,
    apply_claim_decision,
    apply_turn_decision,
    choose_claim_action,
    choose_discard_index,
    choose_turn_action,
)
from mahjong.game import ClaimType, Game, GamePhase, PlayerState
from mahjong.hand import Hand
from mahjong.tiles import parse_tiles


def test_easy_discard_is_legal_index():
    g = Game.new_hand(rng=random.Random(0))
    seat = g.turn_seat
    assert g.has_drawn
    idx = choose_discard_index(
        g, seat, difficulty=BotDifficulty.EASY, rng=random.Random(1)
    )
    assert 0 <= idx < len(g.players[seat].hand.concealed)


def test_easy_turn_can_discard():
    g = Game.new_hand(rng=random.Random(2))
    seat = g.turn_seat
    d = choose_turn_action(
        g, seat, difficulty=BotDifficulty.EASY, rng=random.Random(3)
    )
    assert d.kind in ("discard", "riichi", "tsumo", "ankan", "shouminkan")
    label = apply_turn_decision(g, seat, d)
    assert label in ("discard", "riichi", "tsumo", "ankan", "shouminkan")
    assert g.phase in (GamePhase.CLAIM_WINDOW, GamePhase.PLAYING, GamePhase.ENDED)


def test_easy_claim_never_rons_when_furiten():
    g = Game.new_hand(rng=random.Random(4))
    g.players = [PlayerState() for _ in range(4)]
    g.phase = GamePhase.CLAIM_WINDOW
    g.pending_discard = (0, parse_tiles("E")[0])
    g.players[1].hand = Hand(concealed=parse_tiles("123m456m789m123p E"))
    g.players[1].riichi = True
    g.players[1].temp_furiten = True
    # Engine blocks ron
    assert ClaimType.RON not in g.eligible_claims(1)
    d = choose_claim_action(
        g, 1, difficulty=BotDifficulty.EASY, rng=random.Random(0)
    )
    assert d.kind != ClaimType.RON


def test_normal_prefers_ron_when_available():
    g = Game.new_hand(rng=random.Random(5))
    g.dealer = 0
    g.players = [PlayerState() for _ in range(4)]
    g.phase = GamePhase.CLAIM_WINDOW
    g.pending_discard = (0, parse_tiles("E")[0])
    g.players[1].hand = Hand(concealed=parse_tiles("123m456m789m123p E"))
    g.players[1].riichi = True
    assert ClaimType.RON in g.eligible_claims(1)
    d = choose_claim_action(
        g, 1, difficulty=BotDifficulty.NORMAL, rng=random.Random(0)
    )
    assert d.kind == ClaimType.RON


def test_apply_claim_pass():
    g = Game.new_hand(rng=random.Random(6))
    # Force claim window with a discard that others pass
    seat = g.turn_seat
    assert g.discard(seat, 0)
    if g.phase == GamePhase.CLAIM_WINDOW:
        for s in range(4):
            if s == seat:
                continue
            if s not in g.claim_intents:
                apply_claim_decision(g, s, ClaimDecision(ClaimType.PASS))
        assert g.phase in (GamePhase.PLAYING, GamePhase.ENDED)
