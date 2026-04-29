from __future__ import annotations

import os
from datetime import timedelta
from datetime import datetime
from typing import Optional

import structlog
from telegram import Update
from telegram.ext import (
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
)

from navarra_edu_bot.scheduler.run_state import RunState
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

log = structlog.get_logger()


def _current_convid(run_state: Optional[RunState]) -> str:
    if run_state is not None and run_state.discovered_convid:
        return run_state.discovered_convid
    return "1206"


def _offer_status(storage: Storage, run_state: RunState, offer_id: str) -> str:
    if offer_id in run_state.applied_today:
        return "✅ <b>Estado actual:</b> ya aplicada hoy"

    decision = storage.get_preselected_decision(offer_id)
    if decision is True:
        return "⏳ <b>Estado actual:</b> marcada para aplicar"
    if decision is False:
        return "❌ <b>Estado actual:</b> descartada"
    return "🆕 <b>Estado actual:</b> sin decidir"


def _human_delta(delta: timedelta) -> str:
    total_seconds = max(0, int(delta.total_seconds()))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}h {minutes:02d}m {seconds:02d}s"
    if minutes:
        return f"{minutes}m {seconds:02d}s"
    return f"{seconds}s"


def build_callback_handler(
    storage: Storage,
    thursday_queue: ThursdayQueue | None = None,
    run_state: Optional[RunState] = None,
    *,
    apply_email: str,
    apply_phone: str,
) -> CallbackQueryHandler:
    """Handle inline-button callbacks (apply / discard).

    On Thursday + a Thursday queue is available, "apply" enqueues for the 14:00
    burst. Otherwise it fires a single-offer apply flow immediately.
    """

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()

        try:
            action, offer_id = query.data.split(":", 1)
        except ValueError:
            log.warning("bad_callback_data", data=query.data)
            return

        if action == "apply":
            if run_state is not None and run_state.paused:
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n"
                    f"⏸️ <b>Bot en pausa</b> — reanúdalo con /resume.",
                    parse_mode="HTML",
                    reply_markup=None,
                )
                return

            storage.mark_preselected(offer_id, preselected=True)

            # Skip if already applied today (idempotency).
            if run_state is not None and offer_id in run_state.applied_today:
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n"
                    f"ℹ️ <b>Ya aplicada anteriormente</b> (no se vuelve a enviar)",
                    parse_mode="HTML",
                    reply_markup=None,
                )
                return

            is_thursday = datetime.now().weekday() == 3
            if is_thursday and thursday_queue is not None:
                await thursday_queue.add(offer_id)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n⏳ <b>Encolada para las 14:00</b>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
                log.info("thursday_queued", offer_id=offer_id)
                return

            # Non-Thursday: apply immediately.
            await query.edit_message_text(
                f"{query.message.text_html}\n\n⏳ <b>Aplicando...</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
            import time
            click_time = time.monotonic()

            convid = _current_convid(run_state)

            try:
                from navarra_edu_bot.scraper.apply import apply_single_offer_flow
                _added_offers, true_latency = await apply_single_offer_flow(
                    offer_id=offer_id,
                    email=apply_email,
                    phone=apply_phone,
                    convid=convid,
                )
                if run_state is not None:
                    run_state.applied_today.add(offer_id)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n"
                    f"✅ <b>Solicitud Presentada</b> (tardó {true_latency:.2f} s)",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as e:
                elapsed = time.monotonic() - click_time
                log.error("apply_failed", error=str(e), elapsed_s=elapsed)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n"
                    f"❌ <b>Error al aplicar</b> tras {elapsed:.2f}s: {e}",
                    parse_mode="HTML",
                    reply_markup=None,
                )
        elif action == "discard":
            storage.mark_preselected(offer_id, preselected=False)
            removed_from_queue = False
            if thursday_queue is not None:
                removed_from_queue = await thursday_queue.remove(offer_id)
            await query.edit_message_text(
                f"{query.message.text_html}\n\n"
                f"❌ Descartada"
                f"{' y eliminada de la cola' if removed_from_queue else ''}",
                parse_mode="HTML",
                reply_markup=None,
            )
        else:
            log.warning("unknown_action", action=action)

    return CallbackQueryHandler(_handle)


