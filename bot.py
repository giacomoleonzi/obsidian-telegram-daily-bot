#!/usr/bin/env python3
"""Telegram to Obsidian daily note bot."""

from __future__ import annotations

import asyncio
import logging
import os
import re
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Final
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from PIL import Image, ImageOps
from telegram import Update
from telegram.error import Conflict
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters

try:
    from google import genai
except ImportError:
    genai = None

ALLOWED_STT_PROVIDERS: Final[set[str]] = {"local"}
ALLOWED_SUMMARY_PROVIDERS: Final[set[str]] = {"local", "gemini"}


def _safe_stem(value: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9_-]+", "_", value or "")
    cleaned = cleaned.strip("_")
    return cleaned[:80] if cleaned else "file"


def _message_dt_local(message_dt: datetime | None, timezone_name: str) -> datetime:
    tz = ZoneInfo(timezone_name)
    if message_dt is not None:
        return message_dt.astimezone(tz)
    return datetime.now(tz)

def _required_env(name: str) -> str:
    value = os.getenv(name)
    if value is None or not value.strip():
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value.strip()


def _required_bool_env(name: str) -> bool:
    raw = _required_env(name).lower()
    if raw in {"1", "true", "yes", "y", "on"}:
        return True
    if raw in {"0", "false", "no", "n", "off"}:
        return False
    raise RuntimeError(f"Invalid boolean for {name}: {raw}")


