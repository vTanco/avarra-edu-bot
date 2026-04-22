from __future__ import annotations

from navarra_edu_bot.scraper.browser import browser_context
from navarra_edu_bot.scraper.login import login_educa
from navarra_edu_bot.scraper.parser import parse_offers
from navarra_edu_bot.storage.models import Offer

OFFERS_PAGE_PATH = "/atp/index.xhtml"  # Same page post-login in most cases; adjust.


async def fetch_offers(
    *, username: str, password: str, headless: bool = True
) -> list[Offer]:
    async with browser_context(headless=headless) as (_browser, _ctx, page):
        await login_educa(page, username=username, password=password)
        # Assumes after login the offers page is the current page.
        html = await page.content()
    return parse_offers(html)
