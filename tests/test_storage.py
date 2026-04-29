from datetime import datetime
from pathlib import Path

from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer


def _sample_offer(offer_id: str = "O1") -> Offer:
    return Offer(
        offer_id=offer_id,
        body="0590",
        specialty="Tecnología",
        locality="Pamplona",
        center="IES Example",
        hours_per_week=20,
        duration="Curso completo",
        raw_html_hash="abc",
        seen_at=datetime(2026, 4, 23, 13, 32),
    )


def test_storage_roundtrip(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()

    offer = _sample_offer()
    storage.upsert_offer(offer)

    loaded = storage.get_offer("O1")
    assert loaded is not None
    assert loaded.specialty == "Tecnología"


def test_storage_mark_preselected(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_sample_offer())

    storage.mark_preselected("O1", preselected=True)
    assert storage.is_preselected("O1") is True

    storage.mark_preselected("O1", preselected=False)
    assert storage.is_preselected("O1") is False


def test_storage_list_preselected_for_today(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_sample_offer("O1"))
    storage.upsert_offer(_sample_offer("O2"))
    storage.mark_preselected("O1", preselected=True)

    ids = storage.list_preselected_today(now=datetime.now())
    assert ids == ["O1"]


def test_storage_lists_only_todays_offers(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(
        Offer(
            offer_id="YESTERDAY",
            body="0590",
            specialty="Tecnología",
            locality="Pamplona",
            center="IES Example",
            hours_per_week=20,
            duration="Curso completo",
            raw_html_hash="abc",
            seen_at=datetime(2026, 4, 28, 13, 0),
        )
    )
    storage.upsert_offer(
        Offer(
            offer_id="TODAY-1",
            body="0590",
            specialty="Tecnología",
            locality="Pamplona",
            center="IES Example",
            hours_per_week=20,
            duration="Curso completo",
            raw_html_hash="def",
            seen_at=datetime(2026, 4, 29, 9, 0),
        )
    )
    storage.upsert_offer(
        Offer(
            offer_id="TODAY-2",
            body="0590",
            specialty="Tecnología",
            locality="Pamplona",
            center="IES Example",
            hours_per_week=20,
            duration="Curso completo",
            raw_html_hash="ghi",
            seen_at=datetime(2026, 4, 29, 10, 0),
        )
    )

    offers = storage.list_offers_seen_today(now=datetime(2026, 4, 29, 15, 0))

    assert [offer.offer_id for offer in offers] == ["TODAY-1", "TODAY-2"]


def test_storage_list_recent_decisions(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_sample_offer("O1"))
    storage.upsert_offer(_sample_offer("O2"))
    storage.mark_preselected("O1", preselected=True)
    storage.mark_preselected("O2", preselected=False)

    decisions = storage.list_recent_decisions(limit=5)

    assert len(decisions) == 2
    assert {item["offer_id"] for item in decisions} == {"O1", "O2"}
    assert {item["preselected"] for item in decisions} == {True, False}
