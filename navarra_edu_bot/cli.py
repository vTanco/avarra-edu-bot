import asyncio
import subprocess

import click


def _keychain_read(account: str) -> str:
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", "navarra-edu-bot", "-a", account, "-w"],
        text=True,
    ).strip()


@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """Navarra Edu Bot CLI."""
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.logging_config import configure_logging

    try:
        cfg = load_config(Path("~/.navarra-edu-bot/config.yaml").expanduser())
        configure_logging(cfg.runtime.log_path, cfg.runtime.log_level)
    except FileNotFoundError:
        # El comando ping no requiere config.
        pass


@main.command()
def ping() -> None:
    """Healthcheck ping."""
    click.echo("pong")


@main.command("ping-telegram")
def ping_telegram() -> None:
    """Send a test message to the configured Telegram chat."""
    from navarra_edu_bot.telegram_bot.client import build_bot_app

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    app = build_bot_app(token=token, chat_id=chat_id)

    async def _send() -> None:
        async with app:
            await app.bot.send_message(chat_id=chat_id, text="Hola desde Navarra Edu Bot ✅")

    asyncio.run(_send())
    click.echo("sent")


@main.command()
@click.option("--headless/--headed", default=True)
def fetch(headless: bool) -> None:
    """Login to Educa, fetch offers, print them. Does NOT apply."""
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    from navarra_edu_bot.scraper.fetch import fetch_offers

    offers = asyncio.run(fetch_offers(username=username, password=password, headless=headless))
    click.echo(f"Found {len(offers)} offers:")
    for o in offers:
        click.echo(
            f"  [{o.body}] {o.specialty} @ {o.locality} — {o.center} "
            f"({o.hours_per_week}h, {o.duration})"
        )


@main.command("run-once")
@click.option("--headless/--headed", default=True)
def run_once(headless: bool) -> None:
    """Execute one complete cycle: fetch, filter, notify (NO apply)."""
    from datetime import datetime
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scraper.fetch import fetch_offers
    from navarra_edu_bot.storage.db import Storage
    from navarra_edu_bot.telegram_bot.callbacks import build_callback_handler
    from navarra_edu_bot.telegram_bot.client import build_bot_app
    from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

    config_path = Path("~/.navarra-edu-bot/config.yaml").expanduser()
    cfg = load_config(config_path)

    storage = Storage(cfg.runtime.storage_path)
    storage.init_schema()

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    app = build_bot_app(token=token, chat_id=chat_id)
    app.add_handler(build_callback_handler(storage))

    async def _run() -> None:
        offers = await fetch_offers(username=username, password=password, headless=headless)

        async with app:
            async def _send(offer):
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=format_offer_message(offer),
                    reply_markup=offer_buttons(offer),
                    parse_mode="HTML",
                )

            await notify_new_offers(
                offers=offers,
                now=datetime.now(),
                config=cfg,
                storage=storage,
                send=_send,
            )
            # Keep polling for callbacks for 60 s to capture user presses.
            await app.start()
            await app.updater.start_polling()
            await asyncio.sleep(60)
            await app.updater.stop()
            await app.stop()

    asyncio.run(_run())
    from datetime import datetime as dt

    click.echo(
        f"run-once complete. Pre-selected today: "
        f"{storage.list_preselected_today(now=dt.now())}"
    )


if __name__ == "__main__":
    main()
