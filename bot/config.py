#!/usr/bin/env python3
"""Environment and prompt-file configuration for the bot."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

ALLOWED_STT_PROVIDERS: Final[set[str]] = {"local"}
ALLOWED_SUMMARY_PROVIDERS: Final[set[str]] = {"local", "gemini"}


def required_env(name: str) -> str:
    """Return a required non-empty environment variable.

    Args:
        name: Environment variable name.

    Returns:
        Stripped environment value.

    Raises:
        RuntimeError: If the variable is missing or blank.
    """
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def required_bool_env(name: str) -> bool:
    """Parse a required boolean environment variable.

    Args:
        name: Environment variable name.

    Returns:
        Parsed boolean.

    Raises:
        RuntimeError: If the value is not a recognized boolean token.
    """
    raw = required_env(name).lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean for {name}: {raw}")


def required_int_env(name: str) -> int:
    """Parse a required integer environment variable.

    Args:
        name: Environment variable name.

    Returns:
        Parsed integer.

    Raises:
        RuntimeError: If the value is not an integer.
    """
    raw = required_env(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


def load_prompt_file(path_value: str) -> str:
    """Load a Gemini prompt Markdown file from a relative or absolute path.

    Args:
        path_value: Path string from env (relative to CWD unless absolute).

    Returns:
        Prompt text contents.

    Raises:
        RuntimeError: If the file is missing or empty.
    """
    path = Path(path_value)
    if not path.is_absolute():
        path = Path.cwd() / path
    if not path.is_file():
        raise RuntimeError(f"Prompt file not found: {path}")
    text = path.read_text(encoding="utf-8").strip()
    if not text:
        raise RuntimeError(f"Prompt file is empty: {path}")
    return text


def load_bot_config() -> dict[str, object]:
    """Load and validate runtime configuration from the environment.

    Returns:
        Config dictionary stored on ``application.bot_data``.

    Raises:
        RuntimeError: On invalid or missing configuration.
        ValueError: On invalid note templates.
    """
    token = required_env("TELEGRAM_BOT_TOKEN")
    authorized_chat_id = required_int_env("AUTHORIZED_CHAT_ID")
    timezone_name = required_env("BOT_TIMEZONE")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Invalid BOT_TIMEZONE: {timezone_name}") from exc

    vault_path = Path(required_env("OB_VAULT_PATH"))
    daily_subdir = Path(required_env("BOT_DAILY_SUBDIR"))
    media_subdir = Path(required_env("BOT_MEDIA_SUBDIR"))
    daily_dir = vault_path / daily_subdir
    media_dir = vault_path / media_subdir

    log_level = required_env("BOT_LOG_LEVEL").upper()
    valid_levels = set(logging.getLevelNamesMapping().keys())
    if log_level not in valid_levels:
        raise RuntimeError(f"Invalid BOT_LOG_LEVEL: {log_level}")

    daily_note_format = required_env("BOT_DAILY_NOTE_FORMAT")
    note_template = required_env("BOT_NOTE_TEMPLATE")
    image_note_template = required_env("BOT_IMAGE_NOTE_TEMPLATE")
    if "{audio_file}" not in note_template:
        raise ValueError("BOT_NOTE_TEMPLATE must contain '{audio_file}'")
    if "{image_file}" not in image_note_template:
        raise ValueError("BOT_IMAGE_NOTE_TEMPLATE must contain '{image_file}'")

    image_compression_enabled = required_bool_env("IMAGE_COMPRESSION_ENABLED")
    image_max_bytes = required_int_env("IMAGE_MAX_BYTES")
    image_max_dimension = required_int_env("IMAGE_MAX_DIMENSION")
    image_quality_start = required_int_env("IMAGE_JPEG_QUALITY_START")
    image_quality_min = required_int_env("IMAGE_JPEG_QUALITY_MIN")
    image_quality_step = required_int_env("IMAGE_JPEG_QUALITY_STEP")
    if image_quality_step <= 0:
        raise RuntimeError("IMAGE_JPEG_QUALITY_STEP must be > 0")

    stt_provider = required_env("STT_PROVIDER").lower()
    if stt_provider not in ALLOWED_STT_PROVIDERS:
        raise RuntimeError(f"Unsupported STT_PROVIDER: {stt_provider}")

    summary_provider = required_env("SUMMARY_PROVIDER").lower()
    if summary_provider not in ALLOWED_SUMMARY_PROVIDERS:
        raise RuntimeError(f"Unsupported SUMMARY_PROVIDER: {summary_provider}")

    gemini_api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if summary_provider == "gemini" and not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when SUMMARY_PROVIDER=gemini")

    summary_prompt = load_prompt_file(required_env("GEMINI_SUMMARY_PROMPT_FILE"))
    task_prompt = load_prompt_file(required_env("GEMINI_TASK_PROMPT_FILE"))

    return {
        "token": token,
        "authorized_chat_id": authorized_chat_id,
        "timezone_name": timezone_name,
        "daily_dir": daily_dir,
        "media_dir": media_dir,
        "media_subdir": str(media_subdir),
        "daily_note_format": daily_note_format,
        "log_level": log_level,
        "note_template": note_template,
        "image_note_template": image_note_template,
        "image_compression_enabled": image_compression_enabled,
        "image_max_bytes": image_max_bytes,
        "image_max_dimension": image_max_dimension,
        "image_quality_start": image_quality_start,
        "image_quality_min": image_quality_min,
        "image_quality_step": image_quality_step,
        "stt_provider": stt_provider,
        "stt_language": required_env("STT_LANGUAGE"),
        "whisper_cli_path": required_env("WHISPER_CLI_PATH"),
        "whisper_model_path": required_env("WHISPER_MODEL_PATH"),
        "summary_provider": summary_provider,
        "gemini_api_key": gemini_api_key,
        "gemini_model": required_env("GEMINI_MODEL"),
        "gemini_summary_prompt": summary_prompt,
        "gemini_task_prompt": task_prompt,
    }
