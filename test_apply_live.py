import asyncio
import logging
import sys
from playwright.async_api import async_playwright

from navarra_edu_bot.scraper.login import login_educa
from navarra_edu_bot.scraper.apply import apply_to_offers
from navarra_edu_bot.config.keychain import read_secret

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def main():
    username = read_secret('educa-username')
    password = read_secret('educa-password')
    
    if not username or not password:
        logger.error("Credentials not found in keychain.")
        sys.exit(1)

    # We use headed mode so you can see it live
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context()
        page = await context.new_page()

        try:
            logger.info("Logging in...")
            await login_educa(page, username=username, password=password)
            logger.info("Logged in successfully.")

            logger.info("Applying to offer 121776...")
            # Using the email and phone from your previous session context
            await apply_to_offers(
                page, 
                offer_ids=["121776"], 
                email="vicente.tanco@edu.uah.es", 
                phone="681864143"
            )
            logger.info("Application process completed!")
            
            # Wait a few seconds so the user can see the final state
            await asyncio.sleep(5)
            
        except Exception as e:
            logger.error(f"Error during application: {e}")
            await asyncio.sleep(10) # wait before closing so user can see the error
        finally:
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
