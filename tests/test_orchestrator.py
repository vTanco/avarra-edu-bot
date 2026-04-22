from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from navarra_edu_bot.config.schema import AppConfig, ListEntry
from navarra_edu_bot.orchestrator import notify_new_offers
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer


def _offer(oid: str, specialty: str = "Tecnología", locality: str = "Pamplona") -> Offer:
    return Offer(
        offer_id=oid, body="0590", specialty=specialty, locality=locality,
        center="IES", hours_per_week=22, duration="Curso", raw_html_hash="h",
        seen_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_notify_new_offers_sends_only_eligible(tmp_path: Path, valid_config_dict: dict):
    storage = Storage(tmp_path / "s.db")
    storage.init_schema()

    cfg = AppConfig.model_validate(valid_config_dict)
    offers = [
        _offer("OK", specialty="Tecnología"),
        _offer("NO", specialty="Nuclear"),
    ]
    notifier = AsyncMock()

    # 2026-04-20 = Monday
    await notify_new_offers(
        offers=offers,
        now=datetime(2026, 4, 20, 13, 35),
        config=cfg,
        storage=storage,
        send=notifier,
    )

    sent_ids = [call.args[0].offer_id for call in notifier.await_args_list]
    assert sent_ids == ["OK"]
