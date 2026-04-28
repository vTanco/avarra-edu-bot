import asyncio
import subprocess

import click


def _keychain_read(account: str) -> str:
    from navarra_edu_bot.config.keychain import read_secret
    return read_secret(account)


def compute_next_target(now, target_hour: int, target_minute: int):
    from datetime import timedelta

    target = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target <= now:
        target = target + timedelta(days=1)
    return target


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
    """Daily fast-path loop: each day, poll + notify before target hour, prewarm + fire at target.

    Runs forever in a loop. After each cycle (which ends just after target hour), it recomputes
    the next target (tomorrow at target_hour) and continues. The Telegram app is kept alive
    across cycles. Designed to survive container lifetime — does not depend on Docker restart.
    """
    from datetime import datetime, timedelta
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
    from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
    from navarra_edu_bot.scraper.http_session import HttpSession
    from navarra_edu_bot.scraper.parser import SessionExpiredError, parse_offers
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

    http_session = HttpSession(username=username, password=password, headless=headless)

    async def _fetch_offers_via_http() -> list:
        """Fetch offers via HTTP. Refresh cookies on session expiry, retry once."""
        for attempt in range(2):
            try:
                html = await http_session.fetch_areapersonal_html()
                return parse_offers(html)
            except SessionExpiredError:
                click.echo("session expired, refreshing via Playwright")
                await http_session.refresh()
            except Exception:
                if attempt == 0:
                    # Network blip or first call before refresh — try refresh once
                    click.echo("http fetch failed, refreshing session")
                    await http_session.refresh()
                else:
                    raise
        return []

    async def _poll_until(deadline: datetime, app, seen: set[str]) -> None:
        while datetime.now() < deadline:
            try:
                offers = await _fetch_offers_via_http()
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
                sent_count = await notify_new_offers(
                    offers=offers, now=datetime.now(), config=cfg,
                    storage=storage, send=_send,
                )
                click.echo(
                    f"poll ok @ {datetime.now().isoformat()} | fetched={len(offers)} sent={sent_count}"
                )
            except Exception as exc:
                click.echo(f"poll error: {exc}")
            await asyncio.sleep(cfg.scheduler.poll_interval_seconds)

    async def _run_one_cycle(queue: ThursdayQueue, app, target_ts: datetime) -> None:
        prewarm_start = target_ts - timedelta(seconds=prewarm_seconds_before)
        click.echo(
            f"Cycle target: {target_ts.isoformat()}  Prewarm start: {prewarm_start.isoformat()}"
        )

        # Reset queue and seen-set at the start of each cycle
        await queue.drain()
        seen: set[str] = set()

        # Refresh HTTP session cookies at the start of each cycle (one Playwright
        # login per day; subsequent polls reuse the cookies via aiohttp).
        try:
            await http_session.refresh()
        except Exception as exc:
            click.echo(f"http_session refresh failed: {exc}")

        # Poll in background until target_ts
        poll_task = asyncio.create_task(_poll_until(target_ts, app, seen))

        now = datetime.now()
        if now < prewarm_start:
            wait_s = (prewarm_start - now).total_seconds()
            click.echo(f"Waiting {wait_s:.1f}s until prewarm...")
            await asyncio.sleep(wait_s)

        click.echo("Starting prewarm + fast-path...")
        try:
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
                        details.append(
                            f"• <code>{oid}</code>: {offer.specialty} ({offer.locality})"
                        )
                    else:
                        details.append(f"• <code>{oid}</code>")
                offers_str = "\n".join(details)

                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"✅ <b>Ráfaga completada</b>\n\n"
                        f"Se han presentado {len(submitted)} solicitudes en "
                        f"<b>{elapsed_s:.3f} segundos</b> desde la apertura de las "
                        f"{target_hour:02d}:{target_minute:02d}.\n\n"
                        f"<b>Ofertas aplicadas:</b>\n{offers_str}"
                    ),
                    parse_mode="HTML",
                )
        except Exception as exc:
            click.echo(f"fast-path error: {exc}")
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=f"⚠️ Error en la ráfaga de las {target_hour:02d}:{target_minute:02d}: {exc}",
                )
            except Exception:
                pass

        # Brief grace, then cancel polling task cleanly
        await asyncio.sleep(10)
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass

    async def _run() -> None:
        queue = ThursdayQueue()
        app = build_bot_app(token=token, chat_id=chat_id)
        app.add_handler(build_callback_handler(storage, thursday_queue=queue))

        async with app:
            await app.start()
            await app.updater.start_polling()
            try:
                while True:
                    target_ts = compute_next_target(datetime.now(), target_hour, target_minute)
                    try:
                        await _run_one_cycle(queue, app, target_ts)
                    except Exception as exc:
                        click.echo(f"cycle error: {exc}")
                        # Notify and continue to next day rather than crashing the loop
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id,
                                text=f"⚠️ Error en ciclo diario: {exc}",
                            )
                        except Exception:
                            pass
                    # Small pause before computing next target (avoids tight loop on edge case)
                    await asyncio.sleep(60)
            finally:
                try:
                    await http_session.close()
                except Exception:
                    pass
                try:
                    await app.updater.stop()
                except Exception:
                    pass
                try:
                    await app.stop()
                except Exception:
                    pass

    asyncio.run(_run())


if __name__ == "__main__":
    main()
