"""Singapore Mahjong game state machine."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .fan import (
    evaluate_fan,
    has_all_dragon_pongs,
    has_all_wind_pongs,
    payout_each,
    payout_win,
)
from .hand import Hand, Meld, MeldType, is_winning_hand
from .tiles import Suit, Tile
from .wall import Wall


class GamePhase(str, Enum):
    PLAYING = "playing"
    CLAIM_WINDOW = "claim_window"
    ENDED = "ended"


class ClaimType(str, Enum):
    PASS = "pass"
    CHI = "chi"
    PON = "pon"
    KAN = "kan"
    RON = "ron"  # SG "Game" win on discard


@dataclass
class ClaimIntent:
    seat: int
    kind: ClaimType
    chi_tiles: tuple[Tile, Tile] | None = None


@dataclass
class ScoreBreakdown:
    """Telegram-facing score stub (maps from FanResult)."""

    yaku: list  # list of objects with .name
    han: int
    fu: int
    gain: int


@dataclass
class _YakuName:
    name: str


@dataclass
class HandResult:
    winner: int | None
    score: ScoreBreakdown | None
    reason: str
    deltas: dict[int, int] = field(default_factory=dict)


@dataclass
class Player:
    hand: Hand = field(default_factory=Hand)
    discards: list[Tile] = field(default_factory=list)
    flowers: list[Tile] = field(default_factory=list)
    animals: list[Tile] = field(default_factory=list)
    points: int = 0
    riichi: bool = False  # unused in SG
    ippatsu_chance: bool = False
    temp_furiten: bool = False
    # tiles this player skipped (for miss rule)
    missed: set[tuple[Suit, int]] = field(default_factory=set)


@dataclass
class Game:
    wall: Wall
    players: list[Player]
    dealer: int = 0
    round_wind: int = 0  # prevailing wind
    turn_seat: int = 0
    phase: GamePhase = GamePhase.PLAYING
    has_drawn: bool = False
    last_draw: Tile | None = None
    last_draw_rinshan: bool = False  # replacement draw
    pending_discard: tuple[int, Tile] | None = None
    pending_chankan: tuple[int, Tile] | None = None
    claim_intents: dict[int, ClaimIntent] = field(default_factory=dict)
    claim_window_id: int = 0
    result: HandResult | None = None
    last_error: str | None = None
    first_turn: bool = True
    honba: int = 0
    riichi_sticks: int = 0
    kans_total: int = 0
    min_fan: int = 1
    max_fan: int = 5
    deal_bonus: bool = True  # opening flowers get double animal-pair payouts

    @classmethod
    def new_hand(
        cls,
        *,
        dealer: int = 0,
        round_wind: int = 0,
        honba: int = 0,
        riichi_sticks: int = 0,
        seed: int | None = None,
    ) -> Game:
        import random

        rng = random.Random(seed)
        wall = Wall.shuffled(rng)
        players = [Player() for _ in range(4)]
        # Deal 13 each
        for _ in range(13):
            for s in range(4):
                t = wall.draw()
                assert t is not None
                players[s].hand.concealed.append(t)
        g = cls(
            wall=wall,
            players=players,
            dealer=dealer,
            round_wind=round_wind,
            turn_seat=dealer,
            honba=honba,
            riichi_sticks=riichi_sticks,
        )
        # Expose opening flowers/animals + replacements
        for s in range(4):
            g._flush_bonuses(s, from_deal=True)
            g.players[s].hand.sort()
        # Banker draws
        g._draw_for_turn(dealer)
        g.deal_bonus = False
        return g

    def clear_error(self) -> None:
        self.last_error = None

    def seat_wind(self, seat: int) -> int:
        """Banker=East(0), then S, W, N counterclockwise (= +1 seat)."""
        return (seat - self.dealer) % 4

    def is_furiten(self, seat: int) -> bool:
        return self.players[seat].temp_furiten

    def dora_tile_types(self) -> list[Tile]:
        return []

    # --- bonuses ---
    def _flush_bonuses(self, seat: int, *, from_deal: bool = False) -> list[dict]:
        """Move flowers/animals to exposed; take replacements. Return payout events."""
        events: list[dict] = []
        p = self.players[seat]
        guard = 0
        while guard < 20:
            guard += 1
            bonus = next((t for t in p.hand.concealed if t.is_bonus), None)
            if bonus is None:
                break
            p.hand.concealed.remove(bonus)
            if bonus.is_flower:
                p.flowers.append(bonus)
            else:
                p.animals.append(bonus)
            # Immediate set payouts
            ev = self._check_bonus_payouts(seat, from_deal=from_deal)
            events.extend(ev)
            # Eight flowers auto-win
            if len(p.flowers) >= 8:
                self._win_special(seat, "eight_flowers", tsumo=True)
                return events
            # Seven flowers: if someone else draws 8th, handled on their flush
            rep = self.wall.draw_replacement()
            if rep is None:
                break
            p.hand.concealed.append(rep)
            self.last_draw = rep
            self.last_draw_rinshan = True
        p.hand.sort()
        # All dragons / winds auto-win
        if has_all_dragon_pongs(p.hand.melds):
            self._win_special(seat, "all_dragons", tsumo=True)
        elif has_all_wind_pongs(p.hand.melds):
            self._win_special(seat, "all_winds", tsumo=True)
        return events

    def _check_bonus_payouts(self, seat: int, *, from_deal: bool) -> list[dict]:
        events: list[dict] = []
        p = self.players[seat]
        mult = 2 if from_deal else 1
        animals = {(a.value) for a in p.animals}
        # cat+mouse = 0,1 ; chicken+centipede = 2,3
        if 0 in animals and 1 in animals and not getattr(p, "_paid_cat", False):
            d = payout_each(seat, 2 * mult)
            self._apply_deltas(d)
            p._paid_cat = True  # type: ignore[attr-defined]
            events.append({"kind": "cat_mouse", "deltas": d})
        if 2 in animals and 3 in animals and not getattr(p, "_paid_chick", False):
            d = payout_each(seat, 2 * mult)
            self._apply_deltas(d)
            p._paid_chick = True  # type: ignore[attr-defined]
            events.append({"kind": "chick_centi", "deltas": d})
        if len(p.animals) == 4 and not getattr(p, "_paid_animals", False):
            d = payout_each(seat, 4)
            self._apply_deltas(d)
            p._paid_animals = True  # type: ignore[attr-defined]
            events.append({"kind": "animals", "deltas": d})
        seasons = [t for t in p.flowers if t.is_season_set]
        flo = [t for t in p.flowers if t.is_flower_set]
        if len(seasons) == 4 and not getattr(p, "_paid_season", False):
            d = payout_each(seat, 4)
            self._apply_deltas(d)
            p._paid_season = True  # type: ignore[attr-defined]
            events.append({"kind": "seasons", "deltas": d})
        if len(flo) == 4 and not getattr(p, "_paid_flo", False):
            d = payout_each(seat, 4)
            self._apply_deltas(d)
            p._paid_flo = True  # type: ignore[attr-defined]
            events.append({"kind": "flower_set", "deltas": d})
        # both seat flowers
        seat_f = [t for t in p.flowers if t.flower_wind == self.seat_wind(seat)]
        if len(seat_f) >= 2 and not getattr(p, "_paid_seat_flo", False):
            d = payout_each(seat, 2 * mult)
            self._apply_deltas(d)
            p._paid_seat_flo = True  # type: ignore[attr-defined]
            events.append({"kind": "seat_flowers", "deltas": d})
        # steal 8th flower
        if len(p.flowers) == 7:
            pass  # wait for 8th on own draw
        return events

    def _apply_deltas(self, deltas: dict[int, int]) -> None:
        for s, v in deltas.items():
            self.players[s].points += v

    def _draw_for_turn(self, seat: int) -> None:
        if self.wall.remaining_live <= 0:
            self._exhaustive_draw()
            return
        t = self.wall.draw()
        if t is None:
            self._exhaustive_draw()
            return
        self.players[seat].hand.concealed.append(t)
        self.turn_seat = seat
        self.has_drawn = True
        self.last_draw = t
        self.last_draw_rinshan = False
        self.players[seat].temp_furiten = False
        self.players[seat].missed.clear()
        self._flush_bonuses(seat)
        if self.phase == GamePhase.ENDED:
            return
        # Last tile rule: if wall exhausted after this draw, can still win/kong
        if self.wall.remaining_live <= 0:
            pass

    # --- actions ---
    def can_tsumo(self, seat: int) -> bool:
        if self.phase != GamePhase.PLAYING or seat != self.turn_seat or not self.has_drawn:
            return False
        return self._can_win(seat, tsumo=True, win_tile=None)

    def declare_tsumo(self, seat: int) -> bool:
        self.clear_error()
        if not self.can_tsumo(seat):
            self.last_error = "Cannot win (need mahjong + min fan)."
            return False
        return self._declare_win(seat, tsumo=True, discarder=None)

    def can_riichi(self, seat: int) -> bool:
        return False

    def declare_riichi(self, seat: int, index: int) -> bool:
        self.last_error = "No riichi in Singapore Mahjong."
        return False

    def can_ankan(self, seat: int, tile: Tile) -> bool:
        if self.phase != GamePhase.PLAYING or seat != self.turn_seat or not self.has_drawn:
            return False
        if tile.is_bonus:
            return False
        n = sum(1 for t in self.players[seat].hand.concealed if t.same_tile(tile))
        return n >= 4

    def declare_ankan(self, seat: int, tile: Tile) -> bool:
        """Kong-4 concealed."""
        self.clear_error()
        if not self.can_ankan(seat, tile):
            self.last_error = "Cannot closed kong."
            return False
        hand = self.players[seat].hand
        used = [t for t in hand.concealed if t.same_tile(tile)][:4]
        for t in used:
            hand.concealed.remove(t)
        hand.melds.append(Meld(MeldType.ANKAN, tuple(used)))
        self._after_kong(seat)
        return True

    def can_shouminkan(self, seat: int, tile: Tile) -> bool:
        if self.phase != GamePhase.PLAYING or seat != self.turn_seat or not self.has_drawn:
            return False
        has_pon = any(
            m.type == MeldType.PON and m.tiles[0].same_tile(tile)
            for m in self.players[seat].hand.melds
        )
        has_tile = any(t.same_tile(tile) for t in self.players[seat].hand.concealed)
        return has_pon and has_tile

    def declare_shouminkan(self, seat: int, tile: Tile) -> bool:
        """Kong-1: add to exposed pon — robable."""
        self.clear_error()
        if not self.can_shouminkan(seat, tile):
            self.last_error = "Can't add kong — need an open pong of that tile."
            return False
        hand = self.players[seat].hand
        for t in list(hand.concealed):
            if t.same_tile(tile):
                hand.concealed.remove(t)
                added = t
                break
        else:
            self.last_error = "Missing tile."
            return False
        for i, m in enumerate(hand.melds):
            if m.type == MeldType.PON and m.tiles[0].same_tile(tile):
                hand.melds[i] = Meld(
                    MeldType.MINKAN,
                    tuple(list(m.tiles) + [added]),
                    called_from=m.called_from,
                    called_tile=m.called_tile,
                )
                break
        self.pending_chankan = (seat, tile)
        self.claim_intents = {}
        self.claim_window_id += 1
        self.phase = GamePhase.CLAIM_WINDOW
        self._auto_pass_ineligible()
        if self._intents_ready():
            self.resolve_claims()
        return True

    def _after_kong(self, seat: int) -> None:
        d = payout_each(seat, 2)
        self._apply_deltas(d)
        self.kans_total += 1
        if self.wall.remaining_live <= 0:
            self.has_drawn = True
            self.turn_seat = seat
            return
        rep = self.wall.draw_replacement()
        if rep is None:
            self._exhaustive_draw()
            return
        self.players[seat].hand.concealed.append(rep)
        self.has_drawn = True
        self.last_draw = rep
        self.last_draw_rinshan = True
        self.turn_seat = seat
        self._flush_bonuses(seat)

    def discard(self, seat: int, index: int) -> bool:
        self.clear_error()
        if self.phase != GamePhase.PLAYING or seat != self.turn_seat or not self.has_drawn:
            self.last_error = "Cannot discard now."
            return False
        p = self.players[seat]
        if not 0 <= index < len(p.hand.concealed):
            self.last_error = "Bad index."
            return False
        tile = p.hand.concealed.pop(index)
        if tile.is_bonus:
            p.hand.concealed.insert(index, tile)
            self.last_error = "Expose flower/animal instead of discarding."
            return False
        p.discards.append(tile)
        p.hand.sort()
        self.has_drawn = False
        self.last_draw = None
        self.last_draw_rinshan = False
        self.pending_discard = (seat, tile)
        self.claim_intents = {}
        self.claim_window_id += 1
        self.first_turn = False
        self.phase = GamePhase.CLAIM_WINDOW
        self._auto_pass_ineligible()
        if self._intents_ready():
            self.resolve_claims()
        return True

    def eligible_claims(self, seat: int) -> set[ClaimType]:
        if self.phase == GamePhase.CLAIM_WINDOW and self.pending_chankan:
            if seat == self.pending_chankan[0]:
                return set()
            if self._can_win(seat, tsumo=False, win_tile=self.pending_chankan[1], rob=True):
                return {ClaimType.RON}
            return set()
        if self.phase != GamePhase.CLAIM_WINDOW or self.pending_discard is None:
            return set()
        discarder, tile = self.pending_discard
        if seat == discarder:
            return set()
        out: set[ClaimType] = set()
        if self._can_win(seat, tsumo=False, win_tile=tile):
            out.add(ClaimType.RON)
        key = (tile.suit, tile.value)
        if key not in self.players[seat].missed:
            n = sum(1 for t in self.players[seat].hand.concealed if t.same_tile(tile))
            if n >= 3:
                out.add(ClaimType.KAN)
            if n >= 2:
                out.add(ClaimType.PON)
        if seat == (discarder + 1) % 4 and tile.is_suited:
            if self.chi_options(seat, tile):
                out.add(ClaimType.CHI)
        return out

    def chi_options(self, seat: int, tile: Tile) -> list[tuple[Tile, Tile]]:
        if not tile.is_suited:
            return []
        hand = self.players[seat].hand.concealed
        opts: list[tuple[Tile, Tile]] = []
        v, suit = tile.value, tile.suit
        for a, b in ((v - 2, v - 1), (v - 1, v + 1), (v + 1, v + 2)):
            if not (1 <= a <= 9 and 1 <= b <= 9):
                continue
            ta = next((t for t in hand if t.suit == suit and t.value == a), None)
            tb = next(
                (t for t in hand if t.suit == suit and t.value == b and t is not ta),
                None,
            )
            if ta and tb:
                opts.append((ta, tb))
        return opts

    def _can_win(
        self,
        seat: int,
        *,
        tsumo: bool,
        win_tile: Tile | None,
        rob: bool = False,
    ) -> bool:
        p = self.players[seat]
        if not tsumo and win_tile is not None:
            key = (win_tile.suit, win_tile.value)
            if key in p.missed:
                return False
            if p.discards and p.discards[-1].same_tile(win_tile):
                return False
        fr = evaluate_fan(
            p.hand,
            flowers=p.flowers,
            animals=p.animals,
            win_tile=win_tile,
            tsumo=tsumo,
            seat_wind=self.seat_wind(seat),
            round_wind=self.round_wind,
            replacement_win=tsumo and self.last_draw_rinshan,
            last_tile_win=self.wall.remaining_live <= 0,
            rob_kong=rob,
            min_fan=self.min_fan,
            max_fan=self.max_fan,
        )
        return fr is not None

    def register_claim(
        self,
        seat: int,
        kind: ClaimType,
        *,
        chi_tiles: tuple[Tile, Tile] | None = None,
    ) -> bool:
        self.clear_error()
        if self.phase != GamePhase.CLAIM_WINDOW:
            self.last_error = "No claim window."
            return False
        if kind == ClaimType.PASS:
            self.claim_intents[seat] = ClaimIntent(seat, ClaimType.PASS)
            if self.pending_discard:
                _, tile = self.pending_discard
                elig = self.eligible_claims(seat)
                if ClaimType.RON in elig or ClaimType.PON in elig or ClaimType.KAN in elig:
                    self.players[seat].missed.add((tile.suit, tile.value))
                    if ClaimType.RON in elig:
                        self.players[seat].temp_furiten = True
            if self._intents_ready():
                self.resolve_claims()
            return True
        elig = self.eligible_claims(seat)
        if kind not in elig:
            self.last_error = f"Cannot {kind.value}."
            return False
        if kind == ClaimType.CHI and chi_tiles is None:
            self.last_error = "Chi needs tiles."
            return False
        self.claim_intents[seat] = ClaimIntent(seat, kind, chi_tiles=chi_tiles)
        self._auto_pass_dominated()
        if self._intents_ready():
            self.resolve_claims()
        return True

    def _auto_pass_ineligible(self) -> None:
        for s in range(4):
            if s in self.claim_intents:
                continue
            if self.pending_discard and s == self.pending_discard[0]:
                continue
            if self.pending_chankan and s == self.pending_chankan[0]:
                continue
            if not self.eligible_claims(s):
                self.claim_intents[s] = ClaimIntent(s, ClaimType.PASS)

    def _auto_pass_dominated(self) -> None:
        active = [
            (s, i.kind)
            for s, i in self.claim_intents.items()
            if i.kind != ClaimType.PASS
        ]
        if not active:
            return

        def rank(k: ClaimType) -> float:
            return {
                ClaimType.RON: 4,
                ClaimType.KAN: 3.5,
                ClaimType.PON: 3,
                ClaimType.CHI: 1,
            }.get(k, 0)

        best = max(rank(k) for _, k in active)
        source = (
            self.pending_chankan[0]
            if self.pending_chankan
            else self.pending_discard[0]  # type: ignore[index]
        )

        def dist(s: int) -> int:
            return (s - source) % 4

        leaders = [s for s, k in active if rank(k) == best]
        leader = min(leaders, key=dist)
        for s in range(4):
            if s in self.claim_intents:
                continue
            if self.pending_discard and s == self.pending_discard[0]:
                continue
            if self.pending_chankan and s == self.pending_chankan[0]:
                continue
            elig = self.eligible_claims(s)
            can_beat = False
            for k in elig:
                r = rank(k)
                if r > best or (r == best and dist(s) < dist(leader)):
                    can_beat = True
                    break
            if not can_beat:
                self.claim_intents[s] = ClaimIntent(s, ClaimType.PASS)

    def _intents_ready(self) -> bool:
        needed = set(range(4))
        if self.pending_discard:
            needed.discard(self.pending_discard[0])
        if self.pending_chankan:
            needed.discard(self.pending_chankan[0])
        return needed <= set(self.claim_intents)

    def resolve_claims(self) -> str:
        if not self._intents_ready():
            return "none"

        def rank(k: ClaimType) -> float:
            return {
                ClaimType.RON: 4,
                ClaimType.KAN: 3.5,
                ClaimType.PON: 3,
                ClaimType.CHI: 1,
                ClaimType.PASS: 0,
            }[k]

        source = (
            self.pending_chankan[0]
            if self.pending_chankan
            else self.pending_discard[0]  # type: ignore[index]
        )
        rons = [s for s, i in self.claim_intents.items() if i.kind == ClaimType.RON]
        if rons:
            # Closest counterclockwise from discarder wins (SG)
            winner = min(rons, key=lambda s: (s - source) % 4)
            tile = (
                self.pending_chankan[1]
                if self.pending_chankan
                else self.pending_discard[1]  # type: ignore[index]
            )
            rob = bool(self.pending_chankan)
            if self.pending_chankan:
                self._abort_shouminkan()
            self._declare_win(
                winner, tsumo=False, discarder=source, win_tile=tile, rob=rob
            )
            return "ron"

        for kind in (ClaimType.KAN, ClaimType.PON, ClaimType.CHI):
            cands = [s for s, i in self.claim_intents.items() if i.kind == kind]
            if not cands:
                continue
            winner = min(cands, key=lambda s: (s - source) % 4)
            intent = self.claim_intents[winner]
            if kind == ClaimType.KAN:
                self._apply_daiminkan(winner)
            elif kind == ClaimType.PON:
                self._apply_pon(winner)
            else:
                self._apply_chi(winner, intent.chi_tiles)
            self.pending_discard = None
            self.claim_intents = {}
            self.phase = GamePhase.PLAYING
            for pl in self.players:
                pl.temp_furiten = False
            return kind.value

        self._pass_discard()
        return "pass"

    def _abort_shouminkan(self) -> None:
        return

    def _apply_pon(self, seat: int) -> None:
        discarder, tile = self.pending_discard  # type: ignore[misc]
        hand = self.players[seat].hand
        used = [t for t in hand.concealed if t.same_tile(tile)][:2]
        for t in used:
            hand.concealed.remove(t)
        hand.melds.append(
            Meld(MeldType.PON, (tile, used[0], used[1]), called_from=discarder, called_tile=tile)
        )
        hand.sort()
        self.turn_seat = seat
        self.has_drawn = True
        self.last_draw = None
        self.players[seat].missed.clear()

    def _apply_daiminkan(self, seat: int) -> None:
        discarder, tile = self.pending_discard  # type: ignore[misc]
        hand = self.players[seat].hand
        used = [t for t in hand.concealed if t.same_tile(tile)][:3]
        for t in used:
            hand.concealed.remove(t)
        hand.melds.append(
            Meld(
                MeldType.MINKAN,
                (tile, used[0], used[1], used[2]),
                called_from=discarder,
                called_tile=tile,
            )
        )
        self.pending_discard = None
        self.claim_intents = {}
        self.phase = GamePhase.PLAYING
        self._after_kong(seat)

    def _apply_chi(self, seat: int, chi_tiles: tuple[Tile, Tile] | None) -> None:
        discarder, tile = self.pending_discard  # type: ignore[misc]
        assert chi_tiles is not None
        hand = self.players[seat].hand

        def take(x: Tile) -> Tile:
            for t in hand.concealed:
                if t.same_tile(x):
                    hand.concealed.remove(t)
                    return t
            raise RuntimeError("chi tiles missing")

        ta, tb = take(chi_tiles[0]), take(chi_tiles[1])
        tiles = tuple(sorted([tile, ta, tb], key=lambda t: t.key()))
        hand.melds.append(
            Meld(MeldType.CHI, tiles, called_from=discarder, called_tile=tile)
        )
        hand.sort()
        self.turn_seat = seat
        self.has_drawn = True
        self.last_draw = None
        self.players[seat].missed.clear()

    def _pass_discard(self) -> None:
        if self.pending_chankan is not None:
            seat = self.pending_chankan[0]
            self.pending_chankan = None
            self.claim_intents = {}
            self.phase = GamePhase.PLAYING
            self._after_kong(seat)
            return
        discarder, _ = self.pending_discard  # type: ignore[misc]
        self.pending_discard = None
        self.claim_intents = {}
        self.phase = GamePhase.PLAYING
        next_seat = (discarder + 1) % 4
        if self.wall.remaining_live <= Wall.END_LIVE and self.wall.remaining_live <= 0:
            self._exhaustive_draw()
            return
        if self.wall.remaining_live <= 0:
            self._exhaustive_draw()
            return
        self._draw_for_turn(next_seat)

    def force_timeout_passes(self) -> None:
        if self.phase != GamePhase.CLAIM_WINDOW:
            return
        for s in range(4):
            if s not in self.claim_intents:
                if self.pending_discard and s == self.pending_discard[0]:
                    continue
                if self.pending_chankan and s == self.pending_chankan[0]:
                    continue
                self.register_claim(s, ClaimType.PASS)

    def _declare_win(
        self,
        seat: int,
        *,
        tsumo: bool,
        discarder: int | None,
        win_tile: Tile | None = None,
        rob: bool = False,
    ) -> bool:
        p = self.players[seat]
        fr = evaluate_fan(
            p.hand,
            flowers=p.flowers,
            animals=p.animals,
            win_tile=win_tile,
            tsumo=tsumo,
            seat_wind=self.seat_wind(seat),
            round_wind=self.round_wind,
            replacement_win=tsumo and self.last_draw_rinshan,
            last_tile_win=self.wall.remaining_live <= 0,
            rob_kong=rob,
            min_fan=self.min_fan,
            max_fan=self.max_fan,
        )
        if fr is None:
            self.last_error = "Not a valid win."
            return False
        fan = fr.capped(self.max_fan)
        # 13 wonders treated as self-draw for payout
        treat_tsumo = tsumo or fr.special == "thirteen_wonders"
        deltas = payout_win(
            fan,
            tsumo=treat_tsumo,
            discarder=None if treat_tsumo else discarder,
            winner=seat,
            max_fan=self.max_fan,
        )
        self._apply_deltas(deltas)
        gain = deltas[seat]
        self.phase = GamePhase.ENDED
        self.result = HandResult(
            winner=seat,
            score=ScoreBreakdown(
                yaku=[_YakuName(i.name) for i in fr.items if i.fan or i.name],
                han=fan,
                fu=0,
                gain=gain,
            ),
            reason="tsumo" if tsumo else ("chankan" if rob else "ron"),
            deltas=deltas,
        )
        self.pending_discard = None
        self.pending_chankan = None
        self.claim_intents = {}
        return True

    def _win_special(self, seat: int, kind: str, *, tsumo: bool) -> None:
        p = self.players[seat]
        fr = evaluate_fan(
            p.hand,
            flowers=p.flowers,
            animals=p.animals,
            win_tile=None,
            tsumo=True,
            seat_wind=self.seat_wind(seat),
            round_wind=self.round_wind,
            min_fan=0,
            max_fan=12,
        )
        # force special
        from .fan import FanItem, FanResult

        special_fan = {
            "eight_flowers": 12,
            "all_dragons": 7,
            "all_winds": 12,
        }[kind]
        fr = FanResult(
            items=[FanItem(kind.replace("_", " ").title(), special_fan)],
            special=kind,
        )
        fan = min(special_fan, 12)
        deltas = payout_win(fan, tsumo=True, discarder=None, winner=seat, max_fan=12)
        self._apply_deltas(deltas)
        self.phase = GamePhase.ENDED
        self.result = HandResult(
            winner=seat,
            score=ScoreBreakdown(
                yaku=[_YakuName(i.name) for i in fr.items],
                han=fan,
                fu=0,
                gain=deltas[seat],
            ),
            reason=kind,
            deltas=deltas,
        )

    def _exhaustive_draw(self) -> None:
        self.phase = GamePhase.ENDED
        self.result = HandResult(winner=None, score=None, reason="draw")
        self.pending_discard = None
        self.claim_intents = {}

    def _index_of_last_draw(self, seat: int) -> int | None:
        if self.last_draw is None:
            return None
        hand = self.players[seat].hand.concealed
        for i in range(len(hand) - 1, -1, -1):
            if hand[i] is self.last_draw or hand[i].same_tile(self.last_draw):
                return i
        return None
