"""Tests for the HTTP-only polling session.

We don't hit the real Navarra portal here. We test the cookie-injection logic
(the only piece with non-trivial logic that doesn't depend on Playwright or
network IO).
"""
from __future__ import annotations

import aiohttp
import pytest

from navarra_edu_bot.scraper.http_session import _inject_playwright_cookies


async def test_inject_playwright_cookies_basic_count():
    jar = aiohttp.CookieJar(unsafe=True)
    cookies = [
        {"name": "JSESSIONID", "value": "abc123", "domain": "appseducacion.navarra.es"},
        {"name": "KEYCLOAK_SESSION", "value": "kc-456", "domain": "sso.educacion.navarra.es"},
    ]
    n = _inject_playwright_cookies(jar, cookies)
    assert n == 2


async def test_inject_playwright_cookies_groups_by_domain():
    jar = aiohttp.CookieJar(unsafe=True)
    cookies = [
        {"name": "A", "value": "1", "domain": "appseducacion.navarra.es"},
        {"name": "B", "value": "2", "domain": "appseducacion.navarra.es"},
        {"name": "C", "value": "3", "domain": "sso.educacion.navarra.es"},
    ]
    n = _inject_playwright_cookies(jar, cookies)
    # All three should be injected even though two share a domain
    assert n == 3


async def test_inject_playwright_cookies_strips_leading_dot_in_domain():
    jar = aiohttp.CookieJar(unsafe=True)
    cookies = [
        {"name": "wide", "value": "ok", "domain": ".navarra.es"},
    ]
    # Should not crash on dotted (parent-domain) cookies
    n = _inject_playwright_cookies(jar, cookies)
    assert n == 1


async def test_inject_playwright_cookies_skips_entries_without_domain():
    jar = aiohttp.CookieJar(unsafe=True)
    cookies = [
        {"name": "no_dom", "value": "x"},  # missing domain
        {"name": "ok", "value": "y", "domain": "appseducacion.navarra.es"},
    ]
    n = _inject_playwright_cookies(jar, cookies)
    assert n == 1


async def test_inject_playwright_cookies_handles_empty_input():
    jar = aiohttp.CookieJar(unsafe=True)
    assert _inject_playwright_cookies(jar, []) == 0
