from __future__ import annotations

import asyncio
import logging
import re
from playwright.async_api import async_playwright
from navarra_edu_bot.config.keychain import read_secret
from navarra_edu_bot.scraper.login import login_educa

logging.basicConfig(level=logging.INFO)

async def find_convid():
    username = read_secret("educa-username")
    password = read_secret("educa-password")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await login_educa(page, username=username, password=password)
        
        # Navigate to area personal and find the 'Nueva solicitud' link
        await page.goto("https://appseducacion.navarra.es/atp/auth/areapersonal.xhtml")
        await page.wait_for_load_state("networkidle")
        
        # The link should have text 'Nueva solicitud'
        link = page.locator("a:has-text('Nueva solicitud')").first
        if await link.count() > 0:
            href = await link.get_attribute("href")
            print(f"Found Nueva Solicitud link: {href}")
            match = re.search(r'convid=(\d+)', href)
            if match:
                print(f"Extracted convid: {match.group(1)}")
            else:
                print("Could not extract convid from href.")
        else:
            print("No 'Nueva solicitud' link found on the page.")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(find_convid())
