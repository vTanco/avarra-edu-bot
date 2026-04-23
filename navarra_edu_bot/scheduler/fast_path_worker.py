from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from playwright.async_api import async_playwright

from navarra_edu_bot.scheduler.ntp_sync import get_ntp_offset, precise_sleep_until
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.scraper.apply import (
    ApplicationError,
    fire_submission,
    prewarm_application_context,
)
from navarra_edu_bot.scraper.login import login_educa

logger = logging.getLogger(__name__)


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
) -> int:
    """Run the Thursday fast-path:
      - Launch browser, login, prewarm page (navigate + fill + open modal).
      - precise_sleep_until(target_ts).
      - Fire submission with queue snapshot.
      - On any ApplicationError after fire, retry: relogin + prewarm + fire, up to max_retries.

    Returns the number of offers successfully submitted.
    """
    offer_ids = await queue.snapshot()
    if not offer_ids:
        logger.warning("fast_path: queue is empty, aborting")
        return 0

    ntp_offset = get_ntp_offset()
    logger.info(f"fast_path: starting with {len(offer_ids)} offers, ntp_offset={ntp_offset:.3f}s")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            attempt = 0
            prewarmed = False
            page = None
            while attempt < max_retries:
                attempt += 1
                try:
                    if not prewarmed:
                        context = await browser.new_context()
                        page = await context.new_page()
                        await login_educa(page, username=username, password=password)
                        await prewarm_application_context(
                            page, email=email, phone=phone, convid=convid,
                        )
                        prewarmed = True
                        logger.info(f"fast_path: prewarmed on attempt {attempt}")

                    if attempt == 1:
                        await precise_sleep_until(target_ts, ntp_offset=ntp_offset)

                    current_ids = await queue.snapshot()
                    if not current_ids:
                        logger.warning("fast_path: queue emptied before fire, aborting")
                        return 0

                    added = await fire_submission(page, offer_ids=current_ids)
                    logger.info(f"fast_path: submitted {added} offers on attempt {attempt}")
                    return added

                except ApplicationError as exc:
                    logger.warning(f"fast_path: attempt {attempt} failed: {exc}")
                    prewarmed = False
                    if attempt >= max_retries:
                        logger.error("fast_path: exhausted retries")
                        return 0
                    await asyncio.sleep(retry_backoff_s)
                except Exception as exc:
                    logger.exception(f"fast_path: unexpected error on attempt {attempt}: {exc}")
                    prewarmed = False
                    if attempt >= max_retries:
                        return 0
                    await asyncio.sleep(retry_backoff_s)
            return 0
        finally:
            await browser.close()
