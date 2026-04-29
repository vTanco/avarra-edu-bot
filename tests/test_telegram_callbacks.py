from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest

from navarra_edu_bot.scheduler.run_state import RunState
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer
from navarra_edu_bot.telegram_bot.callbacks import (
    build_apply_command_handler,
    build_discard_command_handler,
    build_mute_handler,
    build_offer_handler,
    build_pause_handler,
    build_resume_handler,
    build_today_handler,
)


def _offer(offer_id: str, seen_at: datetime) -> Offer:
    return Offer(
        offer_id=offer_id,
        body="0590",
        specialty="Tecnología",
        locality="Pamplona",
        center="IES Example",
        hours_per_week=22,
        duration="Curso completo",
        raw_html_hash=f"h-{offer_id}",
        seen_at=seen_at,
    )


@pytest.mark.asyncio
async def test_today_handler_replays_todays_offers_with_buttons(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_offer("DISC", datetime.now().replace(hour=9, minute=0)))
    storage.upsert_offer(_offer("APPL", datetime.now().replace(hour=10, minute=0)))
    storage.mark_preselected("DISC", preselected=False)

    state = RunState(queue=ThursdayQueue(), applied_today={"APPL"})
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=[])

    handler = build_today_handler(storage, state)
    await handler.callback(update, context)

    message.reply_text.assert_awaited_once()
    assert message.reply_html.await_count == 2

    first_text = message.reply_html.await_args_list[0].args[0]
    second_text = message.reply_html.await_args_list[1].args[0]

    assert "❌ <b>Estado actual:</b> descartada" in first_text
    assert "✅ <b>Estado actual:</b> ya aplicada hoy" in second_text
    assert message.reply_html.await_args_list[0].kwargs["reply_markup"] is not None
    assert message.reply_html.await_args_list[1].kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_today_handler_reports_empty_day(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    state = RunState(queue=ThursdayQueue())
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=[])

    handler = build_today_handler(storage, state)
    await handler.callback(update, context)

    message.reply_text.assert_awaited_once_with("No hay ofertas registradas hoy.")
    message.reply_html.assert_not_awaited()


@pytest.mark.asyncio
async def test_offer_handler_replays_one_offer_with_status(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_offer("OFFER1", datetime.now()))
    storage.mark_preselected("OFFER1", preselected=True)

    state = RunState(queue=ThursdayQueue())
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(message=message)
    context = SimpleNamespace(args=["OFFER1"])

    handler = build_offer_handler(storage, state)
    await handler.callback(update, context)

    message.reply_html.assert_awaited_once()
    payload = message.reply_html.await_args.args[0]
    assert "OFFER1" in payload
    assert "marcada para aplicar" in payload
    assert message.reply_html.await_args.kwargs["reply_markup"] is not None


@pytest.mark.asyncio
async def test_apply_and_discard_commands_manage_queue(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_offer("Q1", datetime.now()))
    state = RunState(queue=ThursdayQueue())
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(message=message)

    class _FakeThursday(datetime):
        @classmethod
        def now(cls):
            return cls(2026, 4, 30, 13, 30, 0)

    with patch("navarra_edu_bot.telegram_bot.callbacks.datetime", _FakeThursday):
        apply_handler = build_apply_command_handler(
            storage,
            state,
            apply_email="x@example.com",
            apply_phone="600000000",
        )
        await apply_handler.callback(update, SimpleNamespace(args=["Q1"]))

    assert await state.queue.snapshot() == ["Q1"]
    assert storage.get_preselected_decision("Q1") is True
    message.reply_html.assert_awaited_once()

    discard_handler = build_discard_command_handler(storage, state)
    await discard_handler.callback(update, SimpleNamespace(args=["Q1"]))

    assert await state.queue.snapshot() == []
    assert storage.get_preselected_decision("Q1") is False
    assert message.reply_text.await_count >= 1


@pytest.mark.asyncio
async def test_pause_mute_and_resume_handlers_update_run_state():
    state = RunState(queue=ThursdayQueue())
    message = SimpleNamespace(reply_text=AsyncMock(), reply_html=AsyncMock())
    update = SimpleNamespace(message=message)

    pause_handler = build_pause_handler(state)
    await pause_handler.callback(update, SimpleNamespace(args=[]))
    assert state.paused is True

    mute_handler = build_mute_handler(state)
    await mute_handler.callback(update, SimpleNamespace(args=["30"]))
    assert state.is_muted() is True

    resume_handler = build_resume_handler(state)
    await resume_handler.callback(update, SimpleNamespace(args=[]))
    assert state.paused is False
    assert state.muted_until is None
