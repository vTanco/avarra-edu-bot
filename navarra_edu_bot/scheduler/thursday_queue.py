from __future__ import annotations

import asyncio


class ThursdayQueue:
    """Async-safe in-memory queue for offer_ids the user confirmed on Thursday.

    Deduplicates on insert. Snapshot preserves insertion order.
    """

    def __init__(self) -> None:
        self._ids: list[str] = []
        self._seen: set[str] = set()
        self._lock = asyncio.Lock()

    async def add(self, offer_id: str) -> None:
        async with self._lock:
            if offer_id in self._seen:
                return
            self._seen.add(offer_id)
            self._ids.append(offer_id)

    async def remove(self, offer_id: str) -> bool:
        """Remove an offer from the queue. Returns True if it was present."""
        async with self._lock:
            if offer_id not in self._seen:
                return False
            self._seen.discard(offer_id)
            self._ids.remove(offer_id)
            return True

    async def snapshot(self) -> list[str]:
        async with self._lock:
            return list(self._ids)

    async def drain(self) -> list[str]:
        async with self._lock:
            drained = list(self._ids)
            self._ids.clear()
            self._seen.clear()
            return drained

    async def size(self) -> int:
        async with self._lock:
            return len(self._ids)
