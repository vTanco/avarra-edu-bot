from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Offer:
    offer_id: str
    body: str
    specialty: str
    locality: str
    center: str
    hours_per_week: int
    duration: str
    raw_html_hash: str
    seen_at: datetime
