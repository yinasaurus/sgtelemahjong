"""SQLite persistence: tables, seats, hands, session scores, history."""

from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any


SCHEMA = """
CREATE TABLE IF NOT EXISTS tables (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    status TEXT NOT NULL,
    rules_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    ended_at TEXT,
    final_json TEXT
);

CREATE TABLE IF NOT EXISTS seats (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,
    seat_index INTEGER NOT NULL,
    telegram_user_id INTEGER,
    display_name TEXT NOT NULL,
    is_bot INTEGER NOT NULL DEFAULT 0,
    bot_difficulty TEXT,
    UNIQUE(table_id, seat_index),
    FOREIGN KEY(table_id) REFERENCES tables(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS hands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,
    hand_number INTEGER NOT NULL,
    winner_seat_index INTEGER,
    loser_seat_index INTEGER,
    dealer_seat_index INTEGER NOT NULL DEFAULT 0,
    han INTEGER,
    fu INTEGER,
    points INTEGER,
    yaku_list TEXT,
    reason TEXT,
    deltas_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(table_id) REFERENCES tables(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS session_scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    table_id INTEGER NOT NULL,
    seat_index INTEGER NOT NULL,
    running_total INTEGER NOT NULL,
    UNIQUE(table_id, seat_index),
    FOREIGN KEY(table_id) REFERENCES tables(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_tables_chat ON tables(chat_id);
CREATE INDEX IF NOT EXISTS idx_hands_table ON hands(table_id);
"""


def connect(path: str | Path) -> sqlite3.Connection:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(p)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(path: str | Path) -> None:
    with closing(connect(path)) as conn:
        conn.executescript(SCHEMA)
        conn.commit()


def _active_table_id(conn: sqlite3.Connection, chat_id: int) -> int | None:
    row = conn.execute(
        """
        SELECT id FROM tables
        WHERE chat_id = ? AND status IN ('setup', 'active')
        ORDER BY id DESC LIMIT 1
        """,
        (chat_id,),
    ).fetchone()
    return int(row["id"]) if row else None


def get_active_table_id(path: str | Path, chat_id: int) -> int | None:
    with closing(connect(path)) as conn:
        return _active_table_id(conn, chat_id)


def upsert_table(
    path: str | Path,
    *,
    chat_id: int,
    status: str,
    rules: dict,
    seats: list[dict],
) -> int:
    with closing(connect(path)) as conn:
        tid = _active_table_id(conn, chat_id)
        rules_json = json.dumps(rules)
        if tid is None:
            cur = conn.execute(
                "INSERT INTO tables (chat_id, status, rules_json) VALUES (?, ?, ?)",
                (chat_id, status, rules_json),
            )
            tid = int(cur.lastrowid)
            start = int(rules.get("start_points", 25000))
            for s in seats:
                conn.execute(
                    """
                    INSERT INTO seats (
                        table_id, seat_index, telegram_user_id, display_name, is_bot, bot_difficulty
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tid,
                        int(s["seat_index"]),
                        s.get("telegram_user_id"),
                        s["display_name"],
                        1 if s.get("is_bot") else 0,
                        s.get("bot_difficulty"),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO session_scores (table_id, seat_index, running_total)
                    VALUES (?, ?, ?)
                    """,
                    (tid, int(s["seat_index"]), start),
                )
        else:
            conn.execute(
                "UPDATE tables SET status = ?, rules_json = ? WHERE id = ?",
                (status, rules_json, tid),
            )
            for s in seats:
                conn.execute(
                    """
                    INSERT INTO seats (
                        table_id, seat_index, telegram_user_id, display_name, is_bot, bot_difficulty
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(table_id, seat_index) DO UPDATE SET
                        telegram_user_id=excluded.telegram_user_id,
                        display_name=excluded.display_name,
                        is_bot=excluded.is_bot,
                        bot_difficulty=excluded.bot_difficulty
                    """,
                    (
                        tid,
                        int(s["seat_index"]),
                        s.get("telegram_user_id"),
                        s["display_name"],
                        1 if s.get("is_bot") else 0,
                        s.get("bot_difficulty"),
                    ),
                )
                # ensure score row exists
                conn.execute(
                    """
                    INSERT OR IGNORE INTO session_scores (table_id, seat_index, running_total)
                    VALUES (?, ?, ?)
                    """,
                    (
                        tid,
                        int(s["seat_index"]),
                        int(rules.get("start_points", 25000)),
                    ),
                )
        conn.commit()
        return tid


