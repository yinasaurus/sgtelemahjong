import random

from mahjong.game import ClaimType, Game, GamePhase, PlayerState
from mahjong.hand import Hand
from mahjong.tiles import parse_tiles
from mahjong.wall import Wall


def test_deal_shapes():
    g = Game.new_hand(rng=random.Random(0))
    assert g.phase == GamePhase.PLAYING
    assert len(g.players[g.dealer].hand.concealed) == 14
    for s in range(4):
        if s == g.dealer:
            continue
        assert len(g.players[s].hand.concealed) == 13
    assert g.wall.remaining_live == 136 - 14 - (13 * 4 + 1)


def test_discard_opens_claim_window():
    g = Game.new_hand(rng=random.Random(1))
    dealer = g.dealer
    assert g.discard(dealer, 0)
    assert g.phase in (GamePhase.CLAIM_WINDOW, GamePhase.PLAYING)
    if g.phase == GamePhase.PLAYING:
        assert g.turn_seat == (dealer + 1) % 4


def test_ron_priority_over_pon():
    g = Game.new_hand(rng=random.Random(2))
    g.dealer = 0
    g.round_wind = 0
    g.players = [PlayerState() for _ in range(4)]
    g.phase = GamePhase.PLAYING
    g.has_drawn = True
    g.turn_seat = 0

    # Seat 1 can pon East
    g.players[1].hand = Hand(concealed=parse_tiles("EE 123m456m789p12s"))
    assert len(g.players[1].hand.concealed) == 13

    # Seat 2: riichi tenpai on East (tanki; yaku = riichi)
    # 4 sequences (12) + singleton E (1) = 13, waits E
    g.players[2].hand = Hand(concealed=parse_tiles("123m456m789m123p E"))
    g.players[2].riichi = True
    assert len(g.players[2].hand.concealed) == 13

    g.players[3].hand = Hand(concealed=parse_tiles("123456789m123p")[:13])
    g.players[0].hand = Hand(concealed=parse_tiles("111222333444m55p"))
    assert len(g.players[0].hand.concealed) == 14
    g.players[0].hand.concealed[0] = parse_tiles("E")[0]

    assert g.discard(0, 0)
    assert g.phase == GamePhase.CLAIM_WINDOW
    assert ClaimType.PON in g.eligible_claims(1)
    assert ClaimType.RON in g.eligible_claims(2)
    assert g.register_claim(1, ClaimType.PON)
    # ron should resolve immediately (pon dominated)
    assert g.register_claim(2, ClaimType.RON)
    assert g.phase == GamePhase.ENDED
    assert g.result and g.result.winner == 2


def test_furiten_blocks_ron():
    g = Game.new_hand(rng=random.Random(3))
    g.players = [PlayerState() for _ in range(4)]
    g.phase = GamePhase.CLAIM_WINDOW
    g.pending_discard = (0, parse_tiles("E")[0])
    g.players[1].hand.concealed = parse_tiles("123m456m789m123p E")
    g.players[1].riichi = True
    g.players[1].temp_furiten = True
    assert ClaimType.RON not in g.eligible_claims(1)


def test_wall_dora_indicator():
    w = Wall.new(rng=random.Random(0))
    inds = w.dora_indicators()
    assert len(inds) == 1
    w.register_kan()
    assert len(w.dora_indicators()) == 2
