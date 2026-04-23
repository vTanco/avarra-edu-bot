from __future__ import annotations

from datetime import datetime

from navarra_edu_bot.config.schema import ListEntry
from navarra_edu_bot.storage.models import Offer

_THURSDAY = 3  # Monday=0 ... Sunday=6
_WEEKDAYS = {0, 1, 2, 4}  # Mon, Tue, Wed, Fri — "closed" days


def is_eligible(
    offer: Offer,
    now: datetime,
    available_lists: list[ListEntry],
    thursday_open_specialties: list[ListEntry],
) -> bool:
    weekday = now.weekday()
    
    # Thursday: everything in the open list is eligible.
    if weekday == _THURSDAY:
        return _match_any(offer, thursday_open_specialties)
    
    # Friday before 08:30: the Thursday window is still open.
    if weekday == 4 and (now.hour < 8 or (now.hour == 8 and now.minute < 30)):
        return _match_any(offer, thursday_open_specialties)
        
    # Other working days: only your permanent lists.
    if weekday in _WEEKDAYS:
        return _match_any(offer, available_lists)
        
    return False


def _match_any(offer: Offer, entries: list[ListEntry]) -> bool:
    return any(
        e.body == offer.body and e.specialty.lower() == offer.specialty.lower() for e in entries
    )
