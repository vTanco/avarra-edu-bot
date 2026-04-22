from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from navarra_edu_bot.storage.models import Offer


def format_offer_message(offer: Offer) -> str:
    return (
        f"<b>{offer.specialty}</b> ({offer.body})\n"
        f"📍 {offer.locality} — {offer.center}\n"
        f"⏱ {offer.hours_per_week} h/semana · {offer.duration}\n"
        f"<code>{offer.offer_id}</code>"
    )


def offer_buttons(offer: Offer) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aplicar", callback_data=f"apply:{offer.offer_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"discard:{offer.offer_id}"),
            ]
        ]
    )
