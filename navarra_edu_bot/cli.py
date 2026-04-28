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
    from navarra_edu_bot.filter.ranker import rank_offers as _rank_offers
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
    from navarra_edu_bot.scheduler.run_state import RunState
    from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
    from navarra_edu_bot.scraper.http_session import HttpSession
    from navarra_edu_bot.scraper.parser import (
        SessionExpiredError,
        discover_active_convid,
        is_convocatoria_ended,
        parse_applied_offer_ids,
        parse_offers,
    )
    from navarra_edu_bot.storage.db import Storage
    from navarra_edu_bot.telegram_bot.callbacks import (
        build_callback_handler,
        build_cancel_handler,
        build_queue_handler,
        build_status_handler,
    )
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
    state = RunState(queue=ThursdayQueue())

    def _rank_offer_ids(ids: list[str]) -> list[str]:
        """Order offer_ids by user preference using ranker.rank_offers."""
        offers = [o for o in (storage.get_offer(i) for i in ids) if o is not None]
        ranked = _rank_offers(
            offers,
            preferred_localities=cfg.user.preferred_localities,
            specialty_order=cfg.user.specialty_preference_order,
        )
        ranked_ids = [o.offer_id for o in ranked]
        # Append any unknown ids at the end so we don't silently drop them
        for i in ids:
            if i not in ranked_ids:
                ranked_ids.append(i)
        return ranked_ids

    async def _fetch_areapersonal_html() -> str:
        """GET areapersonal HTML. Refresh cookies on session expiry."""
        for attempt in range(2):
            try:
                return await http_session.fetch_areapersonal_html()
            except Exception as exc:
                if attempt == 0:
                    click.echo(f"http fetch failed ({exc}), refreshing session")
                    await http_session.refresh()
                else:
                    raise
        return ""

    async def _refresh_applied_today() -> None:
        """Fetch the user's solicitudes and update state.applied_today."""
        try:
            html = await http_session.fetch_solicitudes_html()
            ids = set(parse_applied_offer_ids(html))
            state.applied_today = ids
            click.echo(f"applied_today refreshed: {len(ids)} offer(s)")
        except Exception as exc:
            click.echo(f"applied_today refresh failed: {exc}")

    async def _poll_until(deadline: datetime, app) -> None:
        seen: set[str] = set()
        while datetime.now() < deadline:
            try:
                html = await _fetch_areapersonal_html()

                # Detect end of convocatoria → pause polling, notify once
                if is_convocatoria_ended(html):
                    if not state.convocatoria_ended:
                        state.convocatoria_ended = True
                        try:
                            await app.bot.send_message(
                                chat_id=chat_id,
                                text=(
                                    "⚠️ <b>Convocatoria finalizada</b>\n"
                                    "El portal indica que el plazo ha terminado. "
                                    "Pauso el polling hasta el siguiente ciclo."
                                ),
                                parse_mode="HTML",
                            )
                        except Exception:
                            pass
                    await asyncio.sleep(cfg.scheduler.poll_interval_seconds)
                    continue
                else:
                    state.convocatoria_ended = False

                # Auto-discover convid (used for non-Thursday immediate apply)
                convid_seen = discover_active_convid(html)
                if convid_seen and convid_seen != state.discovered_convid:
                    click.echo(f"discovered convid: {convid_seen}")
                    state.discovered_convid = convid_seen

                offers = parse_offers(html)
                state.last_poll_at = datetime.now()
                state.last_fetched_count = len(offers)

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
                    offers=offers,
                    now=datetime.now(),
                    config=cfg,
                    storage=storage,
                    send=_send,
                    applied_ids=state.applied_today,
                )
                click.echo(
                    f"poll ok @ {datetime.now().isoformat()} | "
                    f"fetched={len(offers)} sent={sent_count} convid={state.discovered_convid}"
                )
            except SessionExpiredError:
                click.echo("session expired, refreshing via Playwright")
                try:
                    await http_session.refresh()
                except Exception as exc:
                    click.echo(f"refresh failed: {exc}")
            except Exception as exc:
                click.echo(f"poll error: {exc}")
            await asyncio.sleep(cfg.scheduler.poll_interval_seconds)

    async def _verify_submitted(submitted: list[str]) -> tuple[list[str], list[str]]:
        """After a fast-path, fetch solicitudes again to check what actually landed.

        Returns (verified, missing) where verified are offer_ids that DID end up in
        the user's solicitudes, and missing are those that didn't.
        """
        try:
            html = await http_session.fetch_solicitudes_html()
            applied_now = set(parse_applied_offer_ids(html))
        except Exception as exc:
            click.echo(f"verify fetch failed: {exc}")
            return submitted, []  # assume everything went through
        verified = [oid for oid in submitted if oid in applied_now]
        missing = [oid for oid in submitted if oid not in applied_now]
        # Update state for /status etc.
        state.applied_today = applied_now
        return verified, missing

    async def _send_heartbeat(
        app,
        target_ts: datetime,
        submitted: list[str],
        verified: list[str],
        missing: list[str],
        elapsed_s: float,
        cycle_error: str | None = None,
    ) -> None:
        """Always-send heartbeat at end of cycle, summarising what happened."""
        lines = [
            f"💓 <b>Resumen del ciclo {target_ts.strftime('%Y-%m-%d %H:%M')}</b>",
            f"📊 Última poll: {state.last_fetched_count} ofertas detectadas",
            f"📋 Cola al disparo: {len(submitted)} solicitada(s)",
        ]
        if submitted:
            lines.append(f"⚡ Ráfaga: {len(submitted)} en {elapsed_s:.3f}s")
            if verified:
                vids = ", ".join(f"<code>{i}</code>" for i in verified)
                lines.append(f"✅ Confirmadas en solicitudes: {vids}")
            if missing:
                mids = ", ".join(f"<code>{i}</code>" for i in missing)
                lines.append(f"⚠️ Disparadas pero no confirmadas: {mids}")
        else:
            lines.append("(no había nada en cola — bot vivo y a la espera)")
        if cycle_error:
            lines.append(f"❌ Error: {cycle_error}")
        try:
            await app.bot.send_message(
                chat_id=chat_id, text="\n".join(lines), parse_mode="HTML"
            )
        except Exception as exc:
            click.echo(f"heartbeat send failed: {exc}")

    async def _run_one_cycle(app, target_ts: datetime) -> None:
        prewarm_start = target_ts - timedelta(seconds=prewarm_seconds_before)
        click.echo(
            f"Cycle target: {target_ts.isoformat()}  Prewarm start: {prewarm_start.isoformat()}"
        )

        await state.queue.drain()
        state.next_target_ts = target_ts

        # Refresh HTTP session and applied_today set at start of cycle.
        try:
            await http_session.refresh()
            await _refresh_applied_today()
        except Exception as exc:
            click.echo(f"cycle setup failed: {exc}")

        poll_task = asyncio.create_task(_poll_until(target_ts, app))

        now = datetime.now()
        if now < prewarm_start:
            wait_s = (prewarm_start - now).total_seconds()
            click.echo(f"Waiting {wait_s:.1f}s until prewarm...")
            await asyncio.sleep(wait_s)

        click.echo("Starting prewarm + fast-path...")
        cycle_error: str | None = None
        submitted: list[str] = []
        elapsed_s = 0.0
        # Use discovered convid if available, otherwise fall back to CLI flag.
        active_convid = state.discovered_convid or convid

        try:
            submitted, elapsed_s = await run_fast_path(
                queue=state.queue,
                target_ts=target_ts,
                username=username,
                password=password,
                email=email,
                phone=phone,
                convid=active_convid,
                max_retries=60,
                retry_backoff_s=1.0,
                headless=headless,
                rank_fn=_rank_offer_ids,
            )
            click.echo(f"fast-path submitted {len(submitted)} offers in {elapsed_s:.3f}s")
        except Exception as exc:
            cycle_error = str(exc)
            click.echo(f"fast-path error: {exc}")

        verified: list[str] = []
        missing: list[str] = []
        if submitted:
            verified, missing = await _verify_submitted(submitted)

        await _send_heartbeat(
            app, target_ts, submitted, verified, missing, elapsed_s, cycle_error
        )

        # Brief grace, then cancel polling task cleanly
        await asyncio.sleep(10)
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass

    async def _run() -> None:
        app = build_bot_app(token=token, chat_id=chat_id)
        app.add_handler(
            build_callback_handler(
                storage,
                thursday_queue=state.queue,
                run_state=state,
                apply_email=email,
                apply_phone=phone,
            )
        )
        app.add_handler(build_status_handler(state))
        app.add_handler(build_cancel_handler(state))
        app.add_handler(build_queue_handler(state))

        async with app:
            await app.start()
            await app.updater.start_polling()
            try:
                while True:
                    target_ts = compute_next_target(datetime.now(), target_hour, target_minute)
                    try:
                        await _run_one_cycle(app, target_ts)
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
