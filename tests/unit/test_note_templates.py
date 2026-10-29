#!/usr/bin/env python3
"""Unit tests for Jinja note template loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.note_templates import configure_note_templates, default_templates_dir


def test_default_templates_load() -> None:
    path = configure_note_templates(default_templates_dir())
    assert path.is_dir()
    assert (path / "text.md.j2").is_file()


def test_missing_templates_dir_fails(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not found"):
        configure_note_templates(tmp_path / "missing")


def test_missing_required_template_fails(tmp_path: Path) -> None:
    (tmp_path / "text.md.j2").write_text("x\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="Missing note templates"):
        configure_note_templates(tmp_path)
