#!/usr/bin/env python3
"""Unit tests for prompt file loading."""

from __future__ import annotations

from pathlib import Path

import pytest

from bot.config import load_prompt_file


def test_load_prompt_file_ok(tmp_path: Path) -> None:
    path = tmp_path / "summary.md"
    path.write_text("# Prompt\n\nHello", encoding="utf-8")
    assert "Hello" in load_prompt_file(str(path))


def test_load_prompt_file_missing(tmp_path: Path) -> None:
    with pytest.raises(RuntimeError, match="not found"):
        load_prompt_file(str(tmp_path / "missing.md"))


def test_load_prompt_file_empty(tmp_path: Path) -> None:
    path = tmp_path / "empty.md"
    path.write_text("   \n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="empty"):
        load_prompt_file(str(path))
