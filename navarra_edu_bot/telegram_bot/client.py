from __future__ import annotations

from telegram.ext import Application, ApplicationBuilder


def build_bot_app(token: str, chat_id: int) -> Application:
    if not token:
        raise ValueError("Telegram token is required")
    if not chat_id:
        raise ValueError("Telegram chat_id is required")
    return ApplicationBuilder().token(token).build()