def _required_int_env(name: str) -> int:
    raw = _required_env(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise RuntimeError(f"Invalid integer for {name}: {raw}") from exc


def _timestamp_id(message_dt: datetime) -> str:
    return message_dt.strftime("%Y%m%d_%H%M%S")


def _daily_note_path(daily_dir: Path, message_dt: datetime, pattern: str) -> Path:
    name = message_dt.strftime(pattern).strip()
    path = daily_dir / name
    if path.suffix.lower() != ".md":
        path = path.with_suffix(".md")
    return path


def _run_ffmpeg_convert(input_path: Path, output_path: Path) -> None:
    command = ["ffmpeg", "-y", "-i", str(input_path), "-ar", "16000", "-ac", "1", str(output_path)]
    subprocess.run(command, check=True, capture_output=True, text=True)


def _transcribe_local_whisper(
    ogg_path: Path,
    wav_path: Path,
    whisper_cli_path: str,
    whisper_model_path: str,
    stt_language: str,
) -> str:
    _run_ffmpeg_convert(ogg_path, wav_path)
    output_base = wav_path.with_suffix("")
    output_txt = output_base.with_suffix(".txt")
    if output_txt.exists():
        output_txt.unlink()
    command = [
        whisper_cli_path,
        "-m",
        whisper_model_path,
        "-f",
        str(wav_path),
        "-l",
        stt_language,
        "-otxt",
        "-of",
        str(output_base),
        "-np",
    ]
    try:
        subprocess.run(command, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as exc:
        logging.error("whisper-cli failed (exit=%s): %s", exc.returncode, " ".join(command))
        if exc.stderr:
            logging.error("whisper-cli stderr: %s", exc.stderr.strip())
        raise
    if output_txt.exists():
        transcription = output_txt.read_text(encoding="utf-8").strip()
        output_txt.unlink(missing_ok=True)
        return transcription
    return ""


def _local_extractive_summary(transcript: str, max_lines: int = 5) -> str:
    normalized = " ".join(transcript.split())
    if not normalized:
        return "Nessuna trascrizione disponibile."
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", normalized) if s.strip()]
    if not sentences:
        return "Nessuna trascrizione disponibile."
    return "\n".join(f"- {item}" for item in sentences[:max_lines])


def _gemini_summary(transcript: str, api_key: str, model: str, prompt: str) -> str:
    if genai is None:
        raise RuntimeError("google-genai not installed. Use SUMMARY_PROVIDER=local.")
    client = genai.Client(api_key=api_key)
    response = client.models.generate_content(model=model, contents=f"{prompt}\n\nTrascrizione:\n{transcript}")
    return (response.text or "").strip() or "Riassunto non disponibile."


def _voice_entry_markdown(
    message_dt: datetime,
    audio_embed: str,
    transcript: str,
    summary: str,
) -> str:
    ts = message_dt.strftime("%H:%M:%S %Z")
    safe_transcript = transcript or "Nessuna trascrizione disponibile."
    return (
        f"### Audio {ts}\n\n"
        f"{audio_embed}\n\n"
        "#### Trascrizione\n\n"
        f"{safe_transcript}\n\n"
        "#### Riassunto\n\n"
        f"{summary}\n"
    )


def _image_entry_markdown(message_dt: datetime, image_embed: str, caption: str) -> str:
    ts = message_dt.strftime("%H:%M:%S %Z")
    caption_block = f"\n\n#### Caption\n\n{caption}\n" if caption else "\n"
    return f"### Immagine {ts}\n\n{image_embed}{caption_block}"


def _text_entry_markdown(message_dt: datetime, text: str) -> str:
    ts = message_dt.strftime("%H:%M:%S %Z")
    body = text.strip() or "(empty text message)"
    return f"### Text {ts}\n\n{body}\n"


def _document_entry_markdown(message_dt: datetime, file_embed: str, caption: str) -> str:
    ts = message_dt.strftime("%H:%M:%S %Z")
    caption_block = f"\n\n#### Caption\n\n{caption}\n" if caption else "\n"
    return f"### File {ts}\n\n{file_embed}{caption_block}"


def _is_authorized_chat(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """Allow updates only from the configured authorized chat id."""
    if update.message is None:
        return False
    authorized_chat_id = context.application.bot_data["authorized_chat_id"]
    current_chat_id = update.message.chat_id
    if current_chat_id == authorized_chat_id:
        return True
    logging.warning("Ignoring update from unauthorized chat_id=%s", current_chat_id)
    return False


async def _safe_reply(message, text: str) -> None:
    try:
        await message.reply_text(text)
    except Exception:
        logging.exception("Failed sending reply to user")


async def _append_to_daily_note(note_path: Path, entry: str, lock: asyncio.Lock, note_date: datetime) -> None:
    header = f"# Daily {note_date.strftime('%Y-%m-%d')}\n\n" if not note_path.exists() else ""
    separator_ts = note_date.strftime("%Y-%m-%d %H:%M:%S %Z")
    block = f"{header}---\n{separator_ts}\n\n{entry.strip()}\n\n"
    async with lock:
        await asyncio.to_thread(note_path.parent.mkdir, parents=True, exist_ok=True)
        await asyncio.to_thread(_append_text, note_path, block)


def _append_text(note_path: Path, content: str) -> None:
    with note_path.open("a", encoding="utf-8") as f:
        f.write(content)


def _compress_image_to_limit(
    image_path: Path,
    max_bytes: int,
    max_dimension: int,
    quality_start: int,
    quality_min: int,
    quality_step: int,
) -> Path:
    """Compress image with Pillow to fit under size limit."""
    if image_path.stat().st_size <= max_bytes:
        return image_path

    output_path = image_path.with_suffix(".jpg")
    with Image.open(image_path) as raw:
        image = ImageOps.exif_transpose(raw).convert("RGB")

    if max(image.size) > max_dimension:
        image.thumbnail((max_dimension, max_dimension), Image.Resampling.LANCZOS)

    for quality in range(quality_start, quality_min - 1, -quality_step):
        image.save(
            output_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=True,
        )
        if output_path.stat().st_size <= max_bytes:
            if output_path != image_path and image_path.exists():
                image_path.unlink()
            return output_path

    # Last-resort scale down and encode at minimum quality.
    width, height = image.size
    scaled = image.resize(
        (max(1, int(width * 0.8)), max(1, int(height * 0.8))),
        Image.Resampling.LANCZOS,
    )
    scaled.save(
        output_path,
        format="JPEG",
        quality=quality_min,
        optimize=True,
        progressive=True,
    )
    if output_path != image_path and image_path.exists():
        image_path.unlink()
    return output_path


async def handle_voice(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.voice is None:
        return
    if not _is_authorized_chat(update, context):
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
    gemini_prompt: str = context.application.bot_data["gemini_prompt"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = _message_dt_local(message.date, timezone_name)
    stem = f"{_timestamp_id(message_dt)}_{_safe_stem(str(message.voice.file_unique_id or message.voice.file_id))}"
    ogg_path = media_dir / f"{stem}.ogg"
    wav_path = Path(tempfile.gettempdir()) / f"{stem}.wav"
    note_path = _daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(message.voice.file_id)
        if not ogg_path.exists():
            await telegram_file.download_to_drive(custom_path=str(ogg_path))

        transcription = ""
        if stt_provider == "local":
            transcription = await asyncio.to_thread(
                _transcribe_local_whisper,
                ogg_path,
                wav_path,
                whisper_cli_path,
                whisper_model_path,
                stt_language,
            )

        if summary_provider == "gemini":
            summary = await asyncio.to_thread(
                _gemini_summary,
                transcription,
                gemini_api_key,
                gemini_model,
                gemini_prompt,
            )
        else:
            summary = _local_extractive_summary(transcription)

        entry = _voice_entry_markdown(
            message_dt=message_dt,
            audio_embed=note_template.format(audio_file=f"{media_subdir}/{ogg_path.name}"),
            transcript=transcription,
            summary=summary,
        )
        await _append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with audio: %s", note_path)
        await _safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing voice message")
        await _safe_reply(message, "❌ Error while saving the message.")
    finally:
        if wav_path.exists():
            wav_path.unlink()


async def handle_image(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None:
        return
    if not _is_authorized_chat(update, context):
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

    message_dt = _message_dt_local(message.date, timezone_name)
    stem = f"{_timestamp_id(message_dt)}_{_safe_stem(str(unique_id))}"
    image_path = media_dir / f"{stem}{suffix}"
    note_path = _daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(file_id)
        if not image_path.exists():
            await telegram_file.download_to_drive(custom_path=str(image_path))

        if image_compression_enabled and image_path.stat().st_size > image_max_bytes:
            original_size = image_path.stat().st_size
            image_path = await asyncio.to_thread(
                _compress_image_to_limit,
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

        entry = _image_entry_markdown(
            message_dt=message_dt,
            image_embed=image_note_template.format(image_file=f"{media_subdir}/{image_path.name}"),
            caption=message.caption or "",
        )
        await _append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with image: %s", note_path)
        await _safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing image message")
        await _safe_reply(message, "❌ Error while saving the message.")


async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.text is None:
        return
    if not _is_authorized_chat(update, context):
        return
    message = update.message
    text = message.text.strip()
    if not text:
        return

    daily_dir: Path = context.application.bot_data["daily_dir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = _message_dt_local(message.date, timezone_name)
    note_path = _daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        entry = _text_entry_markdown(message_dt=message_dt, text=text)
        await _append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with text: %s", note_path)
        await _safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing text message")
        await _safe_reply(message, "❌ Error while saving the message.")


async def handle_document(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.message is None or update.message.document is None:
        return
    if not _is_authorized_chat(update, context):
        return
    message = update.message
    document = message.document

    # Image documents are already handled by handle_image.
    if (document.mime_type or "").startswith("image/"):
        return

    await context.bot.send_chat_action(chat_id=message.chat_id, action=ChatAction.UPLOAD_DOCUMENT)

    daily_dir: Path = context.application.bot_data["daily_dir"]
    media_dir: Path = context.application.bot_data["media_dir"]
    media_subdir: str = context.application.bot_data["media_subdir"]
    note_pattern: str = context.application.bot_data["daily_note_format"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    timezone_name: str = context.application.bot_data["timezone_name"]

    message_dt = _message_dt_local(message.date, timezone_name)
    unique_part = _safe_stem(str(document.file_unique_id or document.file_id))
    original_name = _safe_stem(Path(document.file_name or "document").stem)
    suffix = Path(document.file_name or "document.bin").suffix or ".bin"
    filename = f"{_timestamp_id(message_dt)}_{original_name}_{unique_part}{suffix}"
    doc_path = media_dir / filename
    note_path = _daily_note_path(daily_dir, message_dt, note_pattern)

    try:
        media_dir.mkdir(parents=True, exist_ok=True)
        telegram_file = await context.bot.get_file(document.file_id)
        if not doc_path.exists():
            await telegram_file.download_to_drive(custom_path=str(doc_path))

        entry = _document_entry_markdown(
            message_dt=message_dt,
            file_embed=f"![[{media_subdir}/{doc_path.name}]]",
            caption=message.caption or "",
        )
        await _append_to_daily_note(note_path, entry, note_lock, message_dt)
        logging.info("Updated daily note with file: %s", note_path)
        await _safe_reply(message, "✅")
    except Exception:
        logging.exception("Failed processing document message")
        await _safe_reply(message, "❌ Error while saving the message.")


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


def _load_bot_config() -> dict[str, object]:
    token = _required_env("TELEGRAM_BOT_TOKEN")
    authorized_chat_id = _required_int_env("AUTHORIZED_CHAT_ID")
    timezone_name = _required_env("BOT_TIMEZONE")
    try:
        ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise RuntimeError(f"Invalid BOT_TIMEZONE: {timezone_name}") from exc
    vault_path = Path(_required_env("OB_VAULT_PATH"))
    daily_subdir = Path(_required_env("BOT_DAILY_SUBDIR"))
    media_subdir = Path(_required_env("BOT_MEDIA_SUBDIR"))
    daily_dir = vault_path / daily_subdir
    media_dir = vault_path / media_subdir

    log_level = _required_env("BOT_LOG_LEVEL").upper()
    valid_levels = set(logging.getLevelNamesMapping().keys())
    if log_level not in valid_levels:
        raise RuntimeError(f"Invalid BOT_LOG_LEVEL: {log_level}")

    daily_note_format = _required_env("BOT_DAILY_NOTE_FORMAT")
    note_template = _required_env("BOT_NOTE_TEMPLATE")
    image_note_template = _required_env("BOT_IMAGE_NOTE_TEMPLATE")
    if "{audio_file}" not in note_template:
        raise ValueError("BOT_NOTE_TEMPLATE must contain '{audio_file}'")
    if "{image_file}" not in image_note_template:
        raise ValueError("BOT_IMAGE_NOTE_TEMPLATE must contain '{image_file}'")

    image_compression_enabled = _required_bool_env("IMAGE_COMPRESSION_ENABLED")
    image_max_bytes = _required_int_env("IMAGE_MAX_BYTES")
    image_max_dimension = _required_int_env("IMAGE_MAX_DIMENSION")
    image_quality_start = _required_int_env("IMAGE_JPEG_QUALITY_START")
    image_quality_min = _required_int_env("IMAGE_JPEG_QUALITY_MIN")
    image_quality_step = _required_int_env("IMAGE_JPEG_QUALITY_STEP")
    if image_quality_step <= 0:
        raise RuntimeError("IMAGE_JPEG_QUALITY_STEP must be > 0")

    stt_provider = _required_env("STT_PROVIDER").lower()
    if stt_provider not in ALLOWED_STT_PROVIDERS:
        raise RuntimeError(f"Unsupported STT_PROVIDER: {stt_provider}")

    summary_provider = _required_env("SUMMARY_PROVIDER").lower()
    if summary_provider not in ALLOWED_SUMMARY_PROVIDERS:
        raise RuntimeError(f"Unsupported SUMMARY_PROVIDER: {summary_provider}")

    gemini_api_key = (os.getenv("GEMINI_API_KEY") or "").strip()
    if summary_provider == "gemini" and not gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is required when SUMMARY_PROVIDER=gemini")

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
        "stt_language": _required_env("STT_LANGUAGE"),
        "whisper_cli_path": _required_env("WHISPER_CLI_PATH"),
        "whisper_model_path": _required_env("WHISPER_MODEL_PATH"),
        "summary_provider": summary_provider,
        "gemini_api_key": gemini_api_key,
        "gemini_model": _required_env("GEMINI_MODEL"),
        "gemini_prompt": _required_env("GEMINI_SUMMARY_PROMPT"),
    }


def main() -> None:
    config = _load_bot_config()
    log_level_name = str(config["log_level"])
    log_level_value = logging.getLevelNamesMapping()[log_level_name]
    logging.basicConfig(
        level=log_level_value,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    # Reduce noisy framework logs (including bot-id related HTTP traces).
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    application = Application.builder().token(str(config["token"])).build()
    application.bot_data.update(config)
    application.bot_data["note_lock"] = asyncio.Lock()
    application.add_handler(CommandHandler("whoami", cmd_whoami))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(handle_application_error)

    logging.info(
        "Telegram bot started - daily_dir=%s stt_provider=%s summary_provider=%s timezone=%s authorized_chat_id=%s",
        config["daily_dir"],
        config["stt_provider"],
        config["summary_provider"],
        config["timezone_name"],
        config["authorized_chat_id"],
    )
    # Use 60s long polling to avoid frequent 10s idle requests.
    application.run_polling(timeout=60)


if __name__ == "__main__":
    main()

