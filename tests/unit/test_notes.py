#!/usr/bin/env python3
"""Unit tests for daily-note Markdown builders."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from bot.notes import voice_entry_markdown


def test_voice_entry_transcript_only() -> None:
    dt = datetime(2026, 7, 27, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
    md = voice_entry_markdown(
        message_dt=dt,
        audio_embed="![[Media-folder/a.ogg]]",
        transcript="ciao mondo",
    )
    assert "#### Trascrizione" in md
    assert "ciao mondo" in md
    assert "#### Riassunto" not in md
    assert "#### Task" not in md


def test_voice_entry_with_summary_and_tasks() -> None:
    dt = datetime(2026, 7, 27, 13, 0, 0, tzinfo=ZoneInfo("UTC"))
    md = voice_entry_markdown(
        message_dt=dt,
        audio_embed="![[Media-folder/a.ogg]]",
        transcript="trascrizione lunga",
        summary="- punto A",
        tasks="- [ ] comprare latte",
    )
    assert "#### Riassunto" in md
    assert "- punto A" in md
    assert "#### Task" in md
    assert "- [ ] comprare latte" in md
    # Order: transcript before summary before tasks
    assert md.index("#### Trascrizione") < md.index("#### Riassunto") < md.index("#### Task")
