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


@main.command("run-thursday")
@click.option("--headless/--headed", default=True)
@click.option("--target-hour", default=14, type=int, help="Hora objetivo (default 14)")
@click.option("--target-minute", default=0, type=int, help="Minuto objetivo (default 0)")
@click.option("--prewarm-seconds-before", default=300, type=int,
              help="Segundos antes del target para iniciar prewarm (default 300 = 5min)")
@click.option("--convid", default="1204")
@click.option("--email", default="vicente.tanco@edu.uah.es")
@click.option("--phone", default="681864143")
def run_thursday(
    headless: bool,
    target_hour: int,
    target_minute: int,
    prewarm_seconds_before: int,
    convid: str,
    email: str,
    phone: str,
) -> None:
    """Thursday fast-path: poll + notify 13:30-14:00, prewarm at 13:55, fire at 14:00."""
    from datetime import datetime, timedelta
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
    from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
    from navarra_edu_bot.scraper.fetch import fetch_offers
    from navarra_edu_bot.storage.db import Storage
    from navarra_edu_bot.telegram_bot.callbacks import build_callback_handler
    from navarra_edu_bot.telegram_bot.client import build_bot_app
    from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

    cfg = load_config(Path("~/.navarra-edu-bot/config.yaml").expanduser())
    storage = Storage(cfg.runtime.storage_path)
    storage.init_schema()

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    queue = ThursdayQueue()
    app = build_bot_app(token=token, chat_id=chat_id)
    app.add_handler(build_callback_handler(storage, thursday_queue=queue))

    now = datetime.now()
    target_ts = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target_ts <= now:
        target_ts = target_ts + timedelta(days=1)
    prewarm_start = target_ts - timedelta(seconds=prewarm_seconds_before)

    click.echo(f"Target: {target_ts.isoformat()}  Prewarm start: {prewarm_start.isoformat()}")

    async def _poll_until(deadline: datetime) -> None:
        seen: set[str] = set()
        while datetime.now() < deadline:
            try:
                offers = await fetch_offers(
                    username=username, password=password, headless=headless,
                )
                async def _send(offer):
                    if offer.offer_id in seen:
                        return
                    seen.add(offer.offer_id)
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=format_offer_message(offer),
                        reply_markup=offer_buttons(offer),
                        parse_mode="HTML",
                    )
                await notify_new_offers(
                    offers=offers, now=datetime.now(), config=cfg,
                    storage=storage, send=_send,
                )
            except Exception as exc:
                click.echo(f"poll error: {exc}")
            await asyncio.sleep(60)

    async def _run() -> None:
        async with app:
            await app.start()
            await app.updater.start_polling()
            try:
                # Polling in background until target_ts
                poll_task = asyncio.create_task(_poll_until(target_ts))

                now = datetime.now()
                if now < prewarm_start:
                    wait_s = (prewarm_start - now).total_seconds()
                    click.echo(f"Waiting {wait_s:.1f}s until prewarm...")
                    await asyncio.sleep(wait_s)

                click.echo("Starting prewarm + fast-path...")
                submitted, elapsed_s = await run_fast_path(
                    queue=queue,
                    target_ts=target_ts,
                    username=username,
                    password=password,
                    email=email,
                    phone=phone,
                    convid=convid,
                    max_retries=60,
                    retry_backoff_s=1.0,
                    headless=headless,
                )
                click.echo(f"fast-path submitted {len(submitted)} offers in {elapsed_s:.3f}s")
                
                if submitted:
                    details = []
                    for oid in submitted:
                        offer = storage.get_offer(oid)
                        if offer:
                            details.append(f"• <code>{oid}</code>: {offer.specialty} ({offer.locality})")
                        else:
                            details.append(f"• <code>{oid}</code>")
                    offers_str = "\n".join(details)
                    
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=(
                            f"✅ <b>Ráfaga del jueves completada</b>\n\n"
                            f"Se han presentado {len(submitted)} solicitudes en <b>{elapsed_s:.3f} segundos</b> desde la apertura de las 14:00.\n\n"
                            f"<b>Ofertas aplicadas:</b>\n{offers_str}"
                        ),
                        parse_mode="HTML"
                    )

                await asyncio.sleep(10)
                poll_task.cancel()
            finally:
                await app.updater.stop()
                await app.stop()

    asyncio.run(_run())


if __name__ == "__main__":
    main()
