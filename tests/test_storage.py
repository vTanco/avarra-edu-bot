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
