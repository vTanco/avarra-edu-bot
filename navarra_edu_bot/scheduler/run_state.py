"""Runtime state shared between the run-thursday loop and the Telegram callbacks.

Keeps things the user can query via /status (last poll time, queue size, next
target, etc.) and lets /cancel mutate the queue. All fields are populated by
the main loop and read by the Telegram handlers.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue


@dataclass
class RunState:
    queue: ThursdayQueue
    next_target_ts: Optional[datetime] = None
    last_poll_at: Optional[datetime] = None
    last_fetched_count: int = 0
    applied_today: set[str] = field(default_factory=set)
    convocatoria_ended: bool = False
    discovered_convid: Optional[str] = None
