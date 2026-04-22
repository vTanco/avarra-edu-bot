from datetime import datetime

from navarra_edu_bot.filter.ranker import rank_offers
from navarra_edu_bot.storage.models import Offer


def _offer(*, specialty="Tecnología", locality="Pamplona", hours=20) -> Offer:
    return Offer(
        offer_id=f"{specialty}-{locality}-{hours}",
        body="0590",
        specialty=specialty,
        locality=locality,
        center="IES",
        hours_per_week=hours,
        duration="Curso",
        raw_html_hash="h",
        seen_at=datetime.now(),
    )


PREFERRED_LOCALITIES = ["Pamplona", "Orkoien", "Barañáin"]
SPECIALTY_ORDER = ["Tecnología", "Matemáticas", "Dibujo"]


def test_full_time_ranks_higher_than_part_time():
    offers = [
        _offer(hours=10),
        _offer(hours=22),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert ranked[0].hours_per_week == 22


def test_preferred_locality_ranks_higher():
    offers = [
        _offer(locality="Tudela"),
        _offer(locality="Pamplona"),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert ranked[0].locality == "Pamplona"


def test_specialty_order_tiebreak():
    offers = [
        _offer(specialty="Dibujo"),
        _offer(specialty="Tecnología"),
        _offer(specialty="Matemáticas"),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert [o.specialty for o in ranked] == ["Tecnología", "Matemáticas", "Dibujo"]
