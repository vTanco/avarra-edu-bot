from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


@asynccontextmanager
async def browser_context(
    *, headless: bool = True, user_agent: str | None = None
) -> AsyncIterator[tuple[Browser, BrowserContext, Page]]:
    ua = user_agent or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(user_agent=ua)
        page = await ctx.new_page()
        try:
            yield browser, ctx, page
        finally:
            await browser.close()
