from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue


@pytest.fixture
def fake_browser():
    """Returns (async_playwright_cm, browser, context, page) all as AsyncMocks."""
    page = AsyncMock()
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)
    pw = AsyncMock()
    pw.chromium = chromium
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=pw)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, browser, context, page


async def test_run_fast_path_succeeds_on_first_try(fake_browser):
    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=50)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()) as login, \
         patch(
             "navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context",
             new=AsyncMock(),
         ) as prewarm, \
         patch(
             "navarra_edu_bot.scheduler.fast_path_worker.fire_submission",
             new=AsyncMock(return_value=(["121776"], 1.5)),
         ) as fire, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added, elapsed = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=3,
        )

    assert len(added) == 1
    assert login.await_count == 1
    assert prewarm.await_count == 1
    assert fire.await_count == 1


async def test_run_fast_path_retries_on_fire_failure(fake_browser):
    from navarra_edu_bot.scraper.apply import ApplicationError

    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=20)

    fire_mock = AsyncMock(side_effect=[ApplicationError("boom"), ApplicationError("boom"), (["121776"], 1.5)])

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=fire_mock), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added, elapsed = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=5,
            retry_backoff_s=0.01,
        )

    assert len(added) == 1
    assert fire_mock.await_count == 3


async def test_run_fast_path_aborts_when_queue_empty(fake_browser):
    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    target = datetime.now() + timedelta(milliseconds=20)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()) as login, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()) as prewarm, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=AsyncMock()) as fire, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added, elapsed = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=3,
        )

    assert len(added) == 0
    assert login.await_count == 1
    assert prewarm.await_count == 1
    assert fire.await_count == 0


async def test_run_fast_path_gives_up_after_max_retries(fake_browser):
    from navarra_edu_bot.scraper.apply import ApplicationError

    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=10)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=AsyncMock(side_effect=ApplicationError("boom"))), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added, elapsed = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=2,
            retry_backoff_s=0.01,
        )

    assert len(added) == 0
