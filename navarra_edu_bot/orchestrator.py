from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable

from navarra_edu_bot.config.schema import AppConfig
from navarra_edu_bot.filter.eligibility import is_eligible
from navarra_edu_bot.filter.ranker import rank_offers
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer

Sender = Callable[[Offer], Awaitable[None]]


async def notify_new_offers(
    *,
    offers: list[Offer],
    now: datetime,
    config: AppConfig,
    storage: Storage,
    send: Sender,
) -> int:
    eligible = [
        o
        for o in offers
        if is_eligible(o, now, config.available_lists, config.thursday_open_specialties)
    ]
    ranked = rank_offers(
        eligible,
        preferred_localities=config.user.preferred_localities,
        specialty_order=config.user.specialty_preference_order,
    )
    sent = 0
    for offer in ranked:
        if storage.get_offer(offer.offer_id) is not None:
            continue  # ya notificada previamente
        storage.upsert_offer(offer)
        await send(offer)
        sent += 1
    return sent
