#!/usr/bin/env python3
"""Unit tests for Gemini response normalization."""

from __future__ import annotations

from bot.gemini_enrichment import normalize_gemini_text, normalize_task_markdown


def test_normalize_gemini_text_none_variants() -> None:
    assert normalize_gemini_text(None) is None
    assert normalize_gemini_text("") is None
    assert normalize_gemini_text("   ") is None
    assert normalize_gemini_text("NONE") is None
    assert normalize_gemini_text("none") is None
    assert normalize_gemini_text("```text\nNONE\n```") is None


def test_normalize_gemini_text_keeps_content() -> None:
    assert normalize_gemini_text("- punto uno\n- punto due") == "- punto uno\n- punto due"


def test_normalize_task_markdown_checkboxes() -> None:
    raw = "- [ ] comprare il latte\n- [x] già fatto"
    result = normalize_task_markdown(raw)
    assert result == "- [ ] comprare il latte\n- [ ] già fatto"


def test_normalize_task_markdown_plain_bullets() -> None:
    raw = "- comprare il latte\n* chiamare Mario"
    result = normalize_task_markdown(raw)
    assert result == "- [ ] comprare il latte\n- [ ] chiamare Mario"


def test_normalize_task_markdown_numbered_and_noise() -> None:
    raw = "Ecco i task:\n1. prenotare visita\n2) mandare email\n#### Task"
    result = normalize_task_markdown(raw)
    assert result == "- [ ] prenotare visita\n- [ ] mandare email"


def test_normalize_task_markdown_none() -> None:
    assert normalize_task_markdown("NONE") is None
    assert normalize_task_markdown("solo prosa senza bullet") is None


def test_enrich_transcript_raises_when_both_calls_fail(monkeypatch) -> None:
    from bot import gemini_enrichment as ge

    def boom(*_args, **_kwargs):
        raise RuntimeError("network down")

    monkeypatch.setattr(ge, "_generate_content", boom)
    try:
        ge.enrich_transcript("t", "key", "model", "s", "t")
        raise AssertionError("expected RuntimeError")
    except RuntimeError as exc:
        assert "network" in str(exc)


def test_enrich_transcript_ok(monkeypatch) -> None:
    from bot import gemini_enrichment as ge

    def fake(_key, _model, prompt, _transcript):
        if "summary" in prompt.lower() or prompt == "SUM":
            return "- punto"
        return "- [ ] task"

    monkeypatch.setattr(ge, "_generate_content", fake)
    summary, tasks = ge.enrich_transcript("ciao", "k", "m", "SUM", "TASK")
    assert summary == "- punto"
    assert tasks == "- [ ] task"
