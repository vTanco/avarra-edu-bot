from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from navarra_edu_bot.storage.models import Offer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    specialty TEXT NOT NULL,
    locality TEXT NOT NULL,
    center TEXT NOT NULL,
    hours_per_week INTEGER NOT NULL,
    duration TEXT NOT NULL,
    raw_html_hash TEXT NOT NULL,
    seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    offer_id TEXT PRIMARY KEY,
    preselected INTEGER NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
);

CREATE INDEX IF NOT EXISTS idx_offers_seen_at ON offers(seen_at);
CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON decisions(decided_at);
"""


class Storage:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def upsert_offer(self, offer: Offer) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO offers(offer_id, body, specialty, locality, center,
                                   hours_per_week, duration, raw_html_hash, seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    body=excluded.body,
                    specialty=excluded.specialty,
                    locality=excluded.locality,
                    center=excluded.center,
                    hours_per_week=excluded.hours_per_week,
                    duration=excluded.duration,
                    raw_html_hash=excluded.raw_html_hash,
                    seen_at=excluded.seen_at
                """,
                (
                    offer.offer_id,
                    offer.body,
                    offer.specialty,
                    offer.locality,
                    offer.center,
                    offer.hours_per_week,
                    offer.duration,
                    offer.raw_html_hash,
                    offer.seen_at.isoformat(),
                ),
            )

    def get_offer(self, offer_id: str) -> Offer | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM offers WHERE offer_id = ?", (offer_id,)
            ).fetchone()
        if row is None:
            return None
        return Offer(
            offer_id=row["offer_id"],
            body=row["body"],
            specialty=row["specialty"],
            locality=row["locality"],
            center=row["center"],
            hours_per_week=row["hours_per_week"],
            duration=row["duration"],
            raw_html_hash=row["raw_html_hash"],
            seen_at=datetime.fromisoformat(row["seen_at"]),
        )

    def mark_preselected(self, offer_id: str, *, preselected: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO decisions(offer_id, preselected, decided_at)
                VALUES (?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    preselected=excluded.preselected,
                    decided_at=excluded.decided_at
                """,
                (offer_id, int(preselected), datetime.now().isoformat()),
            )

    def is_preselected(self, offer_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT preselected FROM decisions WHERE offer_id = ?", (offer_id,)
            ).fetchone()
        return bool(row and row["preselected"])

    def list_preselected_today(self, *, now: datetime) -> list[str]:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT offer_id FROM decisions
                WHERE preselected = 1
                  AND decided_at >= ? AND decided_at < ?
                ORDER BY decided_at ASC
                """,
                (start_of_day.isoformat(), end_of_day.isoformat()),
            ).fetchall()
        return [r["offer_id"] for r in rows]