def build_status_handler(run_state: RunState) -> CommandHandler:
    """/status — current queue, next target, last poll, applied-today count."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        queue_ids = await run_state.queue.snapshot()
        last_poll = (
            run_state.last_poll_at.strftime("%H:%M:%S")
            if run_state.last_poll_at
            else "—"
        )
        next_target = (
            run_state.next_target_ts.strftime("%Y-%m-%d %H:%M")
            if run_state.next_target_ts
            else "—"
        )
        queue_str = (
            "\n".join(f"  • <code>{oid}</code>" for oid in queue_ids)
            if queue_ids
            else "  (vacía)"
        )
        applied_str = (
            ", ".join(f"<code>{oid}</code>" for oid in sorted(run_state.applied_today))
            if run_state.applied_today
            else "ninguna"
        )
        if run_state.paused:
            activity = "⏸️ en pausa"
        elif run_state.is_muted():
            activity = f"🔕 silenciado hasta {run_state.muted_until.strftime('%H:%M')}"
        else:
            activity = "▶️ activo"

        text = (
            "<b>Estado del bot</b>\n"
            f"\n🟢 Actividad: <b>{activity}</b>"
            f"\n📅 Próximo target: <b>{next_target}</b>"
            f"\n🔄 Última poll: <b>{last_poll}</b> ({run_state.last_fetched_count} ofertas)"
            f"\n📋 Cola: {len(queue_ids)} oferta(s)\n{queue_str}"
            f"\n✅ Aplicadas hoy: {applied_str}"
            f"\n🆔 Convid activo: <code>{run_state.discovered_convid or '—'}</code>"
        )
        if run_state.convocatoria_ended:
            text += "\n\n⚠️ <b>Convocatoria finalizada</b> — polling pausado."

        await update.message.reply_html(text)

    return CommandHandler("status", _handle)


def build_cancel_handler(run_state: RunState) -> CommandHandler:
    """/cancel <offer_id> — remove an offer from the Thursday queue."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text(
                "Uso: /cancel <offer_id>  (ej. /cancel 121936)"
            )
            return
        offer_id = context.args[0].strip()
        removed = await run_state.queue.remove(offer_id)
        if removed:
            await update.message.reply_text(f"✅ Eliminada {offer_id} de la cola.")
        else:
            await update.message.reply_text(
                f"ℹ️ {offer_id} no estaba en la cola."
            )

    return CommandHandler("cancel", _handle)


def build_queue_handler(run_state: RunState) -> CommandHandler:
    """/queue — show only the queue (shorter than /status)."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        ids = await run_state.queue.snapshot()
        if not ids:
            await update.message.reply_text("Cola vacía.")
            return
        await update.message.reply_html(
            "<b>Cola actual:</b>\n"
            + "\n".join(f"  • <code>{oid}</code>" for oid in ids)
        )

    return CommandHandler("queue", _handle)


def build_today_handler(storage: Storage, run_state: RunState) -> CommandHandler:
    """/today — resend today's offers with fresh inline buttons."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        offers = storage.list_offers_seen_today(now=datetime.now())
        if not offers:
            await update.message.reply_text("No hay ofertas registradas hoy.")
            return

        await update.message.reply_text(
            f"Reenviando {len(offers)} oferta(s) de hoy con botones."
        )
        for offer in offers:
            await update.message.reply_html(
                f"{format_offer_message(offer)}\n\n{_offer_status(storage, run_state, offer.offer_id)}",
                reply_markup=offer_buttons(offer),
            )

    return CommandHandler("today", _handle)


