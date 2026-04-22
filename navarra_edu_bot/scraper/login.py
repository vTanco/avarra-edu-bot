from __future__ import annotations

from playwright.async_api import Page

# The portal uses Navarra's SSO (Keycloak). Flow:
# 1. Navigate to /atp/auth/areapersonal.xhtml (requires auth)
# 2. Portal redirects to SSO at sso.educacion.navarra.es
# 3. SSO shows identity provider selection; user clicks "Usuario Educa"
# 4. Keycloak login form: form#kc-form-login with input#username, input#password, input#kc-login
# 5. Submit → redirected back to areapersonal.xhtml (authenticated)

PORTAL_AREA_PERSONAL_URL = "https://appseducacion.navarra.es/atp/auth/areapersonal.xhtml"

# SSO selectors (confirmed from captured sso_educa_form.html 2026-04-22)
USUARIO_EDUCA_BUTTON = "text=Usuario Educa"
USERNAME_INPUT = "input#username"
PASSWORD_INPUT = "input#password"
SUBMIT_BUTTON = "input#kc-login"

# After successful login, we land on areapersonal.xhtml.
# The logout link only exists when authenticated.
AUTHENTICATED_MARKER = "a[href='/atp/logout.xhtml']"


class LoginError(RuntimeError):
    pass


async def login_educa(page: Page, *, username: str, password: str, timeout_ms: int = 15000) -> None:
    """Login to Educa portal via Keycloak SSO and navigate to the personal area with offers."""
    # Navigate to authenticated area — triggers SSO redirect
    await page.goto(PORTAL_AREA_PERSONAL_URL, timeout=timeout_ms)

    # Wait for SSO page to load, then click "Usuario Educa" identity provider
    await page.click(USUARIO_EDUCA_BUTTON, timeout=timeout_ms)

    # Fill credentials in Keycloak login form
    await page.fill(USERNAME_INPUT, username, timeout=timeout_ms)
    await page.fill(PASSWORD_INPUT, password, timeout=timeout_ms)
    await page.click(SUBMIT_BUTTON, timeout=timeout_ms)

    # Wait for redirect back to authenticated portal
    # The logout link is inside a collapsed dropdown, so it's in the DOM but hidden.
    # Use state='attached' to check DOM presence rather than visibility.
    try:
        await page.wait_for_selector(AUTHENTICATED_MARKER, state="attached", timeout=timeout_ms)
    except Exception as exc:
        raise LoginError("Login did not reach authenticated page in time") from exc
