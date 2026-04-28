from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import ntplib

logger = logging.getLogger(__name__)


_DEFAULT_SERVERS = (
    "hora.roa.es",
    "pool.ntp.org",
    "time.google.com",
)


def get_ntp_offset(
    server: str = "hora.roa.es", timeout: float = 2.0
) -> float:
    """Return the offset in seconds between local clock and a single NTP server.

    Positive offset means the local clock is behind the NTP server.
    Returns 0.0 if the server is unreachable (graceful degradation).
    """
    try:
        client = ntplib.NTPClient()
        response = client.request(server, version=3, timeout=timeout)
        logger.info("ntp_sync_ok", extra={"server": server, "offset_s": response.offset})
        return float(response.offset)
    except Exception as exc:
        logger.warning("ntp_sync_failed", extra={"server": server, "error": str(exc)})
        return 0.0


def get_robust_ntp_offset(
    servers: tuple[str, ...] = _DEFAULT_SERVERS, timeout: float = 1.5
) -> float:
    """Query multiple NTP servers and return the median offset.

    More resilient than a single server: tolerates one or two timeouts. If all
    servers fail we return 0.0 (fall back to system clock with a logged warning).
    """
    offsets: list[float] = []
    for server in servers:
        try:
            client = ntplib.NTPClient()
            response = client.request(server, version=3, timeout=timeout)
            offsets.append(float(response.offset))
        except Exception as exc:
            logger.warning(
                "ntp_sync_failed", extra={"server": server, "error": str(exc)}
            )

    if not offsets:
        logger.error("ntp_sync_all_failed", extra={"servers": list(servers)})
        return 0.0

    offsets.sort()
    median = offsets[len(offsets) // 2]
    logger.info(
        "ntp_sync_robust",
        extra={"successes": len(offsets), "median_s": median, "all": offsets},
    )
    return median


async def precise_sleep_until(target: datetime, ntp_offset: float) -> None:
    """Sleep until `target` wall-clock time, adjusted by NTP offset.

    Uses coarse sleep for the bulk of the wait and a busy-spin for the last
    10 ms to minimise scheduler jitter.
    """
    target_epoch = target.timestamp() - ntp_offset
    now = datetime.now().timestamp()
    remaining = target_epoch - now
    if remaining <= 0:
        return

    if remaining > 0.05:
        await asyncio.sleep(remaining - 0.01)

    while datetime.now().timestamp() < target_epoch:
        await asyncio.sleep(0)