def build_help_handler() -> CommandHandler:
    """/help — show the available Telegram commands."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        text = (
            "<b>Comandos de Telegram</b>\n"
            "\n<b>Consulta</b>"
            "\n/status — estado general"
            "\n/next — siguiente target, prewarm y próxima poll"
            "\n/health — salud operativa del bot"
            "\n/queue — cola del jueves"
            "\n/today — reenvía las ofertas de hoy con botones"
            "\n/offer &lt;id&gt; — detalle de una oferta con botones"
            "\n/history [N] — últimas decisiones"
            "\n/filters — filtros activos"
            "\n/logs [N] — últimos eventos"
            "\n\n<b>Acción</b>"
            "\n/apply &lt;id&gt; — aplicar o encolar una oferta conocida"
            "\n/discard &lt;id&gt; — descartar y, si procede, quitar de la cola"
            "\n/cancel &lt;id&gt; — quitar de la cola del jueves"
            "\n/pause — pausa las acciones automáticas"
            "\n/resume — reanuda el bot"
            "\n/mute [min] — silencia avisos temporalmente"
            "\n/mute_until HH:MM — silencia hasta una hora concreta"
            "\n/restart — reinicia el ciclo actual"
            "\n\n<b>Debug</b>"
            "\n/dryrun — fetch inmediato sin aplicar"
            "\n/test_apply &lt;id&gt; — prueba el flujo de aplicación sin confirmar"
        )
        await update.message.reply_html(text)

    return CommandHandler("help", _handle)


def build_next_handler(
    run_state: RunState, *, poll_interval_seconds: int, prewarm_seconds_before: int
) -> CommandHandler:
    """/next — next target, prewarm and estimated next poll."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        now = datetime.now()
        next_target = run_state.next_target_ts
        if next_target is None:
            await update.message.reply_text("Todavía no hay target calculado.")
            return

        prewarm_start = next_target - timedelta(seconds=prewarm_seconds_before)
        lines = [
            "<b>Siguiente ventana</b>",
            f"🎯 Target: <b>{next_target.strftime('%Y-%m-%d %H:%M:%S')}</b>",
            f"🔥 Prewarm: <b>{prewarm_start.strftime('%Y-%m-%d %H:%M:%S')}</b>",
        ]
        if run_state.last_poll_at is not None:
            next_poll = run_state.last_poll_at + timedelta(seconds=poll_interval_seconds)
            lines.append(
                f"🔄 Próxima poll aprox.: <b>{next_poll.strftime('%H:%M:%S')}</b>"
            )
        lines.append(f"⏳ Faltan: <b>{_human_delta(next_target - now)}</b>")
        await update.message.reply_html("\n".join(lines))

    return CommandHandler("next", _handle)


def build_offer_handler(storage: Storage, run_state: RunState) -> CommandHandler:
    """/offer <offer_id> — show one stored offer with fresh buttons."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Uso: /offer <offer_id>")
            return

        offer_id = context.args[0].strip()
        offer = storage.get_offer(offer_id)
        if offer is None:
            await update.message.reply_text(
                f"No conozco la oferta {offer_id}. Usa /today para ver las de hoy."
            )
            return

        await update.message.reply_html(
            f"{format_offer_message(offer)}\n\n{_offer_status(storage, run_state, offer_id)}",
            reply_markup=offer_buttons(offer),
        )

    return CommandHandler("offer", _handle)


def build_apply_command_handler(
    storage: Storage,
    run_state: RunState,
    *,
    apply_email: str,
    apply_phone: str,
) -> CommandHandler:
    """/apply <offer_id> — command version of the inline Apply button."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Uso: /apply <offer_id>")
            return

        offer_id = context.args[0].strip()
        offer = storage.get_offer(offer_id)
        if offer is None:
            await update.message.reply_text(
                f"No conozco la oferta {offer_id}. Usa /today o /offer {offer_id}."
            )
            return
        if run_state.paused:
            await update.message.reply_text("⏸️ El bot está en pausa. Usa /resume primero.")
            return

        storage.mark_preselected(offer_id, preselected=True)
        if offer_id in run_state.applied_today:
            await update.message.reply_text(
                f"ℹ️ {offer_id} ya figura como aplicada hoy."
            )
            return

        is_thursday = datetime.now().weekday() == 3
        if is_thursday:
            await run_state.queue.add(offer_id)
            await update.message.reply_html(
                f"⏳ <b>Encolada para las 14:00</b>\n\n{format_offer_message(offer)}"
            )
            return

        await update.message.reply_text(f"⏳ Aplicando {offer_id}...")
        import time

        click_time = time.monotonic()
        try:
            from navarra_edu_bot.scraper.apply import apply_single_offer_flow

            _added_offers, true_latency = await apply_single_offer_flow(
                offer_id=offer_id,
                email=apply_email,
                phone=apply_phone,
                convid=_current_convid(run_state),
            )
            run_state.applied_today.add(offer_id)
            await update.message.reply_html(
                f"✅ <b>Solicitud Presentada</b> para <code>{offer_id}</code> "
                f"(tardó {true_latency:.2f} s)"
            )
        except Exception as exc:
            elapsed = time.monotonic() - click_time
            log.error("apply_command_failed", error=str(exc), elapsed_s=elapsed)
            await update.message.reply_text(
                f"❌ Error al aplicar {offer_id} tras {elapsed:.2f}s: {exc}"
            )

    return CommandHandler("apply", _handle)


