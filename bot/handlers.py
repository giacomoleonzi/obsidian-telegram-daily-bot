#!/usr/bin/env python3
"""Telegram message handlers."""

from __future__ import annotations

import asyncio
import logging
import tempfile
from pathlib import Path

from telegram import Update
from telegram.constants import ChatAction
from telegram.error import Conflict
from telegram.ext import ContextTypes

from bot.gemini_enrichment import generate_summary, generate_tasks
from bot.media import compress_image_to_limit
from bot.notes import (
    append_to_daily_note,
    daily_note_path,
    document_entry_markdown,
    image_entry_markdown,
    message_dt_local,
    safe_stem,
    text_entry_markdown,
    timestamp_id,
    voice_entry_markdown,
)
from bot.stt import transcribe_local_whisper


def is_authorized_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow updates only from the configured authorized chat id."""
    if update.message is None:
        return False
    authorized_chat_id = context.application.bot_data["authorized_chat_id"]
    current_chat_id = update.message.chat_id
    if current_chat_id == authorized_chat_id:
        return True
    logging.warning("Ignoring update from unauthorized chat_id=%s", current_chat_id)
    return False


async def safe_reply(message, text: str) -> None:
    """Reply to the user, logging failures without raising."""
    try:
        await message.reply_text(text)
    except Exception:
        logging.exception("Failed sending reply to user")


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download voice, transcribe, optionally enrich with Gemini, append note."""
    if update.message is None or update.message.voice is None:
        return
    if not is_authorized_chat(update, context):
        return
    message = update.message
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.RECORD_VOICE)

    daily_dir: Path = context.application.bot_data["daily_dir"]
    media_dir: Path = context.application.bot_data["media_dir"]
    media_subdir: str = context.application.bot_data["media_subdir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    note_template: str = context.application.bot_data["note_template"]
    stt_provider: str = context.application.bot_data["stt_provider"]
    stt_language: str = context.application.bot_data["stt_language"]
    whisper_cli_path: str = context.application.bot_data["whisper_cli_path"]
    whisper_model_path: str = context.application.bot_data["whisper_model_path"]
    summary_provider: str = context.application.bot_data["summary_provider"]
    gemini_api_key: str = context.application.bot_data["gemini_api_key"]
    gemini_model: str = context.application.bot_data["gemini_model"]
    gemini_summary_prompt: str = context.application.bot_data["gemini_summary_prompt"]
    gemini_task_prompt: str = context.application.bot_data["gemini_task_prompt"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = message_dt_local(message.date, timezone_name)
    stem = f"{timestamp_id(message_dt)}_{safe_stem(str(message.voice.file_unique_id or message.voice.file_id))}"
    ogg_path = media_dir / f"{stem}.ogg"
    wav_path = Path(tempfile.gettempdir()) / f"{stem}.wav"
    note_path = daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(message.voice.file_id)
        if not ogg_path.exists():
            await telegram_file.download_to_drive(custom_path=str(ogg_path))

        transcription = ""
        if stt_provider == "local":
            transcription = await asyncio.to_thread(
                transcribe_local_whisper,
                ogg_path,
                wav_path,
                whisper_cli_path,
                whisper_model_path,
                stt_language,
            )

        summary: str | None = None
        tasks: str | None = None
        if summary_provider == "gemini":
            summary = await asyncio.to_thread(
                generate_summary,
                transcription,
                gemini_api_key,
                gemini_model,
                gemini_summary_prompt,
            )
            tasks = await asyncio.to_thread(
                generate_tasks,
                transcription,
                gemini_api_key,
                gemini_model,
                gemini_task_prompt,
            )

        entry = voice_entry_markdown(
            message_dt=message_dt,
            audio_embed=note_template.format(audio_file=f"{media_subdir}/{ogg_path.name}"),
            transcript=transcription,
            summary=summary,
            tasks=tasks,
        )
        await append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with audio: %s", note_path)
        await safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing voice message")
        await safe_reply(message, "❌ Error while saving the message.")
    finally:
        if wav_path.exists():
            wav_path.unlink()


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download and optionally compress an image, then append to the daily note."""
    if update.message is None:
        return
    if not is_authorized_chat(update, context):
        return
    message = update.message
    if message.photo:
        file_id = message.photo[-1].file_id
        unique_id = message.photo[-1].file_unique_id or file_id
        suffix = ".jpg"
    elif message.document and (message.document.mime_type or "").startswith("image/"):
        file_id = message.document.file_id
        unique_id = message.document.file_unique_id or file_id
        suffix = Path(message.document.file_name or "image.img").suffix or ".img"
    else:
        return
    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_PHOTO)

    daily_dir: Path = context.application.bot_data["daily_dir"]
    media_dir: Path = context.application.bot_data["media_dir"]
    media_subdir: str = context.application.bot_data["media_subdir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    image_note_template: str = context.application.bot_data["image_note_template"]
    image_compression_enabled: bool = context.application.bot_data["image_compression_enabled"]
    image_max_bytes: int = context.application.bot_data["image_max_bytes"]
    image_max_dimension: int = context.application.bot_data["image_max_dimension"]
    image_quality_start: int = context.application.bot_data["image_quality_start"]
    image_quality_min: int = context.application.bot_data["image_quality_min"]
    image_quality_step: int = context.application.bot_data["image_quality_step"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = message_dt_local(message.date, timezone_name)
    stem = f"{timestamp_id(message_dt)}_{safe_stem(str(unique_id))}"
    image_path = media_dir / f"{stem}{suffix}"
    note_path = daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(file_id)
        if not image_path.exists():
            await telegram_file.download_to_drive(custom_path=str(image_path))

        if image_compression_enabled and image_path.stat().st_size > image_max_bytes:
            original_size = image_path.stat().st_size
            image_path = await asyncio.to_thread(
                compress_image_to_limit,
                image_path,
                image_max_bytes,
                image_max_dimension,
                image_quality_start,
                image_quality_min,
                image_quality_step,
            )
            logging.info(
                "Compressed image from %s to %s bytes: %s",
                original_size,
                image_path.stat().st_size,
                image_path.name,
            )

        entry = image_entry_markdown(
            message_dt=message_dt,
            image_embed=image_note_template.format(image_file=f"{media_subdir}/{image_path.name}"),
            caption=message.caption or "",
        )
        await append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with image: %s", note_path)
        await safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing image message")
        await safe_reply(message, "❌ Error while saving the message.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Append a plain text message to the daily note."""
    if update.message is None or update.message.text is None:
        return
    if not is_authorized_chat(update, context):
        return
    message = update.message
    text = message.text.strip()
    if not text:
        return

    daily_dir: Path = context.application.bot_data["daily_dir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = message_dt_local(message.date, timezone_name)
    note_path = daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        entry = text_entry_markdown(message_dt=message_dt, text=text)
        await append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with text: %s", note_path)
        await safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing text message")
        await safe_reply(message, "❌ Error while saving the message.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Download a non-image document and append an embed to the daily note."""
    if update.message is None or update.message.document is None:
        return
    if not is_authorized_chat(update, context):
        return
    message = update.message
    document = message.document

    if (document.mime_type or "").startswith("image/"):
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    daily_dir: Path = context.application.bot_data["daily_dir"]
    media_dir: Path = context.application.bot_data["media_dir"]
    media_subdir: str = context.application.bot_data["media_subdir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = message_dt_local(message.date, timezone_name)
    unique_part = safe_stem(str(document.file_unique_id or document.file_id))
    original_name = safe_stem(Path(document.file_name or "document").stem)
    suffix = Path(document.file_name or "document.bin").suffix or ".bin"
    filename = f"{timestamp_id(message_dt)}_{original_name}_{unique_part}{suffix}"
    doc_path = media_dir / filename
    note_path = daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(document.file_id)
        if not doc_path.exists():
            await telegram_file.download_to_drive(custom_path=str(doc_path))

        entry = document_entry_markdown(
            message_dt=message_dt,
            file_embed=f"![[{media_subdir}/{doc_path.name}]]",
            caption=message.caption or "",
        )
        await append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with file: %s", note_path)
        await safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing document message")
        await safe_reply(message, "❌ Error while saving the message.")


async def cmd_whoami(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Reply with chat/user identifiers for quick verification."""
    if update.message is None:
        return
    message = update.message
    user = message.from_user
    chat = message.chat
    authorized_chat_id = context.application.bot_data["authorized_chat_id"]
    is_authorized = chat.id == authorized_chat_id
    lines = [
        "Identity check:",
        f"- chat_id: `{chat.id}`",
        f"- chat_type: `{chat.type}`",
    ]
    if is_authorized:
        lines.append(f"- authorized_chat_id: `{authorized_chat_id}`")
        lines.append(f"- is_authorized_chat: `{is_authorized}`")
    else:
        lines.append("- is_authorized_chat: `False`")
    if user is not None:
        lines.append(f"- user_id: `{user.id}`")
        if user.username:
            lines.append(f"- username: `@{user.username}`")
        if user.full_name:
            lines.append(f"- full_name: `{user.full_name}`")
    await message.reply_text("\n".join(lines), parse_mode="Markdown")


async def handle_application_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle global telegram application errors."""
    if isinstance(context.error, Conflict):
        logging.error(
            "Telegram polling conflict: another bot instance is using the same token. "
            "Stopping this instance to avoid retry loop."
        )
        context.application.stop_running()
        return
    logging.exception("Unhandled telegram application error: %s", context.error)
