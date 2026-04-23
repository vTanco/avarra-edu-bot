from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ApplicationError(RuntimeError):
    pass


async def prewarm_application_context(
    page: Page,
    *,
    email: str,
    phone: str,
    convid: str = "1204",
    timeout_ms: int = 15000,
) -> None:
    """Navigate to the new-application page, fill email/phone and open the offers modal.

    Leaves the page in a state ready to click 'anadirOfertaBtn' for any target offer.
    Assumes `page` is already authenticated via `login_educa`.
    """
    url = f"https://appseducacion.navarra.es/atp/private/solicitud.xhtml?convid={convid}&action=new"
    logger.info(f"prewarm: navigating to {url}")
    try:
        await page.goto(url, timeout=timeout_ms)
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("prewarm: could not navigate to solicitud.xhtml") from exc

    try:
        await page.fill("input[name='i10:inpEmail']", email, timeout=timeout_ms)
        await page.fill("input[name='i20:inpTfno1']", phone, timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("prewarm: could not fill email/phone") from exc

    try:
        await page.locator("a#elegirOfertasBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#ofertasDisponiblesDialog", state="visible", timeout=timeout_ms)
        await asyncio.sleep(2)
    except Exception as exc:
        raise ApplicationError("prewarm: could not open offers modal") from exc

    logger.info("prewarm: page ready, waiting for fire trigger")


async def fire_submission(
    page: Page,
    *,
    offer_ids: list[str],
    timeout_ms: int = 15000,
) -> int:
    """Click add buttons for target offers, then presentar + confirm.

    Returns the number of offers successfully added. Raises ApplicationError on any
    failure after the add phase (so caller can retry).
    """
    if not offer_ids:
        logger.warning("fire: no offer_ids, skipping")
        return 0

    added_count = 0
    rows = page.locator("#ofertasDisponiblesDtId_data > tr")
    row_count = await rows.count()

    for i in range(row_count):
        row = rows.nth(i)
        cells = row.locator("td")
        if await cells.count() <= 1:
            continue
        row_offer_id = (await cells.nth(1).inner_text()).strip()
        if row_offer_id not in offer_ids:
            continue
        add_btn = row.locator("a[id$=':anadirOfertaBtn']")
        if await add_btn.count() == 0:
            continue
        try:
            await add_btn.click(timeout=timeout_ms)
            added_count += 1
        except Exception as exc:
            logger.error(f"fire: failed to add {row_offer_id}: {exc}")

    if added_count == 0:
        raise ApplicationError(f"fire: none of {offer_ids} were addable")

    close_modal_btn = page.locator("#ofertasDisponiblesDialog button.close")
    if await close_modal_btn.count() > 0:
        await close_modal_btn.click()
        await asyncio.sleep(0.3)

    try:
        await page.locator("a#presentarSolicitudBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#presentarDlg", state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("fire: could not click presentar") from exc

    try:
        await page.locator("button#doSaveSolicitudBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#presentarDlg", state="hidden", timeout=timeout_ms)
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("fire: could not confirm") from exc

    logger.info(f"fire: submitted {added_count} offers")
    return added_count


async def apply_to_offers(
    page: Page,
    *,
    offer_ids: list[str],
    email: str,
    phone: str,
    convid: str = "1204",
    timeout_ms: int = 15000,
) -> None:
    """Backwards-compatible wrapper: prewarm + fire in sequence."""
    if not offer_ids:
        logger.info("No offers to apply to.")
        return
    await prewarm_application_context(
        page, email=email, phone=phone, convid=convid, timeout_ms=timeout_ms,
    )
    await fire_submission(page, offer_ids=offer_ids, timeout_ms=timeout_ms)


async def apply_single_offer_flow(
    offer_id: str, email: str, phone: str, convid: str = "1204",
) -> None:
    """Launch browser, login, apply to a single offer, close. Used by non-Thursday callbacks."""
    from playwright.async_api import async_playwright

    from navarra_edu_bot.config.keychain import read_secret
    from navarra_edu_bot.scraper.login import login_educa

    username = read_secret("educa-username")
    password = read_secret("educa-password")
    if not username or not password:
        raise ApplicationError("Credentials not found in keychain.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await login_educa(page, username=username, password=password)
            await apply_to_offers(
                page, offer_ids=[offer_id], email=email, phone=phone, convid=convid,
            )
        finally:
            await browser.close()
