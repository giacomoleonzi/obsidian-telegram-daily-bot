#!/usr/bin/env python3
"""Orchestrate opt-in Gemini promotion for a stored voice entry."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes

from bot.gemini_enrichment import enrich_transcript
from bot.notes import update_voice_entry_cloud
from bot.store import Entry, EntryStore


def gemini_keyboard(entry_id: str) -> InlineKeyboardMarkup:
    """Build the single-button opt-in keyboard for an entry."""
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("🧠 Gemini", callback_data=f"g:{entry_id}")]]
    )


def truncate_telegram(text: str, limit: int = 3500) -> str:
    """Truncate text to fit Telegram message limits with a clear suffix."""
    text = text.strip() or "(vuoto)"
    if len(text) <= limit:
        return text
    return text[: limit - 20].rstrip() + "\n…(troncato)"


def format_local_reply() -> str:
    """User-visible reply after local transcription (no transcript echo)."""
    return "✅"


def format_cloud_reply(summary: str | None, tasks: str | None) -> str:
    """User-visible reply after successful Gemini promotion (no transcript echo)."""
    parts = ["☁️ Gemini"]
    if summary:
        parts.extend(["", "#### Riassunto", summary.strip()])
    if tasks:
        parts.extend(["", "#### Task", tasks.strip()])
    if not summary and not tasks:
        parts.extend(["", "(Nessun riassunto/task aggiuntivi)"])
    return truncate_telegram("\n".join(parts), 4000)


async def promote_entry(
    context: ContextTypes.DEFAULT_TYPE,
    entry_id: str,
    *,
    answer_chat_id: int | None = None,
) -> None:
    """CAS → Gemini → vault update → Telegram edit. Safe to call concurrently.

    Marks ``processing`` **before** any cloud call. On failure restores
    ``failed`` and never corrupts the local note body beyond a no-op.
    """
    store: EntryStore = context.application.bot_data["entry_store"]
    note_lock: asyncio.Lock = context.application.bot_data["note_lock"]
    api_key: str = context.application.bot_data["gemini_api_key"]
    model: str = context.application.bot_data["gemini_model"]
    summary_prompt: str = context.application.bot_data["gemini_summary_prompt"]
    task_prompt: str = context.application.bot_data["gemini_task_prompt"]

    entry = store.try_begin_processing(entry_id)
    if entry is None:
        current = store.get_entry(entry_id)
        logging.info(
            "Skip promotion id=%s status=%s",
            entry_id,
            current.status if current else "missing",
        )
        return

    try:
        summary, tasks = await asyncio.to_thread(
            enrich_transcript,
            entry.transcript,
            api_key,
            model,
            summary_prompt,
            task_prompt,
        )
        note_path = Path(entry.note_path)
        async with note_lock:
            ok = await asyncio.to_thread(
                update_voice_entry_cloud,
                note_path,
                entry.id,
                summary,
                tasks,
            )
        if not ok:
            raise RuntimeError(f"Impossibile aggiornare la nota per entry {entry.id}")

        store.mark_cloud(entry.id, summary=summary, tasks=tasks)
        await _notify_success(context, entry, summary, tasks)
        logging.info("Promoted entry id=%s to cloud", entry.id)
    except Exception as exc:
        logging.exception("Gemini promotion failed id=%s", entry.id)
        store.mark_failed(entry.id, str(exc))
        await _notify_failure(context, entry, str(exc), answer_chat_id=answer_chat_id)


async def _notify_success(
    context: ContextTypes.DEFAULT_TYPE,
    entry: Entry,
    summary: str | None,
    tasks: str | None,
) -> None:
    text = format_cloud_reply(summary, tasks)
    if entry.telegram_message_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=entry.chat_id,
                message_id=entry.telegram_message_id,
                text=text,
                reply_markup=None,
            )
            return
        except Exception:
            logging.exception("edit_message_text failed for entry %s", entry.id)
    try:
        await context.bot.send_message(chat_id=entry.chat_id, text=text)
    except Exception:
        logging.exception("send_message success fallback failed for entry %s", entry.id)


async def _notify_failure(
    context: ContextTypes.DEFAULT_TYPE,
    entry: Entry,
    error: str,
    *,
    answer_chat_id: int | None,
) -> None:
    short = error.strip().splitlines()[0][:200] if error else "errore sconosciuto"
    text = f"{format_local_reply()}\n\n❌ Gemini: {short}"
    markup = gemini_keyboard(entry.id)
    if entry.telegram_message_id is not None:
        try:
            await context.bot.edit_message_text(
                chat_id=entry.chat_id,
                message_id=entry.telegram_message_id,
                text=text,
                reply_markup=markup,
            )
            return
        except Exception:
            logging.exception("edit_message_text failure path for entry %s", entry.id)
    chat_id = answer_chat_id or entry.chat_id
    try:
        await context.bot.send_message(chat_id=chat_id, text=text, reply_markup=markup)
    except Exception:
        logging.exception("send_message failure fallback for entry %s", entry.id)


# Re-export helpers useful to callers / tests
__all__ = [
    "format_cloud_reply",
    "format_local_reply",
    "gemini_keyboard",
    "promote_entry",
    "truncate_telegram",
]
