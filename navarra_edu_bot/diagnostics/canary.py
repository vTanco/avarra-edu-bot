"""Pre-flight canaries: probe critical paths before the race so failures surface
with enough margin to fix them manually.

Two canaries:
  - run_polling_canary: at the start of the polling window. Verifies that the
    HTTP session can fetch areapersonal and that parser still understands the
    HTML.
  - run_fastpath_canary: ~10 minutes before the burst, while the prewarmed
    page is alive. Verifies the modal still has the add-button selector.

Both return CanaryResult with `ok: bool` and a human-readable message. They
NEVER raise — caller decides what to do with the result.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class CanaryResult:
    ok: bool
    message: str
    detail: Optional[str] = None


async def run_polling_canary(http_session) -> CanaryResult:
    """Validate that we can fetch + parse the personal area.

    Checks:
      1. HTTP GET areapersonal returns 200.
      2. parser detects the authenticated marker (logout link).
      3. discover_active_convid finds a convid.
    """
    from navarra_edu_bot.scraper.parser import (
        SessionExpiredError,
        discover_active_convid,
        is_convocatoria_ended,
        parse_offers,
    )

    try:
        html = await http_session.fetch_areapersonal_html()
    except Exception as exc:
        return CanaryResult(False, f"HTTP fetch failed: {exc}")

    if is_convocatoria_ended(html):
        return CanaryResult(
            False, "Portal indica plazo finalizado", detail="convocatoria_ended"
        )

    try:
        offers = parse_offers(html)
    except SessionExpiredError as exc:
        return CanaryResult(False, f"Session expired: {exc}")
    except Exception as exc:
        return CanaryResult(False, f"Parse failed: {exc}")

    convid = discover_active_convid(html)
    if convid is None:
        return CanaryResult(
            False, "No se encontró convid activo en la página",
            detail="missing_convid",
        )

    return CanaryResult(
        True,
        f"Polling canary OK — {len(offers)} ofertas detectadas, convid={convid}",
        detail=str(len(offers)),
    )


async def run_fastpath_canary(page) -> CanaryResult:
    """Validate that the prewarmed page still exposes the add-button selector.

    Doesn't click anything — just verifies the DOM hasn't changed under us
    (e.g. portal pushed a new build mid-day).
    """
    try:
        rows = page.locator("#ofertasDisponiblesDtId_data > tr")
        row_count = await rows.count()
        if row_count == 0:
            return CanaryResult(
                False, "Modal de ofertas vacío — selector roto o ofertas no cargadas"
            )
        # Pick first row, check the add button selector is present
        first_btn = rows.nth(0).locator("a[id$=':anadirOfertaBtn']")
        btn_count = await first_btn.count()
        if btn_count == 0:
            return CanaryResult(
                False,
                "Selector :anadirOfertaBtn no encontrado en la primera fila",
                detail="selector_drift",
            )
    except Exception as exc:
        return CanaryResult(False, f"Fast-path canary explotó: {exc}")

    return CanaryResult(True, f"Fast-path canary OK — {row_count} filas en modal")