def build_discard_command_handler(storage: Storage, run_state: RunState) -> CommandHandler:
    """/discard <offer_id> — command version of the inline Discard button."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Uso: /discard <offer_id>")
            return

        offer_id = context.args[0].strip()
        offer = storage.get_offer(offer_id)
        if offer is None:
            await update.message.reply_text(
                f"No conozco la oferta {offer_id}. Usa /today para ver las conocidas."
            )
            return

        storage.mark_preselected(offer_id, preselected=False)
        removed = await run_state.queue.remove(offer_id)
        await update.message.reply_text(
            f"❌ Descartada {offer_id}{' y eliminada de la cola' if removed else ''}."
        )

    return CommandHandler("discard", _handle)


def build_pause_handler(run_state: RunState) -> CommandHandler:
    """/pause — stop automatic actions while keeping the process alive."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if run_state.paused:
            await update.message.reply_text("El bot ya estaba en pausa.")
            return
        run_state.paused = True
        await update.message.reply_text(
            "⏸️ Bot en pausa. Sigue vivo, pero no notificará ni disparará solicitudes."
        )

    return CommandHandler("pause", _handle)


def build_resume_handler(run_state: RunState) -> CommandHandler:
    """/resume — resume a paused or muted bot."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        run_state.paused = False
        run_state.muted_until = None
        await update.message.reply_text("▶️ Bot reanudado.")

    return CommandHandler("resume", _handle)


def build_mute_handler(run_state: RunState) -> CommandHandler:
    """/mute [minutes] — temporarily silence Telegram notifications."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        minutes = 60
        if context.args:
            try:
                minutes = max(1, min(24 * 60, int(context.args[0])))
            except ValueError:
                await update.message.reply_text("Uso: /mute [minutos]")
                return
        run_state.muted_until = datetime.now() + timedelta(minutes=minutes)
        await update.message.reply_text(
            f"🔕 Avisos silenciados hasta las {run_state.muted_until.strftime('%H:%M')}."
        )

    return CommandHandler("mute", _handle)


def build_mute_until_handler(run_state: RunState) -> CommandHandler:
    """/mute_until HH:MM — silence until an absolute local time."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text("Uso: /mute_until HH:MM")
            return
        raw = context.args[0].strip()
        try:
            hour_str, minute_str = raw.split(":", 1)
            hour = int(hour_str)
            minute = int(minute_str)
            now = datetime.now()
            target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if target <= now:
                target = target + timedelta(days=1)
        except ValueError:
            await update.message.reply_text("Uso: /mute_until HH:MM")
            return

        run_state.muted_until = target
        await update.message.reply_text(
            f"🔕 Avisos silenciados hasta {target.strftime('%Y-%m-%d %H:%M')}."
        )

    return CommandHandler("mute_until", _handle)


def build_history_handler(storage: Storage) -> CommandHandler:
    """/history [N] — show the latest apply/discard decisions."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        limit = 10
        if context.args:
            try:
                limit = max(1, min(30, int(context.args[0])))
            except ValueError:
                await update.message.reply_text("Uso: /history [N]")
                return

        decisions = storage.list_recent_decisions(limit=limit)
        if not decisions:
            await update.message.reply_text("No hay decisiones registradas todavía.")
            return

        lines = [f"<b>Últimas {len(decisions)} decisiones</b>\n"]
        for item in decisions:
            action = "✅ aplicar" if item["preselected"] else "❌ descartar"
            when = item["decided_at"].split("T")[1][:8] if "T" in item["decided_at"] else item["decided_at"]
            label = item["specialty"] or "Oferta desconocida"
            locality = item["locality"] or "—"
            lines.append(
                f"<code>{when}</code> {action} <code>{item['offer_id']}</code> "
                f"{label} @ {locality}"
            )
        await update.message.reply_html("\n".join(lines))

    return CommandHandler("history", _handle)


