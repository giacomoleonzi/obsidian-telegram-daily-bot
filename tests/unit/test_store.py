#!/usr/bin/env python3
"""Unit tests for persistent entry store (SQLite)."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.store import EntryStore


@pytest.fixture
def store(tmp_path: Path) -> EntryStore:
    db = tmp_path / "state.sqlite3"
    s = EntryStore(db)
    yield s
    s.close()


def test_create_and_get_entry(store: EntryStore) -> None:
    entry = store.create_entry(
        note_path="/vault/Daily/2026-07-27.md",
        transcript="ciao mondo",
        chat_id=42,
        telegram_user_message_id=100,
    )
    assert entry.id
    assert len(entry.id) >= 4
    assert entry.status == "local"
    assert entry.transcript == "ciao mondo"
    loaded = store.get_entry(entry.id)
    assert loaded is not None
    assert loaded.id == entry.id
    assert loaded.note_path == "/vault/Daily/2026-07-27.md"


def test_cas_begin_processing_succeeds_once(store: EntryStore) -> None:
    entry = store.create_entry(
        note_path="/vault/Daily/a.md",
        transcript="t",
        chat_id=1,
        telegram_user_message_id=2,
    )
    first = store.try_begin_processing(entry.id)
    assert first is not None
    assert first.status == "processing"
    second = store.try_begin_processing(entry.id)
    assert second is None
    assert store.get_entry(entry.id).status == "processing"


def test_cas_allows_retry_from_failed(store: EntryStore) -> None:
    entry = store.create_entry(
        note_path="/vault/Daily/a.md",
        transcript="t",
        chat_id=1,
        telegram_user_message_id=2,
    )
    assert store.try_begin_processing(entry.id) is not None
    store.mark_failed(entry.id, "timeout")
    assert store.get_entry(entry.id).status == "failed"
    assert store.get_entry(entry.id).last_error == "timeout"
    again = store.try_begin_processing(entry.id)
    assert again is not None
    assert again.status == "processing"


def test_mark_cloud_is_terminal(store: EntryStore) -> None:
    entry = store.create_entry(
        note_path="/vault/Daily/a.md",
        transcript="t",
        chat_id=1,
        telegram_user_message_id=2,
    )
    store.try_begin_processing(entry.id)
    store.mark_cloud(entry.id, summary="- ok", tasks="- [ ] fare x")
    cloud = store.get_entry(entry.id)
    assert cloud is not None
    assert cloud.status == "cloud"
    assert cloud.cloud_summary == "- ok"
    assert cloud.cloud_tasks == "- [ ] fare x"
    assert cloud.processed_at is not None
    assert store.try_begin_processing(entry.id) is None


def test_list_pending_and_latest_promotable(store: EntryStore) -> None:
    a = store.create_entry("/vault/a.md", "one", chat_id=7, telegram_user_message_id=1)
    b = store.create_entry("/vault/b.md", "two", chat_id=7, telegram_user_message_id=2)
    store.create_entry("/vault/c.md", "other chat", chat_id=99, telegram_user_message_id=3)
    store.try_begin_processing(a.id)
    store.mark_cloud(a.id, summary=None, tasks=None)

    pending = store.list_pending(chat_id=7)
    assert [e.id for e in pending] == [b.id]

    latest = store.latest_promotable(chat_id=7)
    assert latest is not None
    assert latest.id == b.id


def test_set_telegram_message_id(store: EntryStore) -> None:
    entry = store.create_entry("/vault/a.md", "t", chat_id=1, telegram_user_message_id=9)
    store.set_telegram_message_id(entry.id, 555)
    assert store.get_entry(entry.id).telegram_message_id == 555
