#!/usr/bin/env python3
"""Application wiring for the Telegram bot."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from telegram.ext import Application, CallbackQueryHandler, CommandHandler, MessageHandler, filters

from bot.callbacks import handle_gemini_callback
from bot.config import load_bot_config
from bot.handlers import (
    cmd_g,
    cmd_pending,
    cmd_whoami,
    handle_application_error,
    handle_document,
    handle_image,
    handle_text,
    handle_voice,
)
from bot.store import EntryStore


def main() -> None:
    """Load config, register handlers, and start long polling."""
    config = load_bot_config()
    log_level_name = str(config["log_level"])
    log_level_value = logging.getLevelNamesMapping()[log_level_name]
    logging.basicConfig(
        level=log_level_value,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logging.getLogger("telegram").setLevel(logging.WARNING)
    logging.getLogger("httpx").setLevel(logging.WARNING)

    state_db_path = Path(str(config["state_db_path"]))
    entry_store = EntryStore(state_db_path)

    async def post_shutdown(application: Application) -> None:
        store = application.bot_data.get("entry_store")
        if isinstance(store, EntryStore):
            store.close()

    application = (
        Application.builder()
        .token(str(config["token"]))
        .post_shutdown(post_shutdown)
        .build()
    )
    application.bot_data.update(config)
    application.bot_data["note_lock"] = asyncio.Lock()
    application.bot_data["entry_store"] = entry_store

    application.add_handler(CommandHandler("whoami", cmd_whoami))
    application.add_handler(CommandHandler("g", cmd_g))
    application.add_handler(CommandHandler("pending", cmd_pending))
    application.add_handler(CallbackQueryHandler(handle_gemini_callback, pattern=r"^g:"))
    application.add_handler(MessageHandler(filters.VOICE, handle_voice))
    application.add_handler(MessageHandler(filters.PHOTO | filters.Document.IMAGE, handle_image))
    application.add_handler(MessageHandler(filters.Document.ALL & ~filters.Document.IMAGE, handle_document))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))
    application.add_error_handler(handle_application_error)

    gemini_enabled = bool(str(config.get("gemini_api_key") or "").strip())
    logging.info(
        "Telegram bot started - daily_dir=%s stt_provider=%s gemini_opt_in=%s "
        "state_db=%s timezone=%s authorized_chat_id=%s",
        config["daily_dir"],
        config["stt_provider"],
        gemini_enabled,
        state_db_path,
        config["timezone_name"],
        config["authorized_chat_id"],
    )
    application.run_polling(timeout=60)
