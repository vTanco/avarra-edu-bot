"""HTTP session for lightweight polling.

The Educa portal uses Keycloak SSO that's hard to replicate with raw HTTP (multiple
redirects, hidden form fields, JS-driven IdP selection). Instead of reimplementing
the SSO flow, we:

  1. Run Playwright once to perform the full login.
  2. Extract the resulting cookies.
  3. Inject them into an aiohttp.ClientSession.
  4. Use HTTP-only requests for subsequent polls (~50 MB vs ~200 MB per browser launch).

Cookies are persisted to the storage layer so that container restarts don't lose
the session — useful when Railway recycles the container right before 14:00.

When the session expires (detected by the SessionExpiredError from parser), call
refresh() to re-run the Playwright login.
"""
from __future__ import annotations

import json
import logging
from collections import defaultdict
from typing import Optional

import aiohttp
from playwright.async_api import async_playwright
from yarl import URL

from navarra_edu_bot.scraper.browser import _LOW_MEM_CHROMIUM_ARGS
from navarra_edu_bot.scraper.login import PORTAL_AREA_PERSONAL_URL, login_educa

# Storage state keys.
_COOKIES_KEY = "http_session.cookies"
_COOKIES_MAX_AGE_S = 6 * 3600  # treat persisted cookies older than 6h as stale

PORTAL_SOLICITUDES_URL = "https://appseducacion.navarra.es/atp/auth/solicitudes.xhtml"


class ConvocatoriaEndedError(RuntimeError):
    """Raised when the portal indicates the convocatoria's plazo has finished."""

logger = logging.getLogger(__name__)

_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)


def _inject_playwright_cookies(
    jar: aiohttp.CookieJar, playwright_cookies: list[dict]
) -> int:
    """Inject Playwright-extracted cookies into an aiohttp CookieJar.

    Groups cookies by domain and registers them under a synthetic https URL
    for each domain so aiohttp's domain-matching works on subsequent requests.

    Returns the number of cookies injected.
    """
    by_domain: dict[str, dict[str, str]] = defaultdict(dict)
    for c in playwright_cookies:
        domain = c.get("domain", "").lstrip(".")
        if not domain:
            continue
        by_domain[domain][c["name"]] = c["value"]

    total = 0
    for domain, cookies_dict in by_domain.items():
        url = URL(f"https://{domain}/")
        jar.update_cookies(cookies_dict, response_url=url)
        total += len(cookies_dict)
    return total


class HttpSession:
    """HTTP session that uses Playwright once for login and aiohttp for everything else.

    If a `storage` is given, cookies are persisted across container restarts via the
    `kv_state` table; `try_restore_from_storage()` rebuilds the aiohttp session
    without a Playwright login when the cookies are fresh enough.
    """

    def __init__(
        self,
        *,
        username: str,
        password: str,
        headless: bool = True,
        storage=None,
    ) -> None:
        self.username = username
        self.password = password
        self.headless = headless
        self.storage = storage
        self._session: Optional[aiohttp.ClientSession] = None

    async def try_restore_from_storage(self) -> bool:
        """Rebuild the aiohttp session from previously-saved cookies, no Playwright.

        Returns True if a fresh-enough cookie blob was found and applied. False
        otherwise — caller should call refresh() to do the full login.
        """
        if self.storage is None:
            return False
        age = self.storage.get_state_age_seconds(_COOKIES_KEY)
        if age is None or age > _COOKIES_MAX_AGE_S:
            return False
        raw = self.storage.get_state(_COOKIES_KEY)
        if not raw:
            return False
        try:
            cookies = json.loads(raw)
        except Exception:
            return False
        if not cookies:
            return False

        if self._session is not None:
            await self._session.close()

        jar = aiohttp.CookieJar(unsafe=True)
        injected = _inject_playwright_cookies(jar, cookies)
        self._session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers={"User-Agent": _USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=20),
        )
        logger.info(
            f"http_session: restored {injected} cookies from storage "
            f"(age={age:.0f}s), no Playwright launched"
        )
        return True

    async def refresh(self) -> None:
        """Run a full Playwright login and rebuild the underlying aiohttp session.

        Closes any pre-existing session before rebuilding, so this is safe to
        call repeatedly (e.g. after detecting session expiry). When storage is
        configured, the resulting cookies are persisted for future restarts.
        """
        logger.info("http_session: refreshing cookies via Playwright login")

        if self._session is not None:
            await self._session.close()
            self._session = None

        async with async_playwright() as p:
            browser = await p.chromium.launch(
                headless=self.headless, args=_LOW_MEM_CHROMIUM_ARGS
            )
            try:
                ctx = await browser.new_context(user_agent=_USER_AGENT)
                page = await ctx.new_page()
                await login_educa(
                    page, username=self.username, password=self.password
                )
                playwright_cookies = await ctx.cookies()
            finally:
                await browser.close()

        # unsafe=True: Navarra cookies use subdomains; default jar can be too strict.
        jar = aiohttp.CookieJar(unsafe=True)
        injected = _inject_playwright_cookies(jar, playwright_cookies)

        self._session = aiohttp.ClientSession(
            cookie_jar=jar,
            headers={"User-Agent": _USER_AGENT},
            timeout=aiohttp.ClientTimeout(total=20),
        )

        # Persist for next container restart
        if self.storage is not None:
            try:
                self.storage.set_state(
                    _COOKIES_KEY, json.dumps(playwright_cookies, default=str)
                )
            except Exception as exc:
                logger.warning(f"http_session: failed to persist cookies: {exc}")

        logger.info(f"http_session: extracted {injected} cookies, session ready")

    async def fetch_areapersonal_html(self) -> str:
        """GET the authenticated personal-area page and return its HTML.

        Caller is responsible for parsing and detecting SessionExpiredError; this
        method does not interpret the body, only the HTTP layer.
        """
        if self._session is None:
            raise RuntimeError("HttpSession not initialised; call refresh() first")

        async with self._session.get(
            PORTAL_AREA_PERSONAL_URL, allow_redirects=True
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"areapersonal returned HTTP {resp.status}"
                )
            return await resp.text()

    async def fetch_solicitudes_html(self) -> str:
        """GET the user's submitted solicitudes page and return its HTML.

        Used for idempotency (skip offers already applied) and post-apply
        verification (confirm a fired application landed in the portal).
        """
        if self._session is None:
            raise RuntimeError("HttpSession not initialised; call refresh() first")

        async with self._session.get(
            PORTAL_SOLICITUDES_URL, allow_redirects=True
        ) as resp:
            if resp.status != 200:
                raise RuntimeError(
                    f"solicitudes returned HTTP {resp.status}"
                )
            return await resp.text()

    async def close(self) -> None:
        if self._session is not None:
            await self._session.close()
            self._session = None
