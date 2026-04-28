"""External watchdog ping (Healthchecks.io or compatible).

Set HEALTHCHECK_PING_URL in the environment. Each call hits that URL with
optional `/start`, `/fail` suffixes. If the env var is missing, this module
is a no-op — nothing breaks.

Healthchecks.io free tier (https://healthchecks.io) gives 20 checks for free,
which is plenty. Configure a daily check expecting a ping by 14:10 every day;
if the bot dies, you get an email.
"""
from __future__ import annotations

import logging
import os
from typing import Optional

import aiohttp

logger = logging.getLogger(__name__)

_ENV_VAR = "HEALTHCHECK_PING_URL"


def _base_url() -> Optional[str]:
    url = os.environ.get(_ENV_VAR, "").strip()
    return url or None


async def ping(suffix: str = "", *, timeout: float = 5.0, payload: str = "") -> bool:
    """Hit the configured healthcheck URL. Returns True on 2xx, False otherwise.

    suffix can be "", "/start", "/fail" or "/{exit_code}". Healthchecks.io
    treats /start as "running" and /fail as "alert me".
    """
    base = _base_url()
    if not base:
        return False
    url = base + suffix
    try:
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=timeout)
        ) as session:
            async with session.post(url, data=payload.encode("utf-8") if payload else None) as resp:
                ok = 200 <= resp.status < 300
                if not ok:
                    logger.warning(
                        f"healthcheck ping {suffix or '(success)'} -> HTTP {resp.status}"
                    )
                return ok
    except Exception as exc:
        logger.warning(f"healthcheck ping {suffix or '(success)'} failed: {exc}")
        return False


async def ping_success(payload: str = "") -> bool:
    """Successful heartbeat — the bot is alive."""
    return await ping("", payload=payload)


async def ping_start(payload: str = "") -> bool:
    """Mark the start of a long task; pair with ping_success/ping_fail when done."""
    return await ping("/start", payload=payload)


async def ping_fail(payload: str = "") -> bool:
    """Tell the watchdog something went wrong."""
    return await ping("/fail", payload=payload)
