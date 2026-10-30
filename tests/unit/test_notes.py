#!/usr/bin/env python3
"""Unit tests for daily-note Markdown builders and cloud updates."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from bot.note_templates import configure_note_templates, default_templates_dir
from bot.notes import (
    append_to_daily_note_sync,
    text_entry_markdown,
    update_voice_entry_cloud,
    voice_entry_markdown,
)

configure_note_templates(default_templates_dir())


def test_text_entry_compact_no_timezone() -> None:
    dt = datetime(2026, 10, 28, 18, 30, 47, tzinfo=ZoneInfo("UTC"))
    md = text_entry_markdown(message_dt=dt, text="Sicofansia")
    assert md == "### Text 18:30:47\nSicofansia\n"


def test_append_block_matches_expected_layout(tmp_path: Path) -> None:
    dt = datetime(2026, 10, 28, 18, 30, 47, tzinfo=ZoneInfo("UTC"))
    note = tmp_path / "2026-10-28.md"
    entry = text_entry_markdown(message_dt=dt, text="Sicofansia")
    append_to_daily_note_sync(note, entry, dt)
    text = note.read_text(encoding="utf-8")
    # Blank line before --- so MD does not treat it as a Setext heading.
    assert "\n\n---\n\n2026-10-28 18:30:47\n### Text 18:30:47\nSicofansia\n" in text
    assert text.startswith("# Daily 2026-10-28\n")


def test_second_append_has_blank_line_before_separator(tmp_path: Path) -> None:
    dt = datetime(2026, 10, 28, 18, 30, 47, tzinfo=ZoneInfo("UTC"))
    note = tmp_path / "2026-10-28.md"
    append_to_daily_note_sync(note, text_entry_markdown(dt, "prima"), dt)
    append_to_daily_note_sync(
        note,
        text_entry_markdown(dt.replace(minute=31), "seconda"),
        dt.replace(minute=31),
    )
    text = note.read_text(encoding="utf-8")
    assert "prima\n\n---\n\n2026-10-28 18:31:47\n### Text 18:31:47\nseconda\n" in text


def test_voice_entry_transcript_only() -> None:
    dt = datetime(2026, 7, 27, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
    md = voice_entry_markdown(
        message_dt=dt,
        audio_embed="![[Media-folder/a.ogg]]",
        transcript="ciao mondo",
        entry_id="a3f9c2",
    )
    assert "<!-- entry:a3f9c2 -->" in md
    assert "processing:: local" in md
    assert "#### Trascrizione" in md
    assert "ciao mondo" in md
    assert "#### Riassunto" not in md
    assert "#### Task" not in md
    assert "UTC" not in md


def test_voice_entry_with_summary_and_tasks() -> None:
    dt = datetime(2026, 7, 27, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
    md = voice_entry_markdown(
        message_dt=dt,
        audio_embed="![[Media-folder/a.ogg]]",
        transcript="trascrizione lunga",
        entry_id="deadbe",
        summary="- punto A",
        tasks="- [ ] comprare latte",
        status="cloud",
    )
    assert "processing:: cloud" in md
    assert "#### Riassunto" in md
    assert "- punto A" in md
    assert "#### Task" in md
    assert "- [ ] comprare latte" in md
    assert md.index("#### Trascrizione") < md.index("#### Riassunto") < md.index("#### Task")


def test_update_voice_entry_cloud_preserves_other_entries(tmp_path: Path) -> None:
    dt = datetime(2026, 7, 27, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
    note = tmp_path / "2026-07-27.md"
    first = voice_entry_markdown(
        message_dt=dt,
        audio_embed="![[Media-folder/a.ogg]]",
        transcript="prima",
        entry_id="111111",
    )
    second = voice_entry_markdown(
        message_dt=dt.replace(minute=1),
        audio_embed="![[Media-folder/b.ogg]]",
        transcript="seconda",
        entry_id="222222",
    )
    append_to_daily_note_sync(note, first, dt)
    append_to_daily_note_sync(note, second, dt.replace(minute=1))

    ok = update_voice_entry_cloud(
        note,
        entry_id="111111",
        summary="- riassunto uno",
        tasks="- [ ] task uno",
    )
    assert ok is True
    text = note.read_text(encoding="utf-8")
    assert "prima" in text
    assert "seconda" in text
    assert "<!-- entry:111111 -->" in text
    assert "<!-- entry:222222 -->" in text
    idx1 = text.index("<!-- entry:111111 -->")
    idx2 = text.index("<!-- entry:222222 -->")
    block1 = text[idx1:idx2]
    block2 = text[idx2:]
    assert "processing:: cloud" in block1
    assert "#### Riassunto" in block1
    assert "- riassunto uno" in block1
    assert "- [ ] task uno" in block1
    assert "processing:: local" in block2
    assert "#### Riassunto" not in block2


def test_update_voice_entry_missing_id_returns_false(tmp_path: Path) -> None:
    note = tmp_path / "empty.md"
    note.write_text("# Daily\n\n", encoding="utf-8")
    assert update_voice_entry_cloud(note, "nope", summary="x", tasks=None) is False
