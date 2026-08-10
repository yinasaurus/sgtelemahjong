"""Session point totals and uma/oka settlement (pure math, no Telegram)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SessionRules:
    # SG sessions often start at 0 and track +/- fan points
    start_points: int = 0
    return_points: int = 0
    uma: tuple[int, int, int, int] = (0, 0, 0, 0)
    length: str = "hanchan"  # unused hint


@dataclass(frozen=True)
class SettlementLine:
    seat_index: int
    rank: int
    raw_total: int
    oka_share: int
    uma: int
    final: int


def oka_pool(rules: SessionRules) -> int:
    """Total oka pot: each player 'owes' (return - start) into the pot for 1st."""
    return 4 * (rules.return_points - rules.start_points)


def rank_seats(totals: dict[int, int], *, dealer: int = 0) -> list[int]:
    """
    Rank seats by score descending.
    Ties: lower seat index closer to dealer wins (dealer first, then ccw).
    """
    seats = list(totals.keys())

    def key(s: int) -> tuple:
        # higher score better; for ties, smaller distance from dealer better
        dist = (s - dealer) % 4
        return (-totals[s], dist)

    return sorted(seats, key=key)


def settle_session(
    totals: dict[int, int],
    rules: SessionRules,
    *,
    dealer: int = 0,
) -> list[SettlementLine]:
    """
    Apply oka (all to 1st) + uma by rank.
    `totals` are running chip counts (usually start + hand deltas).
    """
    order = rank_seats(totals, dealer=dealer)
    pool = oka_pool(rules)
    lines: list[SettlementLine] = []
    for rank_i, seat in enumerate(order):
        rank = rank_i + 1
        oka = pool if rank == 1 else 0
        uma = rules.uma[rank_i]
        raw = totals[seat]
        # Final settlement vs return_points baseline is common for display:
        # final = (raw - return) + uma + oka_share
        # Equivalently many clubs show: raw + uma + oka - start, etc.
        # We use: final = raw - rules.return_points + uma + oka
        final = raw - rules.return_points + uma + oka
        lines.append(
            SettlementLine(
                seat_index=seat,
                rank=rank,
                raw_total=raw,
                oka_share=oka,
                uma=uma,
                final=final,
            )
        )
    return lines


def format_points(n: int) -> str:
    sign = "+" if n > 0 else ""
    return f"{sign}{n}"
