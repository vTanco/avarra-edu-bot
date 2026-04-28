from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime
from typing import Callable, Optional

from playwright.async_api import async_playwright

from navarra_edu_bot.scheduler.ntp_sync import get_ntp_offset, precise_sleep_until
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.scraper.apply import (
    ApplicationError,
    fire_submission,
    prewarm_application_context,
)
from navarra_edu_bot.scraper.browser import _LOW_MEM_CHROMIUM_ARGS
from navarra_edu_bot.scraper.login import login_educa

logger = logging.getLogger(__name__)


async def _prep_context(
    browser,
    *,
    username: str,
    password: str,
    email: str,
    phone: str,
    convid: str,
) -> tuple:
    """Create an isolated context, login, and prewarm with fields filled + modal open.

    Returns (context, page). Caller is responsible for context.close().
    """
    ctx = await browser.new_context()
    page = await ctx.new_page()
    await login_educa(page, username=username, password=password)
    await prewarm_application_context(page, email=email, phone=phone, convid=convid)
    return ctx, page


async def _fire_after_target(
    page,
    offer_id: str,
    target_ts: datetime,
    ntp_offset: float,
    max_retries: int,
    retry_backoff_s: float,
) -> Optional[str]:
    """Wait until target_ts, then fire submission for the single offer_id.

    Returns the offer_id if submitted, None otherwise. Retries internal modal
    operations on transient failures.
    """
    await precise_sleep_until(target_ts, ntp_offset=ntp_offset)

    last_exc: Optional[Exception] = None
    for attempt in range(max_retries):
        try:
            start = time.monotonic()
            added, _elapsed = await fire_submission(
                page, offer_ids=[offer_id], start_time=start
            )
            if added:
                return added[0]
            return None
        except ApplicationError as exc:
            last_exc = exc
            logger.warning(f"fire {offer_id}: attempt {attempt + 1} failed: {exc}")
            await asyncio.sleep(retry_backoff_s)
    if last_exc:
        logger.error(f"fire {offer_id}: gave up after {max_retries} attempts: {last_exc}")
    return None


async def run_fast_path(
    *,
    queue: ThursdayQueue,
    target_ts: datetime,
    username: str,
    password: str,
    email: str,
    phone: str,
    convid: str = "1204",
    max_retries: int = 10,
    retry_backoff_s: float = 0.5,
    headless: bool = True,
    rank_fn: Optional[Callable[[list[str]], list[str]]] = None,
) -> tuple[list[str], float]:
    """Run the fast-path with parallel multi-context apply:

      - Snapshot the queue, optionally rank by user preference.
      - Launch a single Chromium with N isolated contexts (one per offer).
      - In each context: login + prewarm (page navigated, modal open).
      - At target_ts, every context fires its own offer in parallel.

    Returns (list_of_submitted_offer_ids, elapsed_seconds_from_target).
    """
    offer_ids = await queue.snapshot()
    if not offer_ids:
        logger.warning("fast_path: queue empty, aborting")
        return [], 0.0

    if rank_fn is not None:
        try:
            offer_ids = rank_fn(offer_ids)
            logger.info(f"fast_path: ranked offers -> {offer_ids}")
        except Exception as exc:
            logger.warning(f"fast_path: rank_fn failed, using FIFO order: {exc}")

    ntp_offset = get_ntp_offset()
    logger.info(
        f"fast_path: starting prewarm for {len(offer_ids)} offers in parallel, "
        f"ntp_offset={ntp_offset:.3f}s"
    )

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless, args=_LOW_MEM_CHROMIUM_ARGS)
        try:
            # Phase 1: prep all contexts in parallel
            prep_results = await asyncio.gather(
                *[
                    _prep_context(
                        browser,
                        username=username,
                        password=password,
                        email=email,
                        phone=phone,
                        convid=convid,
                    )
                    for _ in offer_ids
                ],
                return_exceptions=True,
            )

            # Filter successful preps
            ready: list[tuple[str, object]] = []  # (offer_id, page)
            contexts_to_close: list[object] = []
            for oid, result in zip(offer_ids, prep_results):
                if isinstance(result, Exception):
                    logger.error(f"prep {oid}: failed: {result}")
                    continue
                ctx, page = result
                contexts_to_close.append(ctx)
                ready.append((oid, page))

            if not ready:
                logger.error("fast_path: no contexts prepared, aborting")
                return [], 0.0

            logger.info(f"fast_path: {len(ready)}/{len(offer_ids)} contexts prewarmed")

            # Phase 2: every context waits for target_ts, then fires its offer
            start_global = time.monotonic()
            fire_results = await asyncio.gather(
                *[
                    _fire_after_target(
                        page,
                        oid,
                        target_ts,
                        ntp_offset,
                        max_retries,
                        retry_backoff_s,
                    )
                    for oid, page in ready
                ],
                return_exceptions=True,
            )
            elapsed = time.monotonic() - start_global

            submitted: list[str] = []
            for (oid, _page), result in zip(ready, fire_results):
                if isinstance(result, Exception):
                    logger.error(f"fire {oid}: exception: {result}")
                elif result:
                    submitted.append(result)

            logger.info(
                f"fast_path: submitted {len(submitted)}/{len(ready)} in {elapsed:.3f}s "
                f"-> {submitted}"
            )
            return submitted, elapsed
        finally:
            await browser.close()
