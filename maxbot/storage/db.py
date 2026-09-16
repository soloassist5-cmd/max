from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, time
from typing import Any, Sequence

import aiosqlite

from ..domain.bells import Bell
from ..domain.events import Event
from ..domain.grades import Grade
from ..domain.homework import Homework
from ..domain.schedule import Lesson

SCHEMA = """
CREATE TABLE IF NOT EXISTS chats (
    chat_id INTEGER PRIMARY KEY,
    title TEXT,
    chat_type TEXT,
    tz_offset INTEGER NOT NULL DEFAULT 3,
    digest_enabled INTEGER NOT NULL DEFAULT 1,
    morning_digest_at TEXT,
    evening_digest_at TEXT,
    last_morning_digest TEXT,
    last_evening_digest TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS lessons (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    weekday INTEGER NOT NULL,
    slot INTEGER NOT NULL,
    subject TEXT NOT NULL,
    room TEXT,
    teacher TEXT,
    UNIQUE(chat_id, weekday, slot)
);

CREATE TABLE IF NOT EXISTS bells (
    chat_id INTEGER NOT NULL,
    number INTEGER NOT NULL,
    start_minutes INTEGER NOT NULL,
    end_minutes INTEGER NOT NULL,
    PRIMARY KEY (chat_id, number)
);

CREATE TABLE IF NOT EXISTS homework (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    due_date TEXT NOT NULL,
    text TEXT NOT NULL,
    created_by INTEGER NOT NULL,
    created_by_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS homework_done (
    homework_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    PRIMARY KEY (homework_id, user_id)
);

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    kind TEXT NOT NULL DEFAULT '',
    event_date TEXT NOT NULL,
    event_time TEXT,
    created_by INTEGER NOT NULL,
    created_by_name TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL,
    notified INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS grades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    subject TEXT NOT NULL,
    value INTEGER NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS pending_actions (
    chat_id INTEGER NOT NULL,
    user_id INTEGER NOT NULL,
    action TEXT NOT NULL,
    data TEXT NOT NULL DEFAULT '{}',
    updated_at TEXT NOT NULL,
    PRIMARY KEY (chat_id, user_id)
);

CREATE TABLE IF NOT EXISTS poll_state (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    marker INTEGER
);

CREATE INDEX IF NOT EXISTS idx_homework_chat_date ON homework(chat_id, due_date);
CREATE INDEX IF NOT EXISTS idx_events_chat_date ON events(chat_id, event_date);
CREATE INDEX IF NOT EXISTS idx_grades_chat_user ON grades(chat_id, user_id);
"""


@dataclass(frozen=True, slots=True)
class ChatSettings:
    chat_id: int
    title: str | None
    chat_type: str | None
    tz_offset: int
    digest_enabled: bool
    morning_digest_at: str | None
    evening_digest_at: str | None
    last_morning_digest: str | None
    last_evening_digest: str | None


def _utcnow() -> str:
    return datetime.utcnow().isoformat(timespec="seconds")


def _row_to_lesson(row: aiosqlite.Row) -> Lesson:
    return Lesson(
        id=row["id"], weekday=row["weekday"], slot=row["slot"],
        subject=row["subject"], room=row["room"], teacher=row["teacher"],
    )


def _row_to_homework(row: aiosqlite.Row) -> Homework:
    return Homework(
        id=row["id"],
        subject=row["subject"],
        due_date=date.fromisoformat(row["due_date"]),
        text=row["text"],
        created_by=row["created_by"],
        created_at=datetime.fromisoformat(row["created_at"]),
        done=bool(row["done"]),
    )


def _row_to_event(row: aiosqlite.Row) -> Event:
    event_time = row["event_time"]
    return Event(
        id=row["id"],
        title=row["title"],
        kind=row["kind"] or "",
        event_date=date.fromisoformat(row["event_date"]),
        event_time=time.fromisoformat(event_time) if event_time else None,
        created_by=row["created_by"],
    )