def build_filters_handler(
    *,
    preferred_localities: list[str],
    specialty_order: list[str],
    available_lists: list[str],
    thursday_open_specialties: list[str],
) -> CommandHandler:
    """/filters — show the active preference and eligibility filters."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        text = (
            "<b>Filtros activos</b>\n"
            f"\n📍 Localidades preferidas: {', '.join(preferred_localities) or '—'}"
            f"\n🏆 Orden de especialidad: {', '.join(specialty_order) or '—'}"
            f"\n🗂️ Listas disponibles L/M/X/V ({len(available_lists)}): "
            f"{', '.join(available_lists) or '—'}"
            f"\n📘 Especialidades abiertas jueves ({len(thursday_open_specialties)}): "
            f"{', '.join(thursday_open_specialties) or '—'}"
        )
        await update.message.reply_html(text)

    return CommandHandler("filters", _handle)


def build_health_handler(
    storage: Storage, run_state: RunState, *, poll_interval_seconds: int
) -> CommandHandler:
    """/health — operational health snapshot without touching the portal."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return

        now = datetime.now()
        cookie_age = storage.get_state_age_seconds("http_session.cookies")
        last_errors = storage.recent_events(limit=1, level="error")
        last_error = "ninguno"
        if last_errors:
            item = last_errors[0]
            payload = item["payload"]
            summary = payload.get("error") if isinstance(payload, dict) else str(payload)
            last_error = f"{item['kind']} @ {item['ts']} — {summary}"

        if run_state.last_poll_at is not None:
            poll_age = _human_delta(now - run_state.last_poll_at)
            next_poll = run_state.last_poll_at + timedelta(seconds=poll_interval_seconds)
            next_poll_str = next_poll.strftime("%H:%M:%S")
        else:
            poll_age = "—"
            next_poll_str = "—"

        activity = "pausado" if run_state.paused else "activo"
        if run_state.is_muted(now):
            activity += f", silenciado hasta {run_state.muted_until.strftime('%H:%M')}"

        lines = [
            "<b>Health</b>",
            f"🟢 Estado: <b>{activity}</b>",
            f"🔄 Última poll: <b>{poll_age}</b> ({run_state.last_fetched_count} ofertas)",
            f"⏱ Próxima poll aprox.: <b>{next_poll_str}</b>",
            f"🆔 Convid activo: <code>{run_state.discovered_convid or '—'}</code>",
            f"📋 Cola: <b>{len(await run_state.queue.snapshot())}</b> oferta(s)",
            f"🍪 Cookies HTTP: <b>{_human_delta(timedelta(seconds=int(cookie_age))) if cookie_age is not None else '—'}</b>",
            f"⚠️ Último error: <code>{last_error}</code>",
            f"🩺 Healthcheck externo: <b>{'configurado' if os.environ.get('HEALTHCHECK_PING_URL') else 'no configurado'}</b>",
        ]
        if run_state.convocatoria_ended:
            lines.append("🚧 Convocatoria finalizada: <b>sí</b>")
        await update.message.reply_html("\n".join(lines))

    return CommandHandler("health", _handle)


def build_logs_handler(storage: Storage) -> CommandHandler:
    """/logs [N] — show the last N events from the SQLite events table.

    Default N=10, max N=30.
    """
    import json as _json

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        n = 10
        if context.args:
            try:
                n = max(1, min(30, int(context.args[0])))
            except ValueError:
                n = 10
        events = storage.recent_events(limit=n)
        if not events:
            await update.message.reply_text("Sin eventos registrados.")
            return
        lines = [f"<b>Últimos {len(events)} eventos:</b>\n"]
        for e in events:
            payload_short = _json.dumps(e["payload"], ensure_ascii=False)
            if len(payload_short) > 120:
                payload_short = payload_short[:117] + "..."
            ts = e["ts"].split("T")[1][:8] if "T" in e["ts"] else e["ts"]
            level_emoji = {"error": "❌", "warning": "⚠️", "info": "ℹ️"}.get(
                e["level"], "·"
            )
            lines.append(
                f"{level_emoji} <code>{ts}</code> <b>{e['kind']}</b> "
                f"{payload_short}"
            )
        await update.message.reply_html("\n".join(lines))

    return CommandHandler("logs", _handle)


