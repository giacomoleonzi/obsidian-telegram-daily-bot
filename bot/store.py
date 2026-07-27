#!/usr/bin/env python3
"""SQLite-backed store for opt-in Gemini promotion entries."""

from __future__ import annotations

import secrets
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Final

STATUS_LOCAL: Final[str] = "local"
STATUS_PROCESSING: Final[str] = "processing"
STATUS_CLOUD: Final[str] = "cloud"
STATUS_FAILED: Final[str] = "failed"

_PROMOTABLE: Final[frozenset[str]] = frozenset({STATUS_LOCAL, STATUS_FAILED})

_SCHEMA: Final[str] = """
CREATE TABLE IF NOT EXISTS entries (
    id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    note_path TEXT NOT NULL,
    entry_anchor TEXT NOT NULL,
    transcript TEXT NOT NULL,
    chat_id INTEGER NOT NULL,
    telegram_message_id INTEGER,
    telegram_user_message_id INTEGER,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    processed_at TEXT,
    last_error TEXT,
    cloud_summary TEXT,
    cloud_tasks TEXT
);
CREATE INDEX IF NOT EXISTS idx_entries_status_created
    ON entries(status, created_at);
CREATE INDEX IF NOT EXISTS idx_entries_chat_status
    ON entries(chat_id, status);
"""


def new_entry_id() -> str:
    """Return a short opaque hex id for callback_data (``g:{id}``)."""
    return secrets.token_hex(3)


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(frozen=True)
class Entry:
    """One voice entry eligible for optional Gemini promotion."""

    id: str
    status: str
    note_path: str
    entry_anchor: str
    transcript: str
    chat_id: int
    telegram_message_id: int | None
    telegram_user_message_id: int | None
    created_at: str
    updated_at: str
    processed_at: str | None
    last_error: str | None
    cloud_summary: str | None
    cloud_tasks: str | None


def _row_to_entry(row: sqlite3.Row) -> Entry:
    return Entry(
        id=row["id"],
        status=row["status"],
        note_path=row["note_path"],
        entry_anchor=row["entry_anchor"],
        transcript=row["transcript"],
        chat_id=row["chat_id"],
        telegram_message_id=row["telegram_message_id"],
        telegram_user_message_id=row["telegram_user_message_id"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        processed_at=row["processed_at"],
        last_error=row["last_error"],
        cloud_summary=row["cloud_summary"],
        cloud_tasks=row["cloud_tasks"],
    )


class EntryStore:
    """Persistent map from opaque ids to note anchors and promotion state."""

    def __init__(self, db_path: Path) -> None:
        """Open (or create) the SQLite database and ensure schema exists.

        Args:
            db_path: Path to the SQLite file (parent dirs are created).
        """
        self._db_path = db_path
        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL;")
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    def close(self) -> None:
        """Close the database connection."""
        self._conn.close()

    def create_entry(
        self,
        note_path: str,
        transcript: str,
        chat_id: int,
        telegram_user_message_id: int | None,
        entry_id: str | None = None,
    ) -> Entry:
        """Insert a new local entry and return it.

        Args:
            note_path: Absolute or vault-relative path to the daily note.
            transcript: Local Whisper transcript.
            chat_id: Telegram chat id.
            telegram_user_message_id: Original voice message id.
            entry_id: Optional pre-generated id (must match markdown anchor).

        Returns:
            The created ``Entry`` with ``status=local``.
        """
        eid = entry_id or new_entry_id()
        now = _utc_now_iso()
        self._conn.execute(
            """
            INSERT INTO entries (
                id, status, note_path, entry_anchor, transcript, chat_id,
                telegram_message_id, telegram_user_message_id,
                created_at, updated_at, processed_at, last_error,
                cloud_summary, cloud_tasks
            ) VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?, ?, NULL, NULL, NULL, NULL)
            """,
            (eid, STATUS_LOCAL, note_path, eid, transcript, chat_id, telegram_user_message_id, now, now),
        )
        self._conn.commit()
        entry = self.get_entry(eid)
        if entry is None:
            raise RuntimeError(f"Failed to load newly created entry {eid}")
        return entry

    def get_entry(self, entry_id: str) -> Entry | None:
        """Load an entry by id, or None if missing."""
        cur = self._conn.execute("SELECT * FROM entries WHERE id = ?", (entry_id,))
        row = cur.fetchone()
        return _row_to_entry(row) if row else None

    def try_begin_processing(self, entry_id: str) -> Entry | None:
        """CAS: ``local|failed`` → ``processing``. Returns entry or None if not acquired."""
        now = _utc_now_iso()
        cur = self._conn.execute(
            """
            UPDATE entries
            SET status = ?, updated_at = ?, last_error = NULL
            WHERE id = ? AND status IN (?, ?)
            """,
            (STATUS_PROCESSING, now, entry_id, STATUS_LOCAL, STATUS_FAILED),
        )
        self._conn.commit()
        if cur.rowcount != 1:
            return None
        return self.get_entry(entry_id)

    def mark_cloud(
        self,
        entry_id: str,
        summary: str | None,
        tasks: str | None,
    ) -> None:
        """Mark entry as successfully promoted to cloud."""
        now = _utc_now_iso()
        self._conn.execute(
            """
            UPDATE entries
            SET status = ?, updated_at = ?, processed_at = ?,
                cloud_summary = ?, cloud_tasks = ?, last_error = NULL
            WHERE id = ?
            """,
            (STATUS_CLOUD, now, now, summary, tasks, entry_id),
        )
        self._conn.commit()

    def mark_failed(self, entry_id: str, error: str) -> None:
        """Mark entry as failed so it can be retried."""
        now = _utc_now_iso()
        self._conn.execute(
            """
            UPDATE entries
            SET status = ?, updated_at = ?, last_error = ?
            WHERE id = ?
            """,
            (STATUS_FAILED, now, error[:2000], entry_id),
        )
        self._conn.commit()

    def set_telegram_message_id(self, entry_id: str, message_id: int) -> None:
        """Store the bot reply message id used for later editMessageText."""
        now = _utc_now_iso()
        self._conn.execute(
            """
            UPDATE entries
            SET telegram_message_id = ?, updated_at = ?
            WHERE id = ?
            """,
            (message_id, now, entry_id),
        )
        self._conn.commit()

    def list_pending(self, chat_id: int, limit: int = 20) -> list[Entry]:
        """List promotable entries (local/failed) for a chat, oldest first."""
        cur = self._conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND status IN (?, ?)
            ORDER BY created_at ASC
            LIMIT ?
            """,
            (chat_id, STATUS_LOCAL, STATUS_FAILED, limit),
        )
        return [_row_to_entry(row) for row in cur.fetchall()]

    def latest_promotable(self, chat_id: int) -> Entry | None:
        """Return the most recent local/failed entry for ``/g``, or None."""
        cur = self._conn.execute(
            """
            SELECT * FROM entries
            WHERE chat_id = ? AND status IN (?, ?)
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chat_id, STATUS_LOCAL, STATUS_FAILED),
        )
        row = cur.fetchone()
        return _row_to_entry(row) if row else None
