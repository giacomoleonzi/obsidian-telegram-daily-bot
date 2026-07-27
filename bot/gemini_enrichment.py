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


def enrich_transcript(
    transcript: str,
    api_key: str,
    model: str,
    summary_prompt: str,
    task_prompt: str,
) -> tuple[str | None, str | None]:
    """Run both Gemini calls for opt-in promotion.

    Empty/NONE model replies become ``None`` sections (still a success).
    Network/API failures raise so the caller can mark the entry ``failed``
    without writing partial cloud content when both calls error.

    Args:
        transcript: Local Whisper transcript.
        api_key: Gemini API key.
        model: Model name.
        summary_prompt: Call A prompt body.
        task_prompt: Call B prompt body.

    Returns:
        ``(summary, tasks)`` each optional.

    Raises:
        RuntimeError: If google-genai is missing.
        Exception: Propagated from the Gemini client when a call fails.
    """
    summary_error: Exception | None = None
    tasks_error: Exception | None = None
    summary: str | None = None
    tasks: str | None = None

    try:
        summary = normalize_gemini_text(
            _generate_content(api_key, model, summary_prompt, transcript)
        )
    except Exception as exc:
        logging.exception("Gemini summary call failed during promotion")
        summary_error = exc

    try:
        tasks = normalize_task_markdown(
            _generate_content(api_key, model, task_prompt, transcript)
        )
    except Exception as exc:
        logging.exception("Gemini tasks call failed during promotion")
        tasks_error = exc

    if summary_error is not None and tasks_error is not None:
        raise summary_error
    return summary, tasks
