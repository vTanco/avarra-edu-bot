from __future__ import annotations

import hashlib
from datetime import datetime

from bs4 import BeautifulSoup

from navarra_edu_bot.storage.models import Offer


class SessionExpiredError(RuntimeError):
    pass


# Selectors extracted from captured fixtures. Adjust after Task 9.
# Document here the exact path used, e.g.:
# - Offers table: table#offersTable
# - Row: tbody > tr
# - Cells: td:nth-child(1) body, (2) specialty, (3) locality, (4) center,
#          (5) hours, (6) duration, (7) apply button
# - Login presence indicator (session expired): div.login-form
_OFFERS_TABLE_SELECTOR = "table#offersTable tbody tr"  # TODO: confirm
_LOGIN_INDICATOR = "div.login-form"  # TODO: confirm


def parse_offers(html: str) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")

    if soup.select_one(_LOGIN_INDICATOR):
        raise SessionExpiredError("Session expired: login form detected")

    rows = soup.select(_OFFERS_TABLE_SELECTOR)
    now = datetime.now()
    offers: list[Offer] = []
    for idx, row in enumerate(rows):
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 6:
            continue
        offer_id = row.get("data-id") or f"row-{idx}-{_hash(cells)}"
        offers.append(
            Offer(
                offer_id=str(offer_id),
                body=cells[0],
                specialty=cells[1],
                locality=cells[2],
                center=cells[3],
                hours_per_week=_parse_int(cells[4]),
                duration=cells[5],
                raw_html_hash=_hash(cells),
                seen_at=now,
            )
        )
    return offers


def _hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _parse_int(text: str) -> int:
    digits = "".join(c for c in text if c.isdigit())
    return int(digits) if digits else 0
