from __future__ import annotations

from playwright.async_api import Page

PORTAL_LOGIN_URL = "https://appseducacion.navarra.es/atp/index.xhtml"

# Selectors — adjust after capturing login_page.html in Task 9.
USUARIO_EDUCA_BUTTON = "text=Usuario Educa"
USERNAME_INPUT = "input[name='username']"       # TODO: confirm
PASSWORD_INPUT = "input[name='password']"       # TODO: confirm
SUBMIT_BUTTON = "button[type='submit']"         # TODO: confirm
AUTHENTICATED_MARKER = "text=Adjudicación telemática"  # TODO: confirm


class LoginError(RuntimeError):
    pass


async def login_educa(page: Page, *, username: str, password: str, timeout_ms: int = 15000) -> None:
    await page.goto(PORTAL_LOGIN_URL, timeout=timeout_ms)
    await page.click(USUARIO_EDUCA_BUTTON, timeout=timeout_ms)
    await page.fill(USERNAME_INPUT, username, timeout=timeout_ms)
    await page.fill(PASSWORD_INPUT, password, timeout=timeout_ms)
    await page.click(SUBMIT_BUTTON, timeout=timeout_ms)
    try:
        await page.wait_for_selector(AUTHENTICATED_MARKER, timeout=timeout_ms)
    except Exception as exc:
        raise LoginError("Login did not reach authenticated page in time") from exc
