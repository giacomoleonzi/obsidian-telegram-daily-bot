#!/usr/bin/env python3
"""Jinja2 renderer for Obsidian daily-note Markdown templates."""

from __future__ import annotations

from pathlib import Path
from typing import Final

from jinja2 import Environment, FileSystemLoader, StrictUndefined, TemplateNotFound

REQUIRED_TEMPLATES: Final[tuple[str, ...]] = (
    "daily_header.md.j2",
    "block.md.j2",
    "text.md.j2",
    "voice.md.j2",
    "image.md.j2",
    "document.md.j2",
)

_DEFAULT_TEMPLATES_DIR: Final[Path] = Path(__file__).resolve().parent.parent / "config" / "templates"

_env: Environment | None = None
_templates_dir: Path | None = None


def default_templates_dir() -> Path:
    """Return the packaged default templates directory."""
    return _DEFAULT_TEMPLATES_DIR


def configure_note_templates(templates_dir: Path) -> Path:
    """Load and validate Jinja templates from ``templates_dir``.

    Args:
        templates_dir: Directory containing ``*.md.j2`` files.

    Returns:
        Resolved templates directory.

    Raises:
        RuntimeError: If the directory or a required template is missing.
    """
    global _env, _templates_dir
    path = templates_dir.expanduser()
    if not path.is_absolute():
        path = Path.cwd() / path
    path = path.resolve()
    if not path.is_dir():
        raise RuntimeError(f"Note templates directory not found: {path}")

    env = Environment(
        loader=FileSystemLoader(str(path)),
        undefined=StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
        keep_trailing_newline=True,
        autoescape=False,
    )
    missing = [name for name in REQUIRED_TEMPLATES if not (path / name).is_file()]
    if missing:
        raise RuntimeError(f"Missing note templates in {path}: {', '.join(missing)}")
    # Fail fast on syntax errors.
    for name in REQUIRED_TEMPLATES:
        env.get_template(name)

    _env = env
    _templates_dir = path
    return path


def _get_env() -> Environment:
    if _env is None:
        configure_note_templates(default_templates_dir())
    assert _env is not None
    return _env


def render_template(name: str, **context: object) -> str:
    """Render a named template with the given context.

    Args:
        name: Template filename (e.g. ``text.md.j2``).
        **context: Template variables.

    Returns:
        Rendered Markdown string.

    Raises:
        RuntimeError: If the template cannot be loaded.
    """
    try:
        template = _get_env().get_template(name)
    except TemplateNotFound as exc:
        raise RuntimeError(f"Note template not found: {name}") from exc
    return template.render(**context)
