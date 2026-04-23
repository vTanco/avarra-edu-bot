from __future__ import annotations

import hashlib
import re
from datetime import datetime

from bs4 import BeautifulSoup

from navarra_edu_bot.storage.models import Offer


class SessionExpiredError(RuntimeError):
    pass


# Selectors confirmed from real portal fixtures (captured 2026-04-22).
#
# Page structure (authenticated, /atp/auth/areapersonal.xhtml):
#   - User menu: .dropdown-user (present when logged in)
#   - DataTable: div.ui-datatable > div.ui-datatable-tablewrapper > table
#   - Data rows: tbody[id$='_data'] > tr[data-ri] (data-ri = row index)
#   - Expanded detail rows: tr.ui-expanded-row-content (skip these)
#   - Columns (0-indexed td[role=gridcell]):
#     0: expand button
#     1: Id (e.g. "121776")
#     2: Lista (e.g. "0590/INSTALACIONES ELECTROTÉCNICAS/C")
#     3: Localidad (e.g. "PAMPLONA")
#     4: Centro (e.g. "CI SAN JUAN-DONIBANE")
#     5: Tipo oferta (e.g. "S" for sustitución)
#     6: Perfiles
#     7: Jornada - horas lectivas (e.g. "SUPERIOR A MEDIA JORNADA (12)")
#     8: Itinerante
#     9: Habilidades
#
# Page structure (not authenticated, /atp/index.xhtml):
#   - Has form#formIndex
#   - Does NOT have .dropdown-user

_DATATABLE_ROWS_SELECTOR = "div.ui-datatable tbody[id$='_data'] > tr[data-ri]"
_LOGOUT_LINK = "a[href='/atp/logout.xhtml']"
_NOT_AUTHENTICATED_INDICATOR = "form#formIndex"


def parse_offers(html: str) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")

    # Detect session expired / not authenticated:
    # If we see the public index form AND no logout link, session is expired.
    has_logout = soup.select_one(_LOGOUT_LINK)
    has_index_form = soup.select_one(_NOT_AUTHENTICATED_INDICATOR)

    if has_index_form and not has_logout:
        raise SessionExpiredError("Session expired: login form detected, no user menu")

    rows = soup.select(_DATATABLE_ROWS_SELECTOR)
    now = datetime.now()
    offers: list[Offer] = []
    for row in rows:
        cells = row.find_all("td", role="gridcell")
        if len(cells) < 8:
            continue

        offer_id = cells[1].get_text(strip=True)
        lista_raw = cells[2].get_text(strip=True)
        locality = cells[3].get_text(strip=True)
        center = cells[4].get_text(strip=True)
        jornada_raw = cells[7].get_text(strip=True)

        # Parse "0590/INSTALACIONES ELECTROTÉCNICAS/C" → body="0590", specialty="INSTALACIONES ELECTROTÉCNICAS", lang="C"
        body, specialty, lang = _parse_lista(lista_raw)
        
        # Filtramos automáticamente las ofertas en Euskera ("E") según lo pedido
        # Usamos startswith porque a veces viene con info extra, ej: "E (perfil de lengua extranjera: inglés)"
        if lang.upper().startswith("E"):
            continue

        # Parse "SUPERIOR A MEDIA JORNADA (12)" → 12
        hours = _parse_hours(jornada_raw)

        # Parse duration from the expanded detail row (next sibling)
        duration = _parse_duration(row)

        offers.append(
            Offer(
                offer_id=offer_id,
                body=body,
                specialty=specialty,
                locality=locality,
                center=center,
                hours_per_week=hours,
                duration=duration,
                raw_html_hash=_hash([offer_id, lista_raw, locality, center, jornada_raw]),
                seen_at=now,
            )
        )
    return offers


def _parse_lista(raw: str) -> tuple[str, str, str]:
    """Parse '0590/INSTALACIONES ELECTROTÉCNICAS/C' → ('0590', 'INSTALACIONES ELECTROTÉCNICAS', 'C')."""
    parts = raw.split("/")
    body = parts[0].strip() if len(parts) >= 1 else ""
    specialty = parts[1].strip() if len(parts) >= 2 else raw.strip()
    lang = parts[2].strip() if len(parts) >= 3 else "C" # Default to Castellano if not specified
    return body, specialty, lang


def _parse_hours(raw: str) -> int:
    """Parse 'SUPERIOR A MEDIA JORNADA (12)' → 12."""
    match = re.search(r"\((\d+)\)", raw)
    if match:
        return int(match.group(1))
    digits = "".join(c for c in raw if c.isdigit())
    return int(digits) if digits else 0


def _parse_duration(data_row) -> str:
    """Extract start/end dates from the expanded detail row that follows the data row."""
    next_row = data_row.find_next_sibling("tr", class_="ui-expanded-row-content")
    if not next_row:
        return ""
    dts = next_row.find_all("dt")
    parts = []
    for dt in dts:
        dd = dt.find_next_sibling("dd")
        if dd:
            label = dt.get_text(strip=True)
            value = dd.get_text(strip=True)
            if label in ("Fecha inicio", "Fecha fin (máxima)"):
                parts.append(f"{label}: {value}")
    return " | ".join(parts) if parts else ""


def _hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]
