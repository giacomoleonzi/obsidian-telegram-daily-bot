#!/usr/bin/env python3
"""Application wiring for the Telegram bot."""

from __future__ import annotations

import asyncio
import logging

from telegram.ext import Application, CommandHandler, MessageHandler, filters

from bot.config import load_bot_config
from bot.handlers import (
    cmd_whoami,
    handle_application_error,
    handle_document,
    handle_image,
    handle_text,
    handle_voice,
)


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
    application.run_polling(timeout=60)
