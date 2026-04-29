from __future__ import annotations

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

log = structlog.get_logger()


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

            convid = (
                run_state.discovered_convid
                if run_state is not None and run_state.discovered_convid
                else "1206"
            )

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
            await query.edit_message_text(
                f"{query.message.text_html}\n\n❌ Descartada",
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

        text = (
            "<b>Estado del bot</b>\n"
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
