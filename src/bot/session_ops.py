"""Record hand results and format standings / settlement."""

from __future__ import annotations

from mahjong.settlement import SessionRules, format_points, settle_session

from db import models as db

from .state import Table, WIND


def deltas_from_result(table: Table) -> dict[int, int]:
    g = table.game
    assert g is not None and g.result is not None
    r = g.result
    if r.deltas:
        return {i: int(r.deltas.get(i, 0)) for i in range(4)}
    return {i: 0 for i in range(4)}


def record_finished_hand(db_path: str, table: Table) -> dict[int, int] | None:
    """Persist hand + update running totals. Returns new totals or None if skipped."""
    if table.result_recorded or table.db_table_id is None or table.game is None:
        return None
    if table.game.result is None:
        return None
    r = table.game.result
    deltas = deltas_from_result(table)
    sc = r.score
    yaku = [y.name for y in sc.yaku] if sc else []
    loser = None
    payers = [s for s, v in deltas.items() if v < 0]
    if len(payers) == 1:
        loser = payers[0]
    db.record_hand(
        db_path,
        table_id=table.db_table_id,
        hand_number=table.hand_number,
        winner_seat_index=r.winner,
        loser_seat_index=loser,
        dealer_seat_index=table.game.dealer,
        han=sc.han if sc else None,
        fu=sc.fu if sc else None,
        points=sc.gain if sc else None,
        yaku_list=yaku,
        reason=r.reason,
        deltas=deltas,
    )
    table.result_recorded = True
    return db.get_scores(db_path, table.db_table_id)


def standings_text(db_path: str, table: Table) -> str:
    if table.db_table_id is None:
        return "No session."
    scores = db.get_scores(db_path, table.db_table_id)
    lines = [
        f"📊 Standings — hand #{table.hand_number} played",
        "Singapore session — running fan points (start 0)",
        "",
    ]
    if any(table.session_rules.uma) or table.session_rules.return_points:
        lines.insert(
            2,
            f"Uma {'/'.join(str(u // 1000) for u in table.session_rules.uma)} · "
            f"return {table.session_rules.return_points}",
        )
    order = sorted(scores.keys(), key=lambda s: (-scores[s], s))
    for rank, seat in enumerate(order, start=1):
        name = table.seats[seat].display_name
        lines.append(f"{rank}. {WIND[seat]} {name}: {scores[seat]}")
    return "\n".join(lines)


def end_session_text(db_path: str, table: Table) -> str:
    assert table.db_table_id is not None
    scores = db.get_scores(db_path, table.db_table_id)
    dealer = table.game.dealer if table.game else 0
    lines_s = settle_session(scores, table.session_rules, dealer=dealer)
    payload = {
        "abandoned": False,
        "scores": {str(k): v for k, v in scores.items()},
        "names": {str(s.seat_index): s.display_name for s in table.seats},
        "settlement": [
            {
                "seat": ln.seat_index,
                "rank": ln.rank,
                "raw": ln.raw_total,
                "oka": ln.oka_share,
                "uma": ln.uma,
                "final": ln.final,
            }
            for ln in lines_s
        ],
    }
    db.complete_session(db_path, table.db_table_id, final_payload=payload)
    out = ["🏁 Session ended — final fan points", ""]
    if any(table.session_rules.uma) or table.session_rules.return_points:
        out = [
            "🏁 Session ended — settlement (oka + uma)",
            f"Oka pot: {4 * (table.session_rules.return_points - table.session_rules.start_points)}",
            "",
        ]
    for ln in lines_s:
        name = table.seats[ln.seat_index].display_name
        if any(table.session_rules.uma) or table.session_rules.return_points:
            out.append(
                f"#{ln.rank} {WIND[ln.seat_index]} {name}: "
                f"raw {ln.raw_total} · uma {format_points(ln.uma)} · "
                f"oka {format_points(ln.oka_share)} → {format_points(ln.final)}"
            )
        else:
            out.append(
                f"#{ln.rank} {WIND[ln.seat_index]} {name}: {format_points(ln.raw_total)}"
            )
    return "\n".join(out)


def history_text(db_path: str, chat_id: int) -> str:
    rows = db.list_history(db_path, chat_id, limit=8)
    if not rows:
        return "No completed sessions in this chat yet."
    lines = ["📜 Recent sessions"]
    for r in rows:
        final = r["final"]
        sett = final.get("settlement") or []
        if final.get("abandoned"):
            lines.append(f"#{r['id']} {r['ended_at'] or r['created_at']} — abandoned")
            continue
        if sett:
            top = min(sett, key=lambda x: x["rank"])
            name = final.get("names", {}).get(str(top["seat"]), f"seat{top['seat']}")
            lines.append(
                f"#{r['id']} {r['ended_at'] or ''} — 1st {name} ({format_points(top['final'])})"
            )
        else:
            lines.append(f"#{r['id']} {r['ended_at'] or r['created_at']}")
    return "\n".join(lines)
