from __future__ import annotations

from playwright.async_api import Page

# The portal uses Navarra's SSO. Flow:
# 1. Navigate to /atp/auth/areapersonal.xhtml (requires auth)
# 2. Portal redirects to SSO login (NIF or "Usuario Educa")
# 3. User clicks "Usuario Educa" tab/button
# 4. Fill username + password in SSO form
# 5. Submit → redirected back to areapersonal.xhtml (authenticated)

PORTAL_AREA_PERSONAL_URL = "https://appseducacion.navarra.es/atp/auth/areapersonal.xhtml"

# SSO selectors — these need confirmation on first headed run.
# The SSO page has tabs for authentication methods. "Usuario Educa" is one tab.
USUARIO_EDUCA_BUTTON = "text=Usuario Educa"
USERNAME_INPUT = "input[name='username']"       # TODO: confirm after SSO inspection
PASSWORD_INPUT = "input[name='password']"       # TODO: confirm after SSO inspection
SUBMIT_BUTTON = "button[type='submit']"         # TODO: confirm after SSO inspection

# After successful login, we land on areapersonal.xhtml with user name visible.
AUTHENTICATED_MARKER = "ul.dropdown-user"


class LoginError(RuntimeError):
    pass


async def login_educa(page: Page, *, username: str, password: str, timeout_ms: int = 15000) -> None:
    """Login to Educa portal via SSO and navigate to the personal area with offers."""
    # Navigate to authenticated area — triggers SSO redirect
    await page.goto(PORTAL_AREA_PERSONAL_URL, timeout=timeout_ms)

    # Wait for SSO page to load, then click "Usuario Educa"
    await page.click(USUARIO_EDUCA_BUTTON, timeout=timeout_ms)

    # Fill credentials in SSO form
    await page.fill(USERNAME_INPUT, username, timeout=timeout_ms)
    await page.fill(PASSWORD_INPUT, password, timeout=timeout_ms)
    await page.click(SUBMIT_BUTTON, timeout=timeout_ms)

    # Wait for redirect back to authenticated portal
    try:
        await page.wait_for_selector(AUTHENTICATED_MARKER, timeout=timeout_ms)
    except Exception as exc:
        raise LoginError("Login did not reach authenticated page in time") from exc
