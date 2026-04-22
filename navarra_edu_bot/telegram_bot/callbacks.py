from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from navarra_edu_bot.storage.db import Storage

log = structlog.get_logger()


def build_callback_handler(storage: Storage) -> CallbackQueryHandler:
    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()

        try:
            action, offer_id = query.data.split(":", 1)
        except ValueError:
            log.warning("bad_callback_data", data=query.data)
            return

        if action == "apply":
            storage.mark_preselected(offer_id, preselected=True)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text(
                f"{query.message.text_html}\n\n✅ <b>Pre-seleccionada</b>", parse_mode="HTML"
            )
        elif action == "discard":
            storage.mark_preselected(offer_id, preselected=False)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text(
                f"{query.message.text_html}\n\n❌ Descartada", parse_mode="HTML"
            )
        else:
            log.warning("unknown_action", action=action)

    return CallbackQueryHandler(_handle)
