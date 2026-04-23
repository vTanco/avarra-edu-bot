import asyncio
import logging
from pathlib import Path
from datetime import datetime

from navarra_edu_bot.config.loader import load_config
from navarra_edu_bot.scraper.fetch import fetch_offers
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.telegram_bot.callbacks import build_callback_handler
from navarra_edu_bot.telegram_bot.client import build_bot_app
from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons
from navarra_edu_bot.cli import _keychain_read

logging.basicConfig(level=logging.INFO)

async def main():
    config_path = Path("~/.navarra-edu-bot/config.yaml").expanduser()
    cfg = load_config(config_path)

    storage = Storage(cfg.runtime.storage_path)
    
    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    app = build_bot_app(token=token, chat_id=chat_id)
    app.add_handler(build_callback_handler(storage))

    # Fetch offers
    offers = await fetch_offers(username=username, password=password, headless=True)
    
    async with app:
        # Force send all offers
        for offer in offers:
            logging.info(f"Force sending offer {offer.offer_id}")
            await app.bot.send_message(
                chat_id=chat_id,
                text=format_offer_message(offer),
                reply_markup=offer_buttons(offer),
                parse_mode="HTML",
            )
            
        logging.info("Messages sent! Waiting 60s for you to click 'Aplicar'...")
        await app.start()
        await app.updater.start_polling()
        await asyncio.sleep(60)
        await app.updater.stop()
        await app.stop()

if __name__ == "__main__":
    asyncio.run(main())
