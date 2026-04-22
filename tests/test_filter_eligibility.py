from datetime import datetime

from navarra_edu_bot.filter.eligibility import is_eligible
from navarra_edu_bot.config.schema import ListEntry
from navarra_edu_bot.storage.models import Offer


def _offer(body="0590", specialty="Tecnología") -> Offer:
    return Offer(
        offer_id="X",
        body=body,
        specialty=specialty,
        locality="Pamplona",
        center="IES",
        hours_per_week=20,
        duration="Curso",
        raw_html_hash="h",
        seen_at=datetime.now(),
    )


AVAILABLE = [ListEntry(body="0590", specialty="Tecnología", list_type="CONVOCATORIA")]
THURSDAY_OPEN = [
    ListEntry(body="0590", specialty="Tecnología"),
    ListEntry(body="0590", specialty="Matemáticas"),
]


def test_monday_only_available_lists():
    # 2026-04-20 is a Monday
    day = datetime(2026, 4, 20, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Matemáticas"), day, AVAILABLE, THURSDAY_OPEN) is False


def test_thursday_open_call():
    # 2026-04-23 is a Thursday
    day = datetime(2026, 4, 23, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Matemáticas"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Inglés"), day, AVAILABLE, THURSDAY_OPEN) is False


def test_saturday_never():
    day = datetime(2026, 4, 25, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is False
