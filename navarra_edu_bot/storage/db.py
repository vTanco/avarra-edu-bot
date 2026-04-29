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

CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL,
    kind TEXT NOT NULL,
    level TEXT NOT NULL,
    payload TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS kv_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_offers_seen_at ON offers(seen_at);
CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON decisions(decided_at);
CREATE INDEX IF NOT EXISTS idx_events_ts ON events(ts);
CREATE INDEX IF NOT EXISTS idx_events_kind ON events(kind);
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

    def has_decision(self, offer_id: str) -> bool:
        """True if the user has explicitly chosen apply or discard for this offer.

        Used to skip re-notification across days: an offer with no decision yet
        should keep being notified until the user responds.
        """
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM decisions WHERE offer_id = ?", (offer_id,)
            ).fetchone()
        return row is not None

    # ---------- events ----------

    def log_event(
        self, *, kind: str, level: str = "info", payload: dict | None = None
    ) -> None:
        """Append a structured event row. payload is JSON-serialised."""
        import json
        with self._conn() as conn:
            conn.execute(
                "INSERT INTO events(ts, kind, level, payload) VALUES (?, ?, ?, ?)",
                (
                    datetime.now().isoformat(),
                    kind,
                    level,
                    json.dumps(payload or {}, default=str, ensure_ascii=False),
                ),
            )

    def recent_events(
        self, *, limit: int = 20, kind: str | None = None, level: str | None = None
    ) -> list[dict]:
        """Return the most recent events, newest first."""
        import json
        sql = "SELECT id, ts, kind, level, payload FROM events"
        clauses, args = [], []
        if kind:
            clauses.append("kind = ?")
            args.append(kind)
        if level:
            clauses.append("level = ?")
            args.append(level)
        if clauses:
            sql += " WHERE " + " AND ".join(clauses)
        sql += " ORDER BY id DESC LIMIT ?"
        args.append(limit)
        with self._conn() as conn:
            rows = conn.execute(sql, args).fetchall()
        return [
            {
                "id": r["id"],
                "ts": r["ts"],
                "kind": r["kind"],
                "level": r["level"],
                "payload": json.loads(r["payload"]) if r["payload"] else {},
            }
            for r in rows
        ]

    def prune_events(self, *, keep_days: int = 30) -> int:
        cutoff = (datetime.now() - timedelta(days=keep_days)).isoformat()
        with self._conn() as conn:
            cur = conn.execute("DELETE FROM events WHERE ts < ?", (cutoff,))
            return cur.rowcount

    # ---------- kv_state (cookies, applied_today, etc.) ----------

    def set_state(self, key: str, value: str) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO kv_state(key, value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    value=excluded.value,
                    updated_at=excluded.updated_at
                """,
                (key, value, datetime.now().isoformat()),
            )

    def get_state(self, key: str) -> str | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT value FROM kv_state WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else None

    def get_state_age_seconds(self, key: str) -> float | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT updated_at FROM kv_state WHERE key = ?", (key,)
            ).fetchone()
        if not row:
            return None
        return (datetime.now() - datetime.fromisoformat(row["updated_at"])).total_seconds()

    # ---------- legacy ----------

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
