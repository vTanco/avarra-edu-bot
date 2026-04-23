from __future__ import annotations

import asyncio
import logging
from playwright.async_api import async_playwright
from navarra_edu_bot.config.keychain import read_secret
from navarra_edu_bot.scraper.login import login_educa

logging.basicConfig(level=logging.INFO)

async def debug():
    username = read_secret("educa-username")
    password = read_secret("educa-password")
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        await login_educa(page, username=username, password=password)
        
        # Navigate to application
        url = "https://appseducacion.navarra.es/atp/private/solicitud.xhtml?convid=1204&action=new"
        await page.goto(url)
        await page.wait_for_load_state("networkidle")
        
        # Check if email input exists
        exists = await page.locator("input[name='i10:inpEmail']").count()
        print(f"Email input exists: {exists}")
        if exists == 0:
            print("Capturing screenshot...")
            await page.screenshot(path="artifacts/error_page.png")
            print("HTML Snippet:", await page.content())
            
        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug())
