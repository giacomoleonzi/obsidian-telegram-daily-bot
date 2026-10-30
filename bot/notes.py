#!/usr/bin/env python3
"""Daily-note path helpers and Markdown entry builders."""

from __future__ import annotations

import asyncio
import logging
import re
import tempfile
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.note_templates import render_template

_ENTRY_MARKER_RE = re.compile(r"<!--\s*entry:([A-Za-z0-9_-]+)\s*-->")
_PROCESSING_FIELD_RE = re.compile(r"^processing::\s*\S+\s*$", re.MULTILINE)


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


def _heading_time(message_dt: datetime) -> str:
    return message_dt.strftime("%H:%M:%S")


def _separator_ts(message_dt: datetime) -> str:
    return message_dt.strftime("%Y-%m-%d %H:%M:%S")


def voice_entry_markdown(
    message_dt: datetime,
    audio_embed: str,
    transcript: str,
    entry_id: str,
    summary: str | None = None,
    tasks: str | None = None,
    status: str = "local",
) -> str:
    """Build a voice entry for the daily note via Jinja template."""
    return render_template(
        "voice.md.j2",
        time=_heading_time(message_dt),
        audio_embed=audio_embed,
        transcript=transcript or "Nessuna trascrizione disponibile.",
        entry_id=entry_id,
        summary=(summary.strip() if summary else None),
        tasks=(tasks.strip() if tasks else None),
        status=status,
    )


def image_entry_markdown(message_dt: datetime, image_embed: str, caption: str) -> str:
    """Build an image entry for the daily note via Jinja template."""
    return render_template(
        "image.md.j2",
        time=_heading_time(message_dt),
        image_embed=image_embed,
        caption=caption.strip() if caption else "",
    )


def text_entry_markdown(message_dt: datetime, text: str) -> str:
    """Build a plain-text entry for the daily note via Jinja template."""
    return render_template(
        "text.md.j2",
        time=_heading_time(message_dt),
        body=text.strip() or "(empty text message)",
    )


def document_entry_markdown(message_dt: datetime, file_embed: str, caption: str) -> str:
    """Build a document entry for the daily note via Jinja template."""
    return render_template(
        "document.md.j2",
        time=_heading_time(message_dt),
        file_embed=file_embed,
        caption=caption.strip() if caption else "",
    )


def _split_blocks(content: str) -> list[str]:
    """Split a daily note into preamble + bodies that followed ``---`` lines."""
    if not content:
        return [""]
    return re.split(r"(?m)^---\n", content)


def _join_blocks(parts: list[str]) -> str:
    """Inverse of ``_split_blocks``."""
    if not parts:
        return ""
    if len(parts) == 1:
        return parts[0]
    return parts[0] + "".join(f"---\n{part}" for part in parts[1:])


def _inject_cloud_sections(block: str, summary: str | None, tasks: str | None) -> str:
    """Update status field and Riassunto/Task sections inside one entry block."""
    block = _PROCESSING_FIELD_RE.sub("processing:: cloud", block, count=1)
    if "processing:: cloud" not in block and "processing::" not in block:
        block = _ENTRY_MARKER_RE.sub(
            lambda m: f"{m.group(0)}\nprocessing:: cloud",
            block,
            count=1,
        )

    block = re.sub(
        r"\n#### Riassunto\n.*?(?=\n#### |\n### |\n---|\Z)",
        "\n",
        block,
        flags=re.DOTALL,
    )
    block = re.sub(
        r"\n#### Task\n.*?(?=\n#### |\n### |\n---|\Z)",
        "\n",
        block,
        flags=re.DOTALL,
    )

    extras: list[str] = []
    if summary and summary.strip():
        extras.extend(["", "#### Riassunto", summary.strip(), ""])
    if tasks and tasks.strip():
        extras.extend(["", "#### Task", tasks.strip(), ""])
    if not extras:
        return block.rstrip() + "\n"

    match = re.search(r"(#### Trascrizione\n.*?)(?=\n#### |\n### |\Z)", block, flags=re.DOTALL)
    if match:
        insert_at = match.end()
        return (
            block[:insert_at].rstrip()
            + "\n"
            + "\n".join(extras).strip()
            + "\n"
            + block[insert_at:].lstrip()
        )
    return block.rstrip() + "\n" + "\n".join(extras).strip() + "\n"


def update_voice_entry_cloud(
    note_path: Path,
    entry_id: str,
    summary: str | None,
    tasks: str | None,
) -> bool:
    """Rewrite one voice entry with cloud sections; leave others untouched."""
    if not note_path.is_file():
        logging.error("Daily note not found for cloud update: %s", note_path)
        return False

    content = note_path.read_text(encoding="utf-8")
    marker = f"<!-- entry:{entry_id} -->"
    if marker not in content:
        logging.error("Entry marker not found in %s: %s", note_path, entry_id)
        return False

    parts = _split_blocks(content)
    updated = False
    for i, part in enumerate(parts):
        if marker not in part:
            continue
        parts[i] = _inject_cloud_sections(part, summary, tasks)
        updated = True
        break

    if not updated:
        return False

    _atomic_write_text(note_path, _join_blocks(parts))
    return True


def _atomic_write_text(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` via temp file + replace."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w",
        encoding="utf-8",
        dir=str(path.parent),
        delete=False,
        prefix=f".{path.name}.",
        suffix=".tmp",
    ) as handle:
        handle.write(text)
        tmp_name = handle.name
    Path(tmp_name).replace(path)


def _blank_line_before_separator(existing: str) -> str:
    """Return the exact prefix needed so ``---`` is preceded by one blank line.

    Markdown needs a blank line before ``---`` (thematic break). Avoid stacking
    extra blank lines that create large gaps in Obsidian.
    """
    if not existing:
        return ""
    if existing.endswith("\n\n"):
        return ""
    if existing.endswith("\n"):
        return "\n"
    return "\n\n"


def append_to_daily_note_sync(note_path: Path, entry: str, note_date: datetime) -> None:
    """Append an entry to the daily note synchronously using Jinja templates.

    Ensures exactly one blank line before ``---`` (Setext-safe, no extra gaps).
    """
    note_path.parent.mkdir(parents=True, exist_ok=True)
    header = ""
    prefix = ""
    if not note_path.exists():
        header = render_template("daily_header.md.j2", date=note_date.strftime("%Y-%m-%d"))
    else:
        existing = note_path.read_text(encoding="utf-8")
        prefix = _blank_line_before_separator(existing)
    block = render_template(
        "block.md.j2",
        separator_ts=_separator_ts(note_date),
        entry=entry.strip(),
    ).lstrip("\n")
    with note_path.open("a", encoding="utf-8") as handle:
        handle.write(f"{header}{prefix}{block}")


async def append_to_daily_note(
    note_path: Path,
    entry: str,
    lock: asyncio.Lock,
    note_date: datetime,
) -> None:
    """Append an entry to the daily note under an asyncio lock."""
    async with lock:
        await asyncio.to_thread(append_to_daily_note_sync, note_path, entry, note_date)
