from __future__ import annotations

from unicodedata import category, normalize

from navarra_edu_bot.storage.models import Offer

_FULL_TIME_HOURS = 18  # >= 18 h/week treated as full-time.


def rank_offers(
    offers: list[Offer],
    preferred_localities: list[str],
    specialty_order: list[str],
) -> list[Offer]:
    return sorted(offers, key=lambda o: _score(o, preferred_localities, specialty_order))


def _score(
    offer: Offer, preferred_localities: list[str], specialty_order: list[str]
) -> tuple[int, int, int]:
    # Lower score = higher rank.
    full_time_rank = 0 if offer.hours_per_week >= _FULL_TIME_HOURS else 1

    pref = _norm_list(preferred_localities)
    locality_rank = 0 if _norm(offer.locality) in pref else 1

    order = _norm_list(specialty_order)
    specialty = _norm(offer.specialty)
    specialty_rank = order.index(specialty) if specialty in order else len(order)

    return (full_time_rank, locality_rank, specialty_rank)


def _norm(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not category(c).startswith("M")).lower().strip()


def _norm_list(items: list[str]) -> list[str]:
    return [_norm(i) for i in items]
