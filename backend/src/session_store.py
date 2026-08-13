from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel


class ApiModel(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class SessionSnapshot(ApiModel):
    question_text: str = ""
    source_kind: str = ""
    lesson_json: str = ""
    status: str = ""
    error_message: str = ""
    revision: int = 0
    last_student_message: str = ""
    generation: int = 0


class ChatMessage(ApiModel):
    id: str
    role: str
    text: str
    lesson_json: str = ""
    source_kind: str = ""
    generation: int = 0
    status: str = ""


class SessionView(ApiModel):
    snapshot: SessionSnapshot
    messages: list[ChatMessage] = Field(default_factory=list)


class BeginResult(ApiModel):
    generation: int
    allowed: bool
    message: str = ""


class SQLiteSessionStore:
    """Small, browser-scoped persistence layer for the local FastAPI app."""

    def __init__(
        self,
        path: str | Path,
        *,
        daily_lesson_limit: int = 40,
        daily_check_limit: int = 80,
        burst_limit: int = 8,
        burst_window_seconds: int = 60,
    ) -> None:
        self.path = str(path)
        self.daily_lesson_limit = daily_lesson_limit
        self.daily_check_limit = daily_check_limit
        self.burst_limit = burst_limit
        self.burst_window_seconds = burst_window_seconds
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path, timeout=15)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 15000")
        return connection

    def _initialize(self) -> None:
        with self._connect() as connection:
            connection.executescript(
                """
                PRAGMA journal_mode = WAL;
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    question_text TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT '',
                    lesson_json TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT '',
                    error_message TEXT NOT NULL DEFAULT '',
                    revision INTEGER NOT NULL DEFAULT 0,
                    last_student_message TEXT NOT NULL DEFAULT '',
                    generation INTEGER NOT NULL DEFAULT 0,
                    updated_at REAL NOT NULL
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    session_id TEXT NOT NULL REFERENCES sessions(id) ON DELETE CASCADE,
                    role TEXT NOT NULL,
                    text TEXT NOT NULL,
                    lesson_json TEXT NOT NULL DEFAULT '',
                    source_kind TEXT NOT NULL DEFAULT '',
                    generation INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT '',
                    created_at REAL NOT NULL
                );
                CREATE INDEX IF NOT EXISTS messages_session_order
                    ON messages(session_id, id);
                CREATE TABLE IF NOT EXISTS usage (
                    session_id TEXT PRIMARY KEY REFERENCES sessions(id) ON DELETE CASCADE,
                    day_key TEXT NOT NULL,
                    lessons_today INTEGER NOT NULL DEFAULT 0,
                    checks_today INTEGER NOT NULL DEFAULT 0,
                    window_started REAL NOT NULL,
                    recent_calls INTEGER NOT NULL DEFAULT 0
                );
                """
            )

    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).date().isoformat()

    @staticmethod
    def _ensure(connection: sqlite3.Connection, session_id: str) -> None:
        connection.execute(
            "INSERT OR IGNORE INTO sessions(id, updated_at) VALUES (?, ?)",
            (session_id, time.time()),
        )

    @staticmethod
    def _snapshot(row: sqlite3.Row) -> SessionSnapshot:
        return SessionSnapshot(
            question_text=row["question_text"],
            source_kind=row["source_kind"],
            lesson_json=row["lesson_json"],
            status=row["status"],
            error_message=row["error_message"],
            revision=row["revision"],
            last_student_message=row["last_student_message"],
            generation=row["generation"],
        )

    def ensure(self, session_id: str) -> None:
        with self._connect() as connection:
            self._ensure(connection, session_id)

    def snapshot(self, session_id: str) -> SessionSnapshot:
        with self._connect() as connection:
            self._ensure(connection, session_id)
            row = connection.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
        assert row is not None
        return self._snapshot(row)

    def messages(self, session_id: str, limit: int = 80) -> list[ChatMessage]:
        with self._connect() as connection:
            self._ensure(connection, session_id)
            rows = connection.execute(
                """
                SELECT id, role, text, lesson_json, source_kind, generation, status
                FROM (
                    SELECT id, role, text, lesson_json, source_kind, generation, status
                    FROM messages WHERE session_id = ? ORDER BY id DESC LIMIT ?
                ) ORDER BY id
                """,
                (session_id, min(100, max(1, limit))),
            ).fetchall()
        return [
            ChatMessage(
                id=str(row["id"]),
                role=row["role"],
                text=row["text"],
                lesson_json=row["lesson_json"],
                source_kind=row["source_kind"],
                generation=row["generation"],
                status=row["status"],
            )
            for row in rows
        ]

    def view(self, session_id: str) -> SessionView:
        return SessionView(
            snapshot=self.snapshot(session_id),
            messages=self.messages(session_id),
        )

    def _consume(self, connection: sqlite3.Connection, session_id: str, kind: str) -> str:
        now = time.time()
        today = self._today()
        row = connection.execute(
            "SELECT * FROM usage WHERE session_id = ?", (session_id,)
        ).fetchone()
        if row is None:
            lessons = checks = recent = 0
            window_started = now
        else:
            lessons = int(row["lessons_today"])
            checks = int(row["checks_today"])
            recent = int(row["recent_calls"])
            window_started = float(row["window_started"])
            if row["day_key"] != today:
                lessons = checks = 0
            if now - window_started >= self.burst_window_seconds:
                recent = 0
                window_started = now

        if recent >= self.burst_limit:
            return "That is a lot of requests at once. Give me a minute to catch up."
        if kind == "check" and checks >= self.daily_check_limit:
            return "You have used today's work checks. This resets in a day."
        if kind == "lesson" and lessons >= self.daily_lesson_limit:
            return "You have used today's lessons. This resets in a day."

        lessons += int(kind == "lesson")
        checks += int(kind == "check")
        recent += 1
        connection.execute(
            """
            INSERT INTO usage(session_id, day_key, lessons_today, checks_today,
                              window_started, recent_calls)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(session_id) DO UPDATE SET
                day_key = excluded.day_key,
                lessons_today = excluded.lessons_today,
                checks_today = excluded.checks_today,
                window_started = excluded.window_started,
                recent_calls = excluded.recent_calls
            """,
            (session_id, today, lessons, checks, window_started, recent),
        )
        return ""

    def _begin(
        self,
        session_id: str,
        *,
        kind: str,
        user_text: str,
        source_kind: str,
        question_text: str | None = None,
        clear_lesson: bool = False,
        last_student_message: str = "",
    ) -> BeginResult:
        now = time.time()
        with self._connect() as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._ensure(connection, session_id)
            refusal = self._consume(connection, session_id, kind)
            row = connection.execute(
                "SELECT generation FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            assert row is not None
            generation = int(row["generation"]) + 1
            if refusal:
                connection.execute(
                    """
                    UPDATE sessions SET generation = ?, status = 'error',
                        error_message = ?, updated_at = ? WHERE id = ?
                    """,
                    (generation, refusal, now, session_id),
                )
                return BeginResult(generation=generation, allowed=False, message=refusal)

            fields = [
                "generation = ?",
                "status = 'thinking'",
                "error_message = ''",
                "last_student_message = ?",
                "source_kind = ?",
                "updated_at = ?",
            ]
            values: list[object] = [generation, last_student_message, source_kind, now]
            if question_text is not None:
                fields.append("question_text = ?")
                values.append(question_text)
            if clear_lesson:
                fields.append("lesson_json = ''")
            values.append(session_id)
            connection.execute(
                f"UPDATE sessions SET {', '.join(fields)} WHERE id = ?",
                values,
            )
            connection.execute(
                """
                INSERT INTO messages(session_id, role, text, lesson_json, source_kind,
                                     generation, status, created_at)
                VALUES (?, 'user', ?, '', ?, ?, 'ready', ?)
                """,
                (session_id, user_text, source_kind, generation, now),
            )
        return BeginResult(generation=generation, allowed=True)

    def begin_lesson(
        self,
        session_id: str,
        *,
        question_text: str,
        source_kind: str,
    ) -> BeginResult:
        message = question_text
        if source_kind == "image":
            message = (
                f"{question_text}\n\nUploaded an SAT question image."
                if question_text
                else "Uploaded an SAT question image."
            )
        return self._begin(
            session_id,
            kind="lesson",
            user_text=message,
            source_kind=source_kind,
            question_text=question_text,
            clear_lesson=True,
        )

    def begin_replan(self, session_id: str, *, student_message: str) -> BeginResult:
        return self._begin(
            session_id,
            kind="lesson",
            user_text=student_message,
            source_kind="text",
            last_student_message=student_message,
        )

    def begin_check(self, session_id: str, *, student_work: str) -> BeginResult:
        return self._begin(
            session_id,
            kind="check",
            user_text=f"Here's my working:\n\n{student_work}",
            source_kind="work",
            last_student_message=student_work[:400],
        )

    def set_topic_question(self, session_id: str, generation: int, question: str) -> None:
        with self._connect() as connection:
            connection.execute(
                """
                UPDATE sessions SET question_text = ?, updated_at = ?
                WHERE id = ? AND generation = ?
                """,
                (question, time.time(), session_id, generation),
            )

    def complete(
        self,
        session_id: str,
        generation: int,
        *,
        lesson_json: str,
        assistant_text: str,
        question_text: str | None = None,
    ) -> bool:
        now = time.time()
        with self._connect() as connection:
            fields = [
                "lesson_json = ?",
                "status = 'ready'",
                "error_message = ''",
                "revision = revision + 1",
                "updated_at = ?",
            ]
            values: list[object] = [lesson_json, now]
            if question_text is not None:
                fields.append("question_text = ?")
                values.append(question_text)
            values.extend([session_id, generation])
            cursor = connection.execute(
                f"UPDATE sessions SET {', '.join(fields)} WHERE id = ? AND generation = ?",
                values,
            )
            if cursor.rowcount != 1:
                return False
            source = connection.execute(
                "SELECT source_kind FROM sessions WHERE id = ?", (session_id,)
            ).fetchone()
            connection.execute(
                """
                INSERT INTO messages(session_id, role, text, lesson_json, source_kind,
                                     generation, status, created_at)
                VALUES (?, 'assistant', ?, ?, ?, ?, 'ready', ?)
                """,
                (session_id, assistant_text, lesson_json, source["source_kind"], generation, now),
            )
        return True

    def fail(self, session_id: str, generation: int, message: str) -> bool:
        now = time.time()
        with self._connect() as connection:
            cursor = connection.execute(
                """
                UPDATE sessions SET status = 'error', error_message = ?, updated_at = ?
                WHERE id = ? AND generation = ?
                """,
                (message, now, session_id, generation),
            )
            if cursor.rowcount != 1:
                return False
            connection.execute(
                """
                INSERT INTO messages(session_id, role, text, lesson_json, source_kind,
                                     generation, status, created_at)
                VALUES (?, 'assistant', ?, '', 'text', ?, 'error', ?)
                """,
                (session_id, message, generation, now),
            )
        return True

    def reset(self, session_id: str) -> SessionView:
        with self._connect() as connection:
            self._ensure(connection, session_id)
            connection.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            connection.execute(
                """
                UPDATE sessions SET question_text = '', source_kind = '', lesson_json = '',
                    status = '', error_message = '', revision = revision + 1,
                    last_student_message = '', generation = generation + 1, updated_at = ?
                WHERE id = ?
                """,
                (time.time(), session_id),
            )
        return self.view(session_id)

    def forget(self, session_id: str) -> int:
        with self._connect() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS count FROM messages WHERE session_id = ?", (session_id,)
            ).fetchone()
            erased = int(row["count"]) if row else 0
            connection.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._ensure(connection, session_id)
        return erased