def _row_to_grade(row: aiosqlite.Row) -> Grade:
    return Grade(
        id=row["id"], subject=row["subject"], value=row["value"],
        note=row["note"] or "", created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_settings(row: aiosqlite.Row) -> ChatSettings:
    return ChatSettings(
        chat_id=row["chat_id"],
        title=row["title"],
        chat_type=row["chat_type"],
        tz_offset=row["tz_offset"],
        digest_enabled=bool(row["digest_enabled"]),
        morning_digest_at=row["morning_digest_at"],
        evening_digest_at=row["evening_digest_at"],
        last_morning_digest=row["last_morning_digest"],
        last_evening_digest=row["last_evening_digest"],
    )


class Storage:
    def __init__(self, path: str, *, default_tz_offset: int = 3) -> None:
        self._path = path
        self._default_tz_offset = default_tz_offset
        self._conn: aiosqlite.Connection | None = None

    async def connect(self) -> None:
        self._conn = await aiosqlite.connect(self._path)
        self._conn.row_factory = aiosqlite.Row
        await self._conn.execute("PRAGMA journal_mode=WAL")
        await self._conn.execute("PRAGMA foreign_keys=ON")
        await self._conn.executescript(SCHEMA)
        await self._conn.commit()

    async def close(self) -> None:
        if self._conn is not None:
            await self._conn.close()
            self._conn = None

    async def __aenter__(self) -> "Storage":
        await self.connect()
        return self

    async def __aexit__(self, *exc_info: object) -> None:
        await self.close()

    @property
    def conn(self) -> aiosqlite.Connection:
        if self._conn is None:
            raise RuntimeError("Storage не подключён, вызовите connect()")
        return self._conn

    # -- чаты --------------------------------------------------------

    async def touch_chat(self, chat_id: int, *, title: str | None = None, chat_type: str | None = None) -> None:
        await self.conn.execute(
            """
            INSERT INTO chats(chat_id, title, chat_type, tz_offset, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id) DO UPDATE SET
                title = COALESCE(excluded.title, chats.title),
                chat_type = COALESCE(excluded.chat_type, chats.chat_type)
            """,
            (chat_id, title, chat_type, self._default_tz_offset, _utcnow()),
        )
        await self.conn.commit()

    async def get_chat_settings(self, chat_id: int) -> ChatSettings:
        await self.touch_chat(chat_id)
        cursor = await self.conn.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        row = await cursor.fetchone()
        assert row is not None
        return _row_to_settings(row)

    async def update_chat_settings(self, chat_id: int, **fields: Any) -> None:
        if not fields:
            return
        await self.touch_chat(chat_id)  # гарантирует, что строка уже существует
        columns = ", ".join(f"{key} = ?" for key in fields)
        await self.conn.execute(
            f"UPDATE chats SET {columns} WHERE chat_id = ?", (*fields.values(), chat_id)
        )
        await self.conn.commit()

    async def list_chats(self) -> list[ChatSettings]:
        cursor = await self.conn.execute("SELECT * FROM chats")
        return [_row_to_settings(row) for row in await cursor.fetchall()]

    async def mark_digest_sent(self, chat_id: int, *, kind: str, iso_date: str) -> None:
        column = "last_morning_digest" if kind == "morning" else "last_evening_digest"
        await self.conn.execute(f"UPDATE chats SET {column} = ? WHERE chat_id = ?", (iso_date, chat_id))
        await self.conn.commit()

    # -- расписание уроков --------------------------------------------

    async def upsert_lesson(
        self, chat_id: int, weekday: int, slot: int, subject: str,
        room: str | None = None, teacher: str | None = None,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO lessons(chat_id, weekday, slot, subject, room, teacher)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, weekday, slot) DO UPDATE SET
                subject = excluded.subject, room = excluded.room, teacher = excluded.teacher
            """,
            (chat_id, weekday, slot, subject, room, teacher),
        )
        await self.conn.commit()
        if cursor.lastrowid:
            return cursor.lastrowid
        row = await (await self.conn.execute(
            "SELECT id FROM lessons WHERE chat_id=? AND weekday=? AND slot=?", (chat_id, weekday, slot)
        )).fetchone()
        return row["id"]

    async def remove_lesson(self, chat_id: int, lesson_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM lessons WHERE chat_id = ? AND id = ?", (chat_id, lesson_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    async def list_lessons(self, chat_id: int) -> list[Lesson]:
        cursor = await self.conn.execute(
            "SELECT * FROM lessons WHERE chat_id = ? ORDER BY weekday, slot", (chat_id,)
        )
        return [_row_to_lesson(row) for row in await cursor.fetchall()]

    async def get_lesson(self, chat_id: int, lesson_id: int) -> Lesson | None:
        cursor = await self.conn.execute(
            "SELECT * FROM lessons WHERE chat_id = ? AND id = ?", (chat_id, lesson_id)
        )
        row = await cursor.fetchone()
        return _row_to_lesson(row) if row else None

    # -- звонки ----------------------------------------------------------

    async def set_bells(self, chat_id: int, bells: Sequence[Bell]) -> None:
        await self.conn.execute("DELETE FROM bells WHERE chat_id = ?", (chat_id,))
        await self.conn.executemany(
            "INSERT INTO bells(chat_id, number, start_minutes, end_minutes) VALUES (?, ?, ?, ?)",
            [
                (chat_id, bell.number, bell.start.hour * 60 + bell.start.minute, bell.end.hour * 60 + bell.end.minute)
                for bell in bells
            ],
        )
        await self.conn.commit()

    async def get_bells(self, chat_id: int) -> list[Bell]:
        cursor = await self.conn.execute(
            "SELECT number, start_minutes, end_minutes FROM bells WHERE chat_id = ? ORDER BY number", (chat_id,)
        )
        rows = await cursor.fetchall()
        return [
            Bell(row["number"], time(row["start_minutes"] // 60, row["start_minutes"] % 60),
                 time(row["end_minutes"] // 60, row["end_minutes"] % 60))
            for row in rows
        ]

    # -- домашние задания --------------------------------------------

    async def add_homework(
        self, chat_id: int, subject: str, due_date: date, text: str,
        created_by: int, created_by_name: str,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO homework(chat_id, subject, due_date, text, created_by, created_by_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (chat_id, subject, due_date.isoformat(), text, created_by, created_by_name, _utcnow()),
        )
        await self.conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def list_homework(
        self, chat_id: int, user_id: int, *, from_date: date | None = None, only_pending: bool = False,
    ) -> list[Homework]:
        query = [
            "SELECT h.*, CASE WHEN hd.user_id IS NULL THEN 0 ELSE 1 END AS done",
            "FROM homework h LEFT JOIN homework_done hd ON hd.homework_id = h.id AND hd.user_id = ?",
            "WHERE h.chat_id = ?",
        ]
        params: list[Any] = [user_id, chat_id]
        if from_date is not None:
            query.append("AND h.due_date >= ?")
            params.append(from_date.isoformat())
        if only_pending:
            query.append("AND hd.user_id IS NULL")
        query.append("ORDER BY h.due_date, h.subject")
        cursor = await self.conn.execute(" ".join(query), params)
        return [_row_to_homework(row) for row in await cursor.fetchall()]

    async def get_homework(self, chat_id: int, homework_id: int, user_id: int) -> Homework | None:
        cursor = await self.conn.execute(
            """
            SELECT h.*, CASE WHEN hd.user_id IS NULL THEN 0 ELSE 1 END AS done
            FROM homework h LEFT JOIN homework_done hd ON hd.homework_id = h.id AND hd.user_id = ?
            WHERE h.chat_id = ? AND h.id = ?
            """,
            (user_id, chat_id, homework_id),
        )
        row = await cursor.fetchone()
        return _row_to_homework(row) if row else None

    async def toggle_homework_done(self, homework_id: int, user_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM homework_done WHERE homework_id = ? AND user_id = ?", (homework_id, user_id)
        )
        if cursor.rowcount:
            await self.conn.commit()
            return False
        await self.conn.execute(
            "INSERT INTO homework_done(homework_id, user_id) VALUES (?, ?)", (homework_id, user_id)
        )
        await self.conn.commit()
        return True

    async def list_homework_by_date(self, chat_id: int, target_date: date) -> list[Homework]:
        """Все задания на дату, без отметок о выполнении — для рассылки дайджеста."""
        cursor = await self.conn.execute(
            "SELECT *, 0 AS done FROM homework WHERE chat_id = ? AND due_date = ? ORDER BY subject",
            (chat_id, target_date.isoformat()),
        )
        return [_row_to_homework(row) for row in await cursor.fetchall()]

    async def delete_homework(self, chat_id: int, homework_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM homework WHERE chat_id = ? AND id = ?", (chat_id, homework_id)
        )
        await self.conn.execute("DELETE FROM homework_done WHERE homework_id = ?", (homework_id,))
        await self.conn.commit()
        return cursor.rowcount > 0

    # -- события / дедлайны --------------------------------------------

    async def add_event(
        self, chat_id: int, title: str, kind: str, event_date: date, event_time: time | None,
        created_by: int, created_by_name: str,
    ) -> int:
        cursor = await self.conn.execute(
            """
            INSERT INTO events(chat_id, title, kind, event_date, event_time, created_by, created_by_name, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                chat_id, title, kind, event_date.isoformat(),
                event_time.isoformat(timespec="minutes") if event_time else None,
                created_by, created_by_name, _utcnow(),
            ),
        )
        await self.conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def list_events(self, chat_id: int, *, from_date: date | None = None) -> list[Event]:
        query = "SELECT * FROM events WHERE chat_id = ?"
        params: list[Any] = [chat_id]
        if from_date is not None:
            query += " AND event_date >= ?"
            params.append(from_date.isoformat())
        query += " ORDER BY event_date, event_time"
        cursor = await self.conn.execute(query, params)
        return [_row_to_event(row) for row in await cursor.fetchall()]

    async def delete_event(self, chat_id: int, event_id: int) -> bool:
        cursor = await self.conn.execute("DELETE FROM events WHERE chat_id = ? AND id = ?", (chat_id, event_id))
        await self.conn.commit()
        return cursor.rowcount > 0

    async def events_to_remind(self, chat_id: int, today_date: date, tomorrow_date: date) -> list[Event]:
        cursor = await self.conn.execute(
            "SELECT * FROM events WHERE chat_id = ? AND notified = 0 AND event_date IN (?, ?)",
            (chat_id, today_date.isoformat(), tomorrow_date.isoformat()),
        )
        return [_row_to_event(row) for row in await cursor.fetchall()]

    async def mark_event_notified(self, event_id: int) -> None:
        await self.conn.execute("UPDATE events SET notified = 1 WHERE id = ?", (event_id,))
        await self.conn.commit()

    # -- оценки ------------------------------------------------------

    async def add_grade(self, chat_id: int, user_id: int, subject: str, value: int, note: str = "") -> int:
        cursor = await self.conn.execute(
            "INSERT INTO grades(chat_id, user_id, subject, value, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (chat_id, user_id, subject, value, note, _utcnow()),
        )
        await self.conn.commit()
        assert cursor.lastrowid is not None
        return cursor.lastrowid

    async def list_grades(self, chat_id: int, user_id: int) -> list[Grade]:
        cursor = await self.conn.execute(
            "SELECT * FROM grades WHERE chat_id = ? AND user_id = ? ORDER BY created_at", (chat_id, user_id)
        )
        return [_row_to_grade(row) for row in await cursor.fetchall()]

    async def delete_grade(self, chat_id: int, user_id: int, grade_id: int) -> bool:
        cursor = await self.conn.execute(
            "DELETE FROM grades WHERE chat_id = ? AND user_id = ? AND id = ?", (chat_id, user_id, grade_id)
        )
        await self.conn.commit()
        return cursor.rowcount > 0

    # -- состояние диалога (мини-FSM) ------------------------------------

    async def set_pending(self, chat_id: int, user_id: int, action: str, data: dict[str, Any] | None = None) -> None:
        await self.conn.execute(
            """
            INSERT INTO pending_actions(chat_id, user_id, action, data, updated_at) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, user_id) DO UPDATE SET
                action = excluded.action, data = excluded.data, updated_at = excluded.updated_at
            """,
            (chat_id, user_id, action, json.dumps(data or {}, ensure_ascii=False), _utcnow()),
        )
        await self.conn.commit()

    async def get_pending(self, chat_id: int, user_id: int) -> tuple[str, dict[str, Any]] | None:
        cursor = await self.conn.execute(
            "SELECT action, data FROM pending_actions WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return row["action"], json.loads(row["data"])

    async def clear_pending(self, chat_id: int, user_id: int) -> None:
        await self.conn.execute(
            "DELETE FROM pending_actions WHERE chat_id = ? AND user_id = ?", (chat_id, user_id)
        )
        await self.conn.commit()

    # -- курсор long polling --------------------------------------------

    async def get_marker(self) -> int | None:
        cursor = await self.conn.execute("SELECT marker FROM poll_state WHERE id = 1")
        row = await cursor.fetchone()
        return row["marker"] if row else None

    async def set_marker(self, marker: int | None) -> None:
        await self.conn.execute(
            "INSERT INTO poll_state(id, marker) VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET marker = excluded.marker",
            (marker,),
        )
        await self.conn.commit()
