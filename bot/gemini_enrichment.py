#!/usr/bin/env python3
"""Gemini enrichment: optional summary and Obsidian tasks from a transcript."""

from __future__ import annotations

import logging
import re
from typing import Final

try:
    from google import genai
except ImportError:  # pragma: no cover - optional at runtime for local-only
    genai = None

_NONE_TOKENS: Final[set[str]] = {"none", "n/a", "na", "null"}


def normalize_gemini_text(raw: str | None) -> str | None:
    """Treat empty / NONE-like Gemini replies as no content.

    Args:
        raw: Raw model response text.

    Returns:
        Stripped text, or ``None`` if the reply means “no section”.
    """
    if raw is None:
        return None
    text = raw.strip()
    if not text:
        return None
    # Accept bare NONE or a fenced ```text NONE ``` style reply.
    compact = re.sub(r"^```(?:\w+)?\s*|\s*```$", "", text, flags=re.IGNORECASE).strip()
    if compact.lower() in _NONE_TOKENS:
        return None
    if compact.upper() == "NONE":
        return None
    return text


def normalize_task_markdown(raw: str | None) -> str | None:
    """Normalize Gemini task output into Obsidian checkbox lines.

    Args:
        raw: Raw model response (may include plain bullets).

    Returns:
        Newline-joined ``- [ ]`` lines, or ``None`` if no tasks.
    """
    text = normalize_gemini_text(raw)
    if text is None:
        return None

    tasks: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        # Already a checkbox (checked or unchecked).
        checkbox = re.match(r"^[-*]\s+\[([ xX])\]\s+(.+)$", stripped)
        if checkbox:
            body = checkbox.group(2).strip()
            if body:
                tasks.append(f"- [ ] {body}")
            continue
        # Plain markdown bullet → checkbox.
        bullet = re.match(r"^[-*]\s+(.+)$", stripped)
        if bullet:
            body = bullet.group(1).strip()
            # Skip nested none / empty.
            if body and body.upper() != "NONE":
                tasks.append(f"- [ ] {body}")
            continue
        # Numbered list item.
        numbered = re.match(r"^\d+[.)]\s+(.+)$", stripped)
        if numbered:
            body = numbered.group(1).strip()
            if body:
                tasks.append(f"- [ ] {body}")
            continue
        # Ignore prose / headings / other noise.
    if not tasks:
        return None
    return "\n".join(tasks)


def _generate_content(api_key: str, model: str, prompt: str, transcript: str) -> str:
    """Call Gemini generate_content and return response text.

    Args:
        api_key: Gemini API key.
        model: Model name.
        prompt: Prompt body from Markdown file.
        transcript: Voice transcript.

    Returns:
        Raw response text (may be empty).

    Raises:
        RuntimeError: If google-genai is not installed.
    """
    if genai is None:
        raise RuntimeError("google-genai not installed. Use SUMMARY_PROVIDER=local.")
    client = genai.Client(api_key=api_key)
    contents = f"{prompt}\n\nTrascrizione:\n{transcript}"
    response = client.models.generate_content(model=model, contents=contents)
    return (response.text or "").strip()


def generate_summary(transcript: str, api_key: str, model: str, prompt: str) -> str | None:
    """Run Gemini Call A (summary). Returns None on empty/NONE or on failure.

    Args:
        transcript: Voice transcript.
        api_key: Gemini API key.
        model: Model name.
        prompt: Summary prompt text.

    Returns:
        Summary markdown body, or ``None``.
    """
    try:
        raw = _generate_content(api_key, model, prompt, transcript)
        return normalize_gemini_text(raw)
    except Exception:
        logging.exception("Gemini summary call failed")
        return None


def generate_tasks(transcript: str, api_key: str, model: str, prompt: str) -> str | None:
    """Run Gemini Call B (tasks). Returns None on empty/NONE or on failure.

    Args:
        transcript: Voice transcript.
        api_key: Gemini API key.
        model: Model name.
        prompt: Task prompt text.

    Returns:
        Task checkbox markdown, or ``None``.
    """
    try:
        raw = _generate_content(api_key, model, prompt, transcript)
        return normalize_task_markdown(raw)
    except Exception:
        logging.exception("Gemini task call failed")
        return None
