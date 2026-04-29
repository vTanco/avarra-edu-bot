import asyncio
import os
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
@click.option(
    "--email",
    default=lambda: os.environ.get("APPLY_EMAIL", ""),
    help="Email to fill in the application form. Defaults to $APPLY_EMAIL.",
)
@click.option(
    "--phone",
    default=lambda: os.environ.get("APPLY_PHONE", ""),
    help="Phone to fill in the application form. Defaults to $APPLY_PHONE.",
)
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

    Email and phone for the application form must be supplied via --email/--phone or via
    the APPLY_EMAIL / APPLY_PHONE environment variables.
    """
    if not email or not phone:
        raise click.UsageError(
            "Missing email/phone. Set APPLY_EMAIL and APPLY_PHONE env vars "
            "(or pass --email and --phone flags)."
        )
    from datetime import datetime, timedelta
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.diagnostics.backup import daily_backup
    from navarra_edu_bot.diagnostics.canary import (
        run_fastpath_canary,
        run_polling_canary,
    )
    from navarra_edu_bot.diagnostics.healthcheck import (
        ping_fail,
        ping_start,
        ping_success,
    )
    from navarra_edu_bot.diagnostics.snapshot import capture_failure
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
        build_apply_command_handler,
        build_callback_handler,
        build_cancel_handler,
        build_discard_command_handler,
        build_dryrun_handler,
        build_filters_handler,
        build_health_handler,
        build_help_handler,
        build_history_handler,
        build_logs_handler,
        build_mute_handler,
        build_mute_until_handler,
        build_next_handler,
        build_offer_handler,
        build_pause_handler,
        build_poll_handler,
        build_queue_handler,
        build_restart_handler,
        build_resume_handler,
        build_status_handler,
        build_test_apply_handler,
        build_today_handler,
    )
    from navarra_edu_bot.telegram_bot.client import build_bot_app
    from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

    cfg = load_config(Path("~/.navarra-edu-bot/config.yaml").expanduser())
    storage = Storage(cfg.runtime.storage_path)
    storage.init_schema()
    storage.prune_events(keep_days=30)
    storage.log_event(kind="boot", payload={"target_hour": target_hour, "convid_default": convid})

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    http_session = HttpSession(
        username=username, password=password, headless=headless, storage=storage
    )
    state = RunState(queue=ThursdayQueue())

    # Restore applied_today from previous run, if recent
    try:
        if storage.get_state_age_seconds("applied_today") and \
                storage.get_state_age_seconds("applied_today") < 24 * 3600:
            import json as _json
            raw = storage.get_state("applied_today")
            if raw:
                state.applied_today = set(_json.loads(raw))
                click.echo(f"applied_today restored from storage: {len(state.applied_today)}")
    except Exception:
        pass

    POLL_FAIL_ALERT_THRESHOLD = 3
    state_poll_fail_count = {"count": 0, "alerted": False}

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

    async def _poll_now(app) -> tuple[int, int]:
        """Force one poll RIGHT NOW (used by /poll command).

        Bypasses pause/mute, decision-history (already applied/discarded), and
        applied_today — sends every offer eligible for today's day-of-week with
        apply/discard buttons. Useful as a 'show me everything you have' button.
        Returns (fetched_count, sent_count).
        """
        from navarra_edu_bot.filter.eligibility import is_eligible
        from navarra_edu_bot.filter.ranker import rank_offers as _rank

        try:
            html = await _fetch_areapersonal_html()
        except Exception as exc:
            raise RuntimeError(f"fetch failed: {exc}") from exc

        if is_convocatoria_ended(html):
            return (0, 0)

        convid_seen = discover_active_convid(html)
        if convid_seen and convid_seen != state.discovered_convid:
            state.discovered_convid = convid_seen

        offers = parse_offers(html)
        state.last_poll_at = datetime.now()
        state.last_fetched_count = len(offers)

        # Eligibility + ranking ONLY. No dedup by decision or applied_today —
        # /poll is a "show me everything" command.
        now = datetime.now()
        eligible = [
            o
            for o in offers
            if is_eligible(o, now, cfg.available_lists, cfg.thursday_open_specialties)
        ]
        ranked = _rank(
            eligible,
            preferred_localities=cfg.user.preferred_localities,
            specialty_order=cfg.user.specialty_preference_order,
        )

        sent = 0
        for offer in ranked:
            # Persist (so /history etc. see it) but don't filter on it.
            try:
                storage.upsert_offer(offer)
            except Exception:
                pass
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=format_offer_message(offer),
                    reply_markup=offer_buttons(offer),
                    parse_mode="HTML",
                )
                sent += 1
            except Exception as exc:
                click.echo(f"manual_poll send failed for {offer.offer_id}: {exc}")

        storage.log_event(
            kind="manual_poll",
            payload={
                "fetched": len(offers),
                "eligible": len(eligible),
                "sent": sent,
                "convid": state.discovered_convid,
            },
        )
        return (len(offers), sent)

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

                if state.paused:
                    click.echo(
                        f"poll paused @ {datetime.now().isoformat()} | fetched={len(offers)}"
                    )
                    await asyncio.sleep(cfg.scheduler.poll_interval_seconds)
                    continue

                if state.is_muted():
                    click.echo(
                        f"poll muted @ {datetime.now().isoformat()} | fetched={len(offers)}"
                    )
                    await asyncio.sleep(cfg.scheduler.poll_interval_seconds)
                    continue

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
                storage.log_event(
                    kind="poll_ok",
                    payload={
                        "fetched": len(offers),
                        "sent": sent_count,
                        "convid": state.discovered_convid,
                    },
                )
                # Reset failure counter on success
                state_poll_fail_count["count"] = 0
                state_poll_fail_count["alerted"] = False
            except SessionExpiredError:
                click.echo("session expired, refreshing via Playwright")
                storage.log_event(kind="session_expired", level="warning", payload={})
                try:
                    await http_session.refresh()
                except Exception as exc:
                    click.echo(f"refresh failed: {exc}")
                    storage.log_event(
                        kind="refresh_failed", level="error", payload={"error": str(exc)}
                    )
            except Exception as exc:
                click.echo(f"poll error: {exc}")
                storage.log_event(
                    kind="poll_error", level="error", payload={"error": str(exc)}
                )
                state_poll_fail_count["count"] += 1
                # Alert ONCE after N consecutive failures, not every error.
                if (
                    state_poll_fail_count["count"] >= POLL_FAIL_ALERT_THRESHOLD
                    and not state_poll_fail_count["alerted"]
                ):
                    state_poll_fail_count["alerted"] = True
                    try:
                        await app.bot.send_message(
                            chat_id=chat_id,
                            text=(
                                f"⚠️ <b>Polling roto</b>: "
                                f"{state_poll_fail_count['count']} fallos consecutivos.\n"
                                f"Último error: <code>{exc}</code>"
                            ),
                            parse_mode="HTML",
                        )
                    except Exception:
                        pass
                # Capture a failure snapshot (best-effort)
                try:
                    await capture_failure(
                        base=Path(cfg.runtime.storage_path).parent,
                        label="poll_error",
                        html=None,
                        context={"error": str(exc), "ts": datetime.now().isoformat()},
                    )
                except Exception:
                    pass
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
        storage.log_event(
            kind="cycle_start", payload={"target": target_ts.isoformat()}
        )

        await state.queue.drain()
        state.next_target_ts = target_ts
        if state.restart_event is not None:
            state.restart_event.clear()

        # Refresh HTTP session and applied_today set at start of cycle.
        # Try restoring from storage first (fast path), fall back to Playwright login.
        try:
            restored = await http_session.try_restore_from_storage()
            if not restored:
                await http_session.refresh()
            await _refresh_applied_today()
        except Exception as exc:
            click.echo(f"cycle setup failed: {exc}")
            storage.log_event(
                kind="cycle_setup_failed", level="error", payload={"error": str(exc)}
            )

        # Pre-flight CANARY at the start of the cycle.
        canary = await run_polling_canary(http_session)
        click.echo(f"polling_canary: {canary.message}")
        storage.log_event(
            kind="canary_polling",
            level="info" if canary.ok else "warning",
            payload={"ok": canary.ok, "message": canary.message},
        )
        if not canary.ok:
            try:
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=(
                        f"⚠️ <b>Canary pre-vuelo falló</b>\n"
                        f"<code>{canary.message}</code>\n"
                        f"Revisa antes de las 14:00."
                    ),
                    parse_mode="HTML",
                )
            except Exception:
                pass

        poll_task = asyncio.create_task(_poll_until(target_ts, app))

        now = datetime.now()
        if now < prewarm_start:
            wait_s = (prewarm_start - now).total_seconds()
            click.echo(f"Waiting {wait_s:.1f}s until prewarm...")
            # Honor /restart while we wait
            if state.restart_event is not None:
                try:
                    await asyncio.wait_for(
                        state.restart_event.wait(), timeout=wait_s
                    )
                    click.echo("Cycle aborted by /restart")
                    storage.log_event(kind="cycle_restart_requested", level="warning")
                    poll_task.cancel()
                    return
                except asyncio.TimeoutError:
                    pass
            else:
                await asyncio.sleep(wait_s)

        click.echo("Starting prewarm + fast-path...")
        cycle_error: str | None = None
        submitted: list[str] = []
        elapsed_s = 0.0
        # Use discovered convid if available, otherwise fall back to CLI flag.
        active_convid = state.discovered_convid or convid

        # Healthcheck: tell the watchdog the burst is starting.
        await ping_start(payload=f"target={target_ts.isoformat()}")

        try:
            if state.paused:
                cycle_error = "bot paused"
                click.echo("fast-path skipped because bot is paused")
                storage.log_event(
                    kind="fast_path_skipped",
                    level="warning",
                    payload={"reason": "paused"},
                )
            else:
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
                storage.log_event(
                    kind="fast_path_done",
                    payload={
                        "submitted": submitted,
                        "elapsed_s": elapsed_s,
                        "convid": active_convid,
                    },
                )
        except Exception as exc:
            cycle_error = str(exc)
            click.echo(f"fast-path error: {exc}")
            storage.log_event(
                kind="fast_path_error", level="error", payload={"error": str(exc)}
            )
            try:
                await capture_failure(
                    base=Path(cfg.runtime.storage_path).parent,
                    label="fast_path_error",
                    context={"error": str(exc), "convid": active_convid},
                )
            except Exception:
                pass

        verified: list[str] = []
        missing: list[str] = []
        if submitted:
            verified, missing = await _verify_submitted(submitted)

        # Persist applied_today for next container start
        try:
            import json as _json
            storage.set_state(
                "applied_today", _json.dumps(sorted(state.applied_today))
            )
        except Exception:
            pass

        await _send_heartbeat(
            app, target_ts, submitted, verified, missing, elapsed_s, cycle_error
        )

        # Healthcheck: success ping closes the /start, /fail or /(none) cycle.
        if (cycle_error and cycle_error != "bot paused") or missing:
            await ping_fail(payload=f"{cycle_error or 'missing offers'}")
        else:
            await ping_success(payload=f"submitted={len(submitted)}")

        # Daily backup once per day (skip if already done today)
        try:
            today_marker = datetime.now().strftime("%Y-%m-%d")
            if state.last_backup_ts is None or \
                    state.last_backup_ts.strftime("%Y-%m-%d") != today_marker:
                await daily_backup(
                    storage_path=cfg.runtime.storage_path,
                    bot=app.bot,
                    chat_id=chat_id,
                )
                state.last_backup_ts = datetime.now()
        except Exception as exc:
            click.echo(f"daily backup failed: {exc}")

        # Brief grace, then cancel polling task cleanly
        await asyncio.sleep(10)
        poll_task.cancel()
        try:
            await poll_task
        except (asyncio.CancelledError, Exception):
            pass

    async def _dryrun_fetch():
        """Used by /dryrun handler — fetch + parse offers without notifying."""
        html = await _fetch_areapersonal_html()
        return parse_offers(html)

    async def _run() -> None:
        # Initialise the restart event now that we have a running loop
        state.restart_event = asyncio.Event()

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
        app.add_handler(build_help_handler())
        app.add_handler(build_status_handler(state))
        app.add_handler(
            build_next_handler(
                state,
                poll_interval_seconds=cfg.scheduler.poll_interval_seconds,
                prewarm_seconds_before=prewarm_seconds_before,
            )
        )
        app.add_handler(
            build_health_handler(
                storage,
                state,
                poll_interval_seconds=cfg.scheduler.poll_interval_seconds,
            )
        )
        app.add_handler(build_cancel_handler(state))
        app.add_handler(build_queue_handler(state))
        app.add_handler(build_today_handler(storage, state))
        app.add_handler(build_offer_handler(storage, state))
        app.add_handler(
            build_apply_command_handler(
                storage,
                state,
                apply_email=email,
                apply_phone=phone,
            )
        )
        app.add_handler(build_discard_command_handler(storage, state))
        app.add_handler(build_history_handler(storage))
        app.add_handler(
            build_filters_handler(
                preferred_localities=cfg.user.preferred_localities,
                specialty_order=cfg.user.specialty_preference_order,
                available_lists=[
                    f"{entry.body}/{entry.specialty}" for entry in cfg.available_lists
                ],
                thursday_open_specialties=[
                    f"{entry.body}/{entry.specialty}"
                    for entry in cfg.thursday_open_specialties
                ],
            )
        )
        app.add_handler(build_logs_handler(storage))
        app.add_handler(build_dryrun_handler(state, _dryrun_fetch))
        app.add_handler(build_poll_handler(lambda: _poll_now(app)))
        app.add_handler(build_pause_handler(state))
        app.add_handler(build_resume_handler(state))
        app.add_handler(build_mute_handler(state))
        app.add_handler(build_mute_until_handler(state))
        app.add_handler(build_restart_handler(state))
        app.add_handler(
            build_test_apply_handler(state, apply_email=email, apply_phone=phone)
        )

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
