"""Per-chat table manager (lobby + active hand)."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from mahjong.bot_player import BOT_NAMES, BotDifficulty
from mahjong.game import Game
from mahjong.settlement import SessionRules
from mahjong.tiles import Tile

from db import models as db


class TableStatus(str, Enum):
    SETUP = "setup"
    ACTIVE = "active"
    COMPLETED = "completed"


WIND = ("E", "S", "W", "N")


@dataclass
class Seat:
    seat_index: int
    user_id: int | None
    display_name: str
    is_bot: bool = False
    bot_difficulty: str | None = None

    @property
    def occupied(self) -> bool:
        return self.user_id is not None or self.is_bot


@dataclass
class Table:
    chat_id: int
    status: TableStatus = TableStatus.SETUP
    seats: list[Seat] = field(default_factory=list)
    host_user_id: int | None = None
    turn_timeout_s: int = 60
    claim_timeout_s: int = 60
    bot_difficulty: str = BotDifficulty.NORMAL.value
    reserved_bots: int = 0
    session_rules: SessionRules = field(default_factory=SessionRules)
    db_table_id: int | None = None
    game: Game | None = None
    hand_number: int = 0
    result_recorded: bool = False
    # telegram message ids for edits
    board_message_id: int | None = None
    hand_message_ids: dict[int, int] = field(default_factory=dict)  # user_id -> msg
    timer_token: int = 0  # bumped to cancel stale timers
    # (seat, tile) of most recent discard — for board / announce UI
    last_discard: tuple[int, Tile] | None = None

    def __post_init__(self) -> None:
        if not self.seats:
            self.seats = [
                Seat(i, None, f"Seat {WIND[i]}") for i in range(4)
            ]

    def human_count(self) -> int:
        return sum(1 for s in self.seats if s.user_id is not None and not s.is_bot)

    def bot_count(self) -> int:
        return sum(1 for s in self.seats if s.is_bot)

    def open_seat_index(self) -> int | None:
        for s in self.seats:
            if s.user_id is None and not s.is_bot:
                return s.seat_index
        return None

    def seat_of_user(self, user_id: int) -> Seat | None:
        for s in self.seats:
            if s.user_id == user_id:
                return s
        return None

    def name_for_seat(self, seat_index: int) -> str:
        s = self.seats[seat_index]
        wind = WIND[seat_index]
        return f"{s.display_name} ({wind})"

    def fill_bots(self, count: int, *, difficulty: str | None = None) -> str | None:
        """Reserve `count` bot seats (0–3). Call in lobby before/while humans join."""
        if self.status != TableStatus.SETUP:
            return "Table already started."
        if not 0 <= count <= 3:
            return "bots must be 0–3 (need at least one human)."
        diff = difficulty or self.bot_difficulty
        try:
            BotDifficulty(diff)
        except ValueError:
            return "difficulty must be easy, normal, or hard."
        self.bot_difficulty = diff
        # Clear existing bots first
        for s in self.seats:
            if s.is_bot:
                s.is_bot = False
                s.user_id = None
                s.display_name = f"Seat {WIND[s.seat_index]}"
                s.bot_difficulty = None
        self.reserved_bots = count
        name_i = 0
        for s in self.seats:
            if count <= 0:
                break
            if s.user_id is not None:
                continue
            s.is_bot = True
            s.user_id = None
            s.display_name = f"{BOT_NAMES[name_i % len(BOT_NAMES)]} [bot]"
            s.bot_difficulty = diff
            name_i += 1
            count -= 1
        if count > 0:
            return "Not enough empty seats for that many bots."
        return None

    def join(self, user_id: int, display_name: str) -> str | None:
        if self.status != TableStatus.SETUP:
            return "Table already started."
        if self.seat_of_user(user_id) is not None:
            return "You're already seated."
        idx = self.open_seat_index()
        if idx is None:
            return "Table is full."
        self.seats[idx].user_id = user_id
        self.seats[idx].display_name = display_name[:32]
        self.seats[idx].is_bot = False
        self.seats[idx].bot_difficulty = None
        if self.host_user_id is None:
            self.host_user_id = user_id
        return None

    def leave(self, user_id: int) -> str | None:
        if self.status != TableStatus.SETUP:
            return "Can't leave after the hand started. Finish or /endtable."
        seat = self.seat_of_user(user_id)
        if seat is None:
            return "You're not at this table."
        seat.user_id = None
        seat.display_name = f"Seat {WIND[seat.seat_index]}"
        if self.host_user_id == user_id:
            humans = [s for s in self.seats if s.user_id is not None]
            self.host_user_id = humans[0].user_id if humans else None
        return None

    def ready_to_deal(self) -> bool:
        if self.status != TableStatus.SETUP:
            return False
        if self.human_count() < 1:
            return False
        return all(s.occupied for s in self.seats)

    def deal_hand(self) -> None:
        self.game = Game.new_hand(dealer=0, round_wind=0)
        self.status = TableStatus.ACTIVE
        self.hand_number += 1
        self.timer_token += 1
        self.hand_message_ids.clear()
        self.result_recorded = False
        self.last_discard = None
        self.board_is_photo = False  # type: ignore[attr-defined]
        self.discard_message_id = None  # type: ignore[attr-defined]
        self._last_ping_key = None  # type: ignore[attr-defined]

    def to_db_seats(self) -> list[dict]:
        return [
            {
                "seat_index": s.seat_index,
                "telegram_user_id": s.user_id,
                "display_name": s.display_name,
                "is_bot": s.is_bot,
                "bot_difficulty": s.bot_difficulty,
            }
            for s in self.seats
        ]

    def rules_dict(self) -> dict:
        r = self.session_rules
        return {
            "turn_timeout_s": self.turn_timeout_s,
            "claim_timeout_s": self.claim_timeout_s,
            "hand_number": self.hand_number,
            "bot_difficulty": self.bot_difficulty,
            "reserved_bots": self.reserved_bots,
            "start_points": r.start_points,
            "return_points": r.return_points,
            "uma": list(r.uma),
            "length": r.length,
        }


class TableManager:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self.tables: dict[int, Table] = {}
        self._locks: dict[int, object] = {}
        db.init_db(db_path)
        # Live hands live only in memory — orphan DB rows from a previous process
        abandoned = db.abandon_all_active_tables(db_path)
        self.startup_abandoned = abandoned

    def lock_for(self, chat_id: int):
        """Per-table asyncio.Lock (lazy)."""
        import asyncio

        lock = self._locks.get(chat_id)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[chat_id] = lock
        return lock

    def get(self, chat_id: int) -> Table | None:
        return self.tables.get(chat_id)

    def create(
        self,
        chat_id: int,
        host_user_id: int,
        *,
        turn_timeout_s: int,
        claim_timeout_s: int,
        bots: int = 0,
        bot_difficulty: str = "normal",
        session_rules: SessionRules | None = None,
    ) -> Table | str:
        if chat_id in self.tables:
            return "A table already exists in this chat. /endsession or /endtable first."
        if not 0 <= bots <= 3:
            return "bots must be 0–3."
        t = Table(
            chat_id=chat_id,
            host_user_id=host_user_id,
            turn_timeout_s=turn_timeout_s,
            claim_timeout_s=claim_timeout_s,
            bot_difficulty=bot_difficulty,
            reserved_bots=bots,
            session_rules=session_rules or SessionRules(),
        )
        self.tables[chat_id] = t
        self.persist(t)
        return t

    def end(self, chat_id: int, *, abandon: bool = True) -> None:
        """Remove from memory. If abandon, delete active DB row when still setup/no hands."""
        table = self.tables.pop(chat_id, None)
        if table is None:
            db.delete_active_table(self.db_path, chat_id)
            return
        if abandon and table.db_table_id is not None:
            hands = db.hand_count(self.db_path, table.db_table_id)
            if table.status == TableStatus.SETUP or hands == 0:
                db.delete_active_table(self.db_path, chat_id)
            else:
                # abandon mid-session: store raw scores without uma
                scores = db.get_scores(self.db_path, table.db_table_id)
                db.complete_session(
                    self.db_path,
                    table.db_table_id,
                    final_payload={
                        "abandoned": True,
                        "scores": {str(k): v for k, v in scores.items()},
                        "names": {
                            str(s.seat_index): s.display_name for s in table.seats
                        },
                    },
                )

    def persist(self, table: Table) -> None:
        tid = db.upsert_table(
            self.db_path,
            chat_id=table.chat_id,
            status=table.status.value,
            rules=table.rules_dict(),
            seats=table.to_db_seats(),
        )
        table.db_table_id = tid
