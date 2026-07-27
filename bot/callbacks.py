#!/usr/bin/env python3
"""CallbackQuery handlers for opt-in Gemini promotion."""

from __future__ import annotations

import logging
import re

from telegram import Update
from telegram.ext import ContextTypes

from bot.handlers import is_authorized_chat
from bot.promotion import promote_entry
from bot.store import EntryStore, STATUS_CLOUD, STATUS_PROCESSING

_CALLBACK_RE = re.compile(r"^g:([A-Za-z0-9_-]{4,16})$")


async def handle_gemini_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle ``g:{id}`` inline button taps (deferred-safe, idempotent)."""
    query = update.callback_query
    if query is None or query.data is None:
        return
    if not is_authorized_chat(update, context):
        await query.answer("Non autorizzato.", show_alert=True)
        return

    match = _CALLBACK_RE.match(query.data)
    if not match:
        await query.answer("Callback non valido.", show_alert=True)
        return

    entry_id = match.group(1)
    store: EntryStore = context.application.bot_data["entry_store"]
    gemini_api_key: str = context.application.bot_data["gemini_api_key"]
    if not gemini_api_key:
        await query.answer("GEMINI_API_KEY non configurata.", show_alert=True)
        return

    entry = store.get_entry(entry_id)
    if entry is None:
        await query.answer("Voce non trovata (store).", show_alert=True)
        return

    if entry.status == STATUS_CLOUD:
        await query.answer("Già elaborata con Gemini.")
        return
    if entry.status == STATUS_PROCESSING:
        await query.answer("Elaborazione già in corso…")
        return

    await query.answer("Elaboro con Gemini…")
    try:
        await query.edit_message_text(
            text="⏳ Gemini in corso…",
            reply_markup=None,
        )
    except Exception:
        logging.exception("Failed to show processing state for %s", entry_id)

    # Non-blocking vs new voice messages: schedule and return.
    context.application.create_task(
        promote_entry(context, entry_id, answer_chat_id=entry.chat_id),
        update=update,
    )
