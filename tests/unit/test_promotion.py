#!/usr/bin/env python3
"""Unit tests for promotion helpers (no live Gemini / Telegram)."""

from __future__ import annotations

from bot.promotion import format_cloud_reply, format_local_reply, gemini_keyboard, truncate_telegram


def test_truncate_telegram() -> None:
    assert truncate_telegram("ciao") == "ciao"
    long = "x" * 4000
    out = truncate_telegram(long, limit=100)
    assert len(out) <= 100
    assert out.endswith("…(troncato)") or "troncato" in out


def test_format_local_reply_contains_transcript() -> None:
    text = format_local_reply("ciao dal pi")
    assert "ciao dal pi" in text
    assert "Trascrizione" in text


def test_format_cloud_reply_sections() -> None:
    text = format_cloud_reply("base", summary="- a", tasks="- [ ] b")
    assert "Gemini" in text
    assert "- a" in text
    assert "- [ ] b" in text


def test_gemini_keyboard_callback_data() -> None:
    markup = gemini_keyboard("a3f9c2")
    button = markup.inline_keyboard[0][0]
    assert button.callback_data == "g:a3f9c2"
    assert "Gemini" in (button.text or "")
