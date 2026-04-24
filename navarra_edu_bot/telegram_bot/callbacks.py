from __future__ import annotations

from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.storage.db import Storage

log = structlog.get_logger()


def build_callback_handler(
    storage: Storage,
    thursday_queue: ThursdayQueue | None = None,
) -> CallbackQueryHandler:
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

            is_thursday = datetime.now().weekday() == 3
            if is_thursday and thursday_queue is not None:
                await thursday_queue.add(offer_id)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n⏳ <b>Encolada para las 14:00</b>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
                log.info("thursday_queued", offer_id=offer_id)
                return

            await query.edit_message_text(
                f"{query.message.text_html}\n\n⏳ <b>Aplicando...</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
            import time
            click_time = time.monotonic()
            
            try:
                from navarra_edu_bot.scraper.apply import apply_single_offer_flow
                added_offers, true_latency = await apply_single_offer_flow(
                    offer_id=offer_id,
                    email="vicente.tanco@edu.uah.es",
                    phone="681864143",
                    convid="1206",
                )
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n✅ <b>Solicitud Presentada</b> (Tardó {true_latency:.2f} segundos)",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as e:
                elapsed = time.monotonic() - click_time
                log.error("apply_failed", error=str(e), elapsed_s=elapsed)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n❌ <b>Error al aplicar</b> tras {elapsed:.2f}s: {e}",
                    parse_mode="HTML",
                    reply_markup=None,
                )
        elif action == "discard":
            storage.mark_preselected(offer_id, preselected=False)
            await query.edit_message_text(
                f"{query.message.text_html}\n\n❌ Descartada",
                parse_mode="HTML",
                reply_markup=None,
            )
        else:
            log.warning("unknown_action", action=action)

    return CallbackQueryHandler(_handle)
