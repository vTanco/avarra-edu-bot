"""Dry-run del flujo fast-path jueves (sin submit final).

Uso:
    uv run python scripts/test_fast_path_dry.py <offer_id>

Lo que hace:
    1. Login headed (visible).
    2. prewarm_application_context (navega, rellena, abre modal).
    3. Espera 3 segundos.
    4. fire_submission MODIFICADO: sólo clicks anadir + presentar. NO confirma.
    5. Deja el browser abierto 15 segundos para inspección visual.
"""
from __future__ import annotations

import asyncio
import logging
import os
import sys

from playwright.async_api import async_playwright

from navarra_edu_bot.config.keychain import read_secret
from navarra_edu_bot.scraper.apply import prewarm_application_context
from navarra_edu_bot.scraper.login import login_educa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main(offer_id: str, convid: str = "1205") -> None:
    username = read_secret("educa-username")
    password = read_secret("educa-password")
    if not username or not password:
        logger.error("Missing credentials in keychain")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await login_educa(page, username=username, password=password)
            email = os.environ.get("APPLY_EMAIL")
            phone = os.environ.get("APPLY_PHONE")
            if not email or not phone:
                logger.error("Set APPLY_EMAIL and APPLY_PHONE env vars before running.")
                sys.exit(1)
            await prewarm_application_context(
                page,
                email=email,
                phone=phone,
                convid=convid,
            )
            logger.info("Prewarm OK. Waiting 3s to simulate trigger delay.")
            await asyncio.sleep(3)

            rows = page.locator("#ofertasDisponiblesDtId_data > tr")
            row_count = await rows.count()
            clicked = False
            for i in range(row_count):
                cells = rows.nth(i).locator("td")
                if await cells.count() <= 1:
                    continue
                row_id = (await cells.nth(1).inner_text()).strip()
                if row_id == offer_id:
                    add_btn = rows.nth(i).locator("a[id$=':anadirOfertaBtn']")
                    if await add_btn.count() > 0:
                        await add_btn.click()
                        clicked = True
                        break
            if not clicked:
                logger.warning(f"Offer {offer_id} not found in modal")
            else:
                logger.info(f"Added offer {offer_id}. STOPPING HERE (no presentar, no confirm).")

            logger.info("Keeping browser open 15s for visual inspection.")
            await asyncio.sleep(15)
        finally:
            await browser.close()


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/test_fast_path_dry.py <offer_id> [convid]")
        sys.exit(1)
    offer_id = sys.argv[1]
    convid = sys.argv[2] if len(sys.argv) > 2 else "1205"
    asyncio.run(main(offer_id, convid))