def build_dryrun_handler(run_state: RunState, fetch_callback) -> CommandHandler:
    """/dryrun — fetch areapersonal NOW and report what would be notified.

    `fetch_callback` is an async callable that returns a list of `Offer` objects.
    Lives in cli.py because it depends on http_session etc.
    """

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        await update.message.reply_text("⏳ Ejecutando dryrun...")
        try:
            offers = await fetch_callback()
        except Exception as exc:
            await update.message.reply_text(f"❌ dryrun falló: {exc}")
            return
        if not offers:
            await update.message.reply_text("0 ofertas detectadas.")
            return
        lines = [f"<b>{len(offers)} ofertas detectadas:</b>\n"]
        for o in offers[:15]:
            lines.append(
                f"• <code>{o.offer_id}</code> [{o.body}] "
                f"{o.specialty} @ {o.locality} ({o.hours_per_week}h)"
            )
        if len(offers) > 15:
            lines.append(f"...y {len(offers) - 15} más")
        await update.message.reply_html("\n".join(lines))

    return CommandHandler("dryrun", _handle)


def build_poll_handler(poll_callback) -> CommandHandler:
    """/poll — force a real poll RIGHT NOW and send each undecided offer with buttons.

    Bypasses pause/mute (it's an explicit user action) and ignores the cycle's
    seen-set, so every offer that's currently eligible AND has no decision yet
    arrives in the chat with apply/discard buttons.

    `poll_callback` is an async callable returning (fetched_count, sent_count).
    Lives in cli.py because it depends on http_session, storage, config, etc.
    """

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        await update.message.reply_text("⏳ Polling manual en marcha...")
        try:
            fetched, sent = await poll_callback()
        except Exception as exc:
            await update.message.reply_text(f"❌ Polling manual falló: {exc}")
            return
        if fetched == 0:
            await update.message.reply_text(
                "0 ofertas detectadas en el portal ahora mismo."
            )
            return
        if sent == 0:
            await update.message.reply_text(
                f"{fetched} oferta(s) detectada(s), pero ninguna pendiente de decisión "
                "(todas ya aplicadas o descartadas)."
            )
            return
        await update.message.reply_text(
            f"✅ {sent}/{fetched} oferta(s) enviada(s) con botones."
        )

    return CommandHandler("poll", _handle)


def build_restart_handler(run_state: RunState) -> CommandHandler:
    """/restart — abort the current cycle and start a fresh one."""

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if run_state.restart_event is None:
            await update.message.reply_text(
                "Restart no disponible (estado no inicializado)."
            )
            return
        run_state.restart_event.set()
        await update.message.reply_text(
            "🔄 Restart solicitado. El ciclo actual abortará en breve."
        )

    return CommandHandler("restart", _handle)


def build_test_apply_handler(
    run_state: RunState,
    *,
    apply_email: str,
    apply_phone: str,
) -> CommandHandler:
    """/test-apply <offer_id> — run the apply flow up to (but not through) confirm.

    Verifies selectors are intact without consuming a real solicitud.
    """

    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message is None:
            return
        if not context.args:
            await update.message.reply_text(
                "Uso: /test-apply <offer_id>"
            )
            return
        offer_id = context.args[0].strip()
        await update.message.reply_text(
            f"⏳ Test-apply en marcha para {offer_id} (sin presentar la solicitud)..."
        )
        try:
            from navarra_edu_bot.scraper.apply import apply_single_offer_flow
            convid = run_state.discovered_convid or "1206"
            added, latency = await apply_single_offer_flow(
                offer_id=offer_id,
                email=apply_email,
                phone=apply_phone,
                convid=convid,
                dry_run=True,
            )
            if added:
                await update.message.reply_html(
                    f"✅ <b>Test-apply OK</b>: {len(added)} oferta(s) "
                    f"añadida(s), modal de presentar mostrado y descartado. "
                    f"Latencia simulada {latency:.2f}s."
                )
            else:
                await update.message.reply_text(
                    "⚠️ Test-apply: no se pudo añadir la oferta (no estaba en el modal?)."
                )
        except Exception as exc:
            await update.message.reply_text(f"❌ Test-apply falló: {exc}")

    return CommandHandler("test_apply", _handle)
