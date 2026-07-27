#!/usr/bin/env python3
"""Daily-note path helpers and Markdown entry builders."""

from __future__ import annotations

import asyncio
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo


def safe_stem(value: str) -> str:
    """Sanitize a string for use in filenames.

    Args:
        value: Raw identifier or filename stem.

    Returns:
        Safe stem limited to 80 characters.
    """
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "")
    cleaned = cleaned.strip("_")
    return cleaned[:80] if cleaned else "file"


def message_dt_local(message_dt: datetime | None, timezone_name: str) -> datetime:
    """Convert a Telegram message datetime to the configured timezone.

    Args:
        message_dt: Message UTC/aware datetime, or None.
        timezone_name: IANA timezone name.

    Returns:
        Aware datetime in the target timezone.
    """
    tz = ZoneInfo(timezone_name)
    if message_dt is not None:
        return message_dt.astimezone(tz)
    return datetime.now(tz)


def timestamp_id(message_dt: datetime) -> str:
    """Build a sortable timestamp id for media filenames.

    Args:
        message_dt: Local message datetime.

    Returns:
        ``YYYYMMDD_HHMMSS`` string.
    """
    return message_dt.strftime("%Y%m%d_%H%M%S")


def daily_note_path(daily_dir: Path, message_dt: datetime, pattern: str) -> Path:
    """Resolve the daily note path for a message date.

    Args:
        daily_dir: Daily notes directory.
        message_dt: Local message datetime.
        pattern: ``strftime`` pattern for the note name.

    Returns:
        Path ending in ``.md``.
    """
    name = message_dt.strftime(pattern).strip()
    path = daily_dir / name
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    return path


def voice_entry_markdown(
    message_dt: datetime,
    audio_embed: str,
    transcript: str,
    summary: str | None = None,
    tasks: str | None = None,
) -> str:
    """Build a voice entry for the daily note.

    Args:
        message_dt: Local message datetime.
        audio_embed: Obsidian embed line for the audio file.
        transcript: Whisper transcript.
        summary: Optional summary body (no heading).
        tasks: Optional task checkbox body (no heading).

    Returns:
        Markdown block for appending.
    """
    ts = message_dt.strftime("%H:%M:%S %Z")
    safe_transcript = transcript or "Nessuna trascrizione disponibile."
    parts = [
        f"### Audio {ts}\n",
        f"{audio_embed}\n",
        "#### Trascrizione\n",
        f"{safe_transcript}\n",
    ]
    if summary:
        parts.extend(["#### Riassunto\n", f"{summary.strip()}\n"])
    if tasks:
        parts.extend(["#### Task\n", f"{tasks.strip()}\n"])
    return "\n".join(parts)


def image_entry_markdown(message_dt: datetime, image_embed: str, caption: str) -> str:
    """Build an image entry for the daily note."""
    ts = message_dt.strftime("%H:%M:%S %Z")
    caption_block = f"\n\n#### Caption\n\n{caption}\n" if caption else "\n"
    return f"### Immagine {ts}\n\n{image_embed}{caption_block}"


def text_entry_markdown(message_dt: datetime, text: str) -> str:
    """Build a plain-text entry for the daily note."""
    ts = message_dt.strftime("%H:%M:%S %Z")
    body = text.strip() or "(empty text message)"
    return f"### Text {ts}\n\n{body}\n"


def document_entry_markdown(message_dt: datetime, file_embed: str, caption: str) -> str:
    """Build a document entry for the daily note."""
    ts = message_dt.strftime("%H:%M:%S %Z")
    caption_block = f"\n\n#### Caption\n\n{caption}\n" if caption else "\n"
    return f"### File {ts}\n\n{file_embed}{caption_block}"


def append_to_daily_note_sync(note_path: Path, entry: str, note_date: datetime) -> None:
    """Append an entry to the daily note synchronously.

    Args:
        note_path: Target daily note path.
        entry: Markdown entry body.
        note_date: Local datetime used for header/separator.
    """
    note_path.parent.mkdir(parents=True, exist_ok=True)
    header = f"# Daily {note_date.strftime('%Y-%m-%d')}\n\n" if not note_path.exists() else ""
    separator_ts = note_date.strftime("%Y-%m-%d %H:%M:%S %Z")
    block = f"{header}---\n{separator_ts}\n\n{entry.strip()}\n\n"
    with note_path.open("a", encoding="utf-8") as handle:
        handle.write(block)


async def append_to_daily_note(
    note_path: Path,
    entry: str,
    lock: asyncio.Lock,
    note_date: datetime,
) -> None:
    """Append an entry to the daily note under an asyncio lock."""
    async with lock:
        await asyncio.to_thread(append_to_daily_note_sync, note_path, entry, note_date)