def delete_active_table(path: str | Path, chat_id: int) -> None:
    """Remove active/setup table for chat (lobby cancel). Completed history kept."""
    with closing(connect(path)) as conn:
        tid = _active_table_id(conn, chat_id)
        if tid is not None:
            conn.execute("DELETE FROM tables WHERE id = ?", (tid,))
            conn.commit()


def delete_table(path: str | Path, chat_id: int) -> None:
    """Backward-compatible: end/cancel active table only."""
    delete_active_table(path, chat_id)


def get_scores(path: str | Path, table_id: int) -> dict[int, int]:
    with closing(connect(path)) as conn:
        rows = conn.execute(
            "SELECT seat_index, running_total FROM session_scores WHERE table_id = ?",
            (table_id,),
        ).fetchall()
        return {int(r["seat_index"]): int(r["running_total"]) for r in rows}


def record_hand(
    path: str | Path,
    *,
    table_id: int,
    hand_number: int,
    winner_seat_index: int | None,
    loser_seat_index: int | None,
    dealer_seat_index: int,
    han: int | None,
    fu: int | None,
    points: int | None,
    yaku_list: list[str],
    reason: str,
    deltas: dict[int, int],
) -> int:
    with closing(connect(path)) as conn:
        cur = conn.execute(
            """
            INSERT INTO hands (
                table_id, hand_number, winner_seat_index, loser_seat_index,
                dealer_seat_index, han, fu, points, yaku_list, reason, deltas_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                table_id,
                hand_number,
                winner_seat_index,
                loser_seat_index,
                dealer_seat_index,
                han,
                fu,
                points,
                json.dumps(yaku_list),
                reason,
                json.dumps({str(k): v for k, v in deltas.items()}),
            ),
        )
        for seat, delta in deltas.items():
            conn.execute(
                """
                UPDATE session_scores
                SET running_total = running_total + ?
                WHERE table_id = ? AND seat_index = ?
                """,
                (int(delta), table_id, int(seat)),
            )
        conn.commit()
        return int(cur.lastrowid)


def undo_last_hand(path: str | Path, table_id: int) -> dict[str, Any] | None:
    with closing(connect(path)) as conn:
        row = conn.execute(
            """
            SELECT * FROM hands WHERE table_id = ?
            ORDER BY id DESC LIMIT 1
            """,
            (table_id,),
        ).fetchone()
        if row is None:
            return None
        deltas = {int(k): int(v) for k, v in json.loads(row["deltas_json"]).items()}
        for seat, delta in deltas.items():
            conn.execute(
                """
                UPDATE session_scores
                SET running_total = running_total - ?
                WHERE table_id = ? AND seat_index = ?
                """,
                (delta, table_id, seat),
            )
        conn.execute("DELETE FROM hands WHERE id = ?", (int(row["id"]),))
        conn.commit()
        return {
            "hand_number": int(row["hand_number"]),
            "reason": row["reason"],
            "deltas": deltas,
        }


def complete_session(
    path: str | Path,
    table_id: int,
    *,
    final_payload: dict,
) -> None:
    with closing(connect(path)) as conn:
        conn.execute(
            """
            UPDATE tables
            SET status = 'completed', ended_at = CURRENT_TIMESTAMP, final_json = ?
            WHERE id = ?
            """,
            (json.dumps(final_payload), table_id),
        )
        conn.commit()


def list_history(path: str | Path, chat_id: int, *, limit: int = 10) -> list[dict]:
    with closing(connect(path)) as conn:
        rows = conn.execute(
            """
            SELECT id, status, created_at, ended_at, final_json, rules_json
            FROM tables
            WHERE chat_id = ? AND status = 'completed'
            ORDER BY id DESC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()
        out = []
        for r in rows:
            out.append(
                {
                    "id": int(r["id"]),
                    "created_at": r["created_at"],
                    "ended_at": r["ended_at"],
                    "final": json.loads(r["final_json"] or "{}"),
                    "rules": json.loads(r["rules_json"] or "{}"),
                }
            )
        return out


def hand_count(path: str | Path, table_id: int) -> int:
    with closing(connect(path)) as conn:
        row = conn.execute(
            "SELECT COUNT(*) AS c FROM hands WHERE table_id = ?", (table_id,)
        ).fetchone()
        return int(row["c"]) if row else 0
