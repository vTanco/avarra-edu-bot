"""Capture HTML fixtures from the real portal for use in tests.

Run OUTSIDE the 13:30-14:00 window. Requires credentials in Keychain.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from navarra_edu_bot.config.keychain import read_secret

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
PORTAL_URL = "https://appseducacion.navarra.es/atp/index.xhtml"


async def main() -> None:
    username = read_secret("educa-username")
    password = read_secret("educa-password")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto(PORTAL_URL)
        (FIXTURES_DIR / "login_page.html").write_text(await page.content())

        # Click "Usuario Educa" — SELECTOR TBD by human on first run.
        print("Opened login page. Log in manually in the opened browser window.")
        print("Press Enter here once you are on the offers list page.")
        input()

        (FIXTURES_DIR / "offers_list.html").write_text(await page.content())

        print("Now navigate to a day with no offers (or trigger session expiry) and press Enter.")
        input()
        (FIXTURES_DIR / "offers_empty.html").write_text(await page.content())

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
