# Fase 4 — Fast-path jueves Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Minimizar latencia en la carrera del jueves a las 14:00:00 pre-autenticando el navegador a las 13:55 y disparando la solicitud con reintento infinito hasta conseguirla.

**Architecture:** Nuevo subpaquete `scheduler/` que gestiona la cola de ofertas confirmadas del jueves, sincronización NTP y un worker `fast_path_worker` que arranca a las 13:55, pre-carga la página de solicitud con email/teléfono ya rellenados y modal abierto, y a las 14:00:00.000 dispara click-añadir + presentar + confirmar. El callback de Telegram los jueves encola en memoria en vez de aplicar inmediatamente. El comando CLI `run-thursday` orquesta polling + worker + retry.

**Tech Stack:** Python 3.12, Playwright (Chromium headless), `ntplib` (nueva dep), asyncio, python-telegram-bot v21, pytest-asyncio.

---

## File Structure

**Nuevos ficheros:**
- `navarra_edu_bot/scheduler/__init__.py` — paquete nuevo
- `navarra_edu_bot/scheduler/thursday_queue.py` — cola en memoria async-safe
- `navarra_edu_bot/scheduler/ntp_sync.py` — offset NTP + precise_sleep_until
- `navarra_edu_bot/scheduler/fast_path_worker.py` — orquesta prewarm + trigger + retry
- `tests/test_thursday_queue.py`
- `tests/test_ntp_sync.py`
- `tests/test_fast_path_worker.py`
- `tests/test_apply_refactor.py` — para las nuevas funciones extraídas

**Ficheros modificados:**
- `navarra_edu_bot/scraper/apply.py` — extraer `prewarm_application_context` y `fire_submission`
- `navarra_edu_bot/telegram_bot/callbacks.py` — diferencia jueves vs resto
- `navarra_edu_bot/cli.py` — añadir comando `run-thursday`
- `pyproject.toml` — añadir `ntplib>=0.4.0`

---

### Task 1: Cola en memoria `ThursdayQueue`

**Files:**
- Create: `navarra_edu_bot/scheduler/__init__.py`
- Create: `navarra_edu_bot/scheduler/thursday_queue.py`
- Test: `tests/test_thursday_queue.py`

- [ ] **Step 1: Crear paquete vacío**

Crear `navarra_edu_bot/scheduler/__init__.py` con contenido vacío:

```python
```

- [ ] **Step 2: Escribir test que falla**

Crear `tests/test_thursday_queue.py`:

```python
import asyncio
import pytest

from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue


async def test_add_and_snapshot_returns_inserted_ids():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121777")
    assert await q.snapshot() == ["121776", "121777"]


async def test_add_deduplicates():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121776")
    assert await q.snapshot() == ["121776"]


async def test_drain_returns_and_clears():
    q = ThursdayQueue()
    await q.add("121776")
    await q.add("121777")
    drained = await q.drain()
    assert drained == ["121776", "121777"]
    assert await q.snapshot() == []


async def test_size_reflects_queue_length():
    q = ThursdayQueue()
    assert await q.size() == 0
    await q.add("121776")
    assert await q.size() == 1


async def test_concurrent_adds_are_safe():
    q = ThursdayQueue()
    await asyncio.gather(*(q.add(f"id{i}") for i in range(50)))
    snap = await q.snapshot()
    assert len(snap) == 50
    assert set(snap) == {f"id{i}" for i in range(50)}
```

- [ ] **Step 3: Ejecutar tests y verificar que fallan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_thursday_queue.py -v`
Expected: `ModuleNotFoundError: No module named 'navarra_edu_bot.scheduler.thursday_queue'`

- [ ] **Step 4: Implementar `ThursdayQueue`**

Crear `navarra_edu_bot/scheduler/thursday_queue.py`:

```python
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
```

- [ ] **Step 5: Ejecutar tests y verificar que pasan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_thursday_queue.py -v`
Expected: 5 passed.

- [ ] **Step 6: Commit**

```bash
git add navarra_edu_bot/scheduler/__init__.py navarra_edu_bot/scheduler/thursday_queue.py tests/test_thursday_queue.py
git commit -m "feat(scheduler): ThursdayQueue async-safe in-memory queue"
```

---

### Task 2: Sincronización NTP + `precise_sleep_until`

**Files:**
- Modify: `pyproject.toml` (añadir `ntplib>=0.4.0`)
- Create: `navarra_edu_bot/scheduler/ntp_sync.py`
- Test: `tests/test_ntp_sync.py`

- [ ] **Step 1: Añadir dependencia**

Editar `pyproject.toml` y añadir `ntplib>=0.4.0` en `dependencies`. La lista queda:

```toml
dependencies = [
    "playwright>=1.44.0",
    "python-telegram-bot>=21.0",
    "pydantic>=2.7.0",
    "pyyaml>=6.0.1",
    "aiohttp>=3.9.0",
    "structlog>=24.1.0",
    "click>=8.1.7",
    "beautifulsoup4>=4.12.0",
    "ntplib>=0.4.0",
]
```

Luego:

```bash
cd /Users/vicente.tancoedu.uah.es/educacion && uv sync
```

- [ ] **Step 2: Escribir test que falla**

Crear `tests/test_ntp_sync.py`:

```python
import asyncio
import time
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from navarra_edu_bot.scheduler.ntp_sync import (
    get_ntp_offset,
    precise_sleep_until,
)


def test_get_ntp_offset_returns_float_on_success():
    fake_response = MagicMock()
    fake_response.offset = 0.123
    fake_client = MagicMock()
    fake_client.request.return_value = fake_response
    with patch("navarra_edu_bot.scheduler.ntp_sync.ntplib.NTPClient", return_value=fake_client):
        offset = get_ntp_offset("hora.roa.es")
    assert offset == 0.123


def test_get_ntp_offset_returns_zero_on_failure():
    fake_client = MagicMock()
    fake_client.request.side_effect = Exception("network down")
    with patch("navarra_edu_bot.scheduler.ntp_sync.ntplib.NTPClient", return_value=fake_client):
        offset = get_ntp_offset("hora.roa.es")
    assert offset == 0.0


async def test_precise_sleep_until_waits_until_target():
    target = datetime.now() + timedelta(milliseconds=200)
    start = time.monotonic()
    await precise_sleep_until(target, ntp_offset=0.0)
    elapsed = time.monotonic() - start
    assert 0.15 < elapsed < 0.35


async def test_precise_sleep_until_returns_immediately_if_past():
    target = datetime.now() - timedelta(seconds=10)
    start = time.monotonic()
    await precise_sleep_until(target, ntp_offset=0.0)
    elapsed = time.monotonic() - start
    assert elapsed < 0.05
```

- [ ] **Step 3: Ejecutar tests y verificar que fallan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_ntp_sync.py -v`
Expected: `ModuleNotFoundError: No module named 'navarra_edu_bot.scheduler.ntp_sync'`

- [ ] **Step 4: Implementar módulo NTP**

Crear `navarra_edu_bot/scheduler/ntp_sync.py`:

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import ntplib

logger = logging.getLogger(__name__)


def get_ntp_offset(server: str = "hora.roa.es", timeout: float = 2.0) -> float:
    """Return the offset in seconds between local clock and NTP server.

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
```

- [ ] **Step 5: Ejecutar tests y verificar que pasan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_ntp_sync.py -v`
Expected: 4 passed.

- [ ] **Step 6: Commit**

```bash
git add pyproject.toml uv.lock navarra_edu_bot/scheduler/ntp_sync.py tests/test_ntp_sync.py
git commit -m "feat(scheduler): NTP offset + precise_sleep_until with busy-spin"
```

---

### Task 3: Refactor `apply.py` — extraer prewarm y fire

**Files:**
- Modify: `navarra_edu_bot/scraper/apply.py`
- Create: `tests/test_apply_refactor.py`

El objetivo es separar la preparación (cosas que pueden hacerse antes de las 14:00) del disparo (acciones a ejecutar exactamente a las 14:00:00.000).

- [ ] **Step 1: Escribir test que falla (sólo verifica imports nuevos)**

Crear `tests/test_apply_refactor.py`:

```python
import inspect

import pytest

from navarra_edu_bot.scraper import apply as apply_mod


def test_prewarm_and_fire_are_exported():
    assert hasattr(apply_mod, "prewarm_application_context")
    assert hasattr(apply_mod, "fire_submission")
    assert inspect.iscoroutinefunction(apply_mod.prewarm_application_context)
    assert inspect.iscoroutinefunction(apply_mod.fire_submission)


def test_apply_to_offers_still_exported_for_backcompat():
    assert hasattr(apply_mod, "apply_to_offers")
    assert inspect.iscoroutinefunction(apply_mod.apply_to_offers)
```

- [ ] **Step 2: Ejecutar tests y verificar que fallan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_apply_refactor.py -v`
Expected: Fallos en los primeros dos asserts (no existen `prewarm_application_context` ni `fire_submission`).

- [ ] **Step 3: Refactorizar `apply.py`**

Reemplazar contenido de `navarra_edu_bot/scraper/apply.py` por:

```python
from __future__ import annotations

import asyncio
import logging

from playwright.async_api import Page

logger = logging.getLogger(__name__)


class ApplicationError(RuntimeError):
    pass


async def prewarm_application_context(
    page: Page,
    *,
    email: str,
    phone: str,
    convid: str = "1204",
    timeout_ms: int = 15000,
) -> None:
    """Navigate to the new-application page, fill email/phone and open the offers modal.

    Leaves the page in a state ready to click 'anadirOfertaBtn' for any target offer.
    Assumes `page` is already authenticated via `login_educa`.
    """
    url = f"https://appseducacion.navarra.es/atp/private/solicitud.xhtml?convid={convid}&action=new"
    logger.info(f"prewarm: navigating to {url}")
    try:
        await page.goto(url, timeout=timeout_ms)
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("prewarm: could not navigate to solicitud.xhtml") from exc

    try:
        await page.fill("input[name='i10:inpEmail']", email, timeout=timeout_ms)
        await page.fill("input[name='i20:inpTfno1']", phone, timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("prewarm: could not fill email/phone") from exc

    try:
        await page.locator("a#elegirOfertasBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#ofertasDisponiblesDialog", state="visible", timeout=timeout_ms)
        await asyncio.sleep(2)
    except Exception as exc:
        raise ApplicationError("prewarm: could not open offers modal") from exc

    logger.info("prewarm: page ready, waiting for fire trigger")


async def fire_submission(
    page: Page,
    *,
    offer_ids: list[str],
    timeout_ms: int = 15000,
) -> int:
    """Click add buttons for target offers, then presentar + confirm.

    Returns the number of offers successfully added. Raises ApplicationError on any
    failure after the add phase (so caller can retry).
    """
    if not offer_ids:
        logger.warning("fire: no offer_ids, skipping")
        return 0

    added_count = 0
    rows = page.locator("#ofertasDisponiblesDtId_data > tr")
    row_count = await rows.count()

    for i in range(row_count):
        row = rows.nth(i)
        cells = row.locator("td")
        if await cells.count() <= 1:
            continue
        row_offer_id = (await cells.nth(1).inner_text()).strip()
        if row_offer_id not in offer_ids:
            continue
        add_btn = row.locator("a[id$=':anadirOfertaBtn']")
        if await add_btn.count() == 0:
            continue
        try:
            await add_btn.click(timeout=timeout_ms)
            added_count += 1
        except Exception as exc:
            logger.error(f"fire: failed to add {row_offer_id}: {exc}")

    if added_count == 0:
        raise ApplicationError(f"fire: none of {offer_ids} were addable")

    close_modal_btn = page.locator("#ofertasDisponiblesDialog button.close")
    if await close_modal_btn.count() > 0:
        await close_modal_btn.click()
        await asyncio.sleep(0.3)

    try:
        await page.locator("a#presentarSolicitudBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#presentarDlg", state="visible", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("fire: could not click presentar") from exc

    try:
        await page.locator("button#doSaveSolicitudBtn").click(timeout=timeout_ms)
        await page.wait_for_selector("#presentarDlg", state="hidden", timeout=timeout_ms)
        await page.wait_for_load_state("networkidle", timeout=timeout_ms)
    except Exception as exc:
        raise ApplicationError("fire: could not confirm") from exc

    logger.info(f"fire: submitted {added_count} offers")
    return added_count


async def apply_to_offers(
    page: Page,
    *,
    offer_ids: list[str],
    email: str,
    phone: str,
    convid: str = "1204",
    timeout_ms: int = 15000,
) -> None:
    """Backwards-compatible wrapper: prewarm + fire in sequence."""
    if not offer_ids:
        logger.info("No offers to apply to.")
        return
    await prewarm_application_context(
        page, email=email, phone=phone, convid=convid, timeout_ms=timeout_ms,
    )
    await fire_submission(page, offer_ids=offer_ids, timeout_ms=timeout_ms)


async def apply_single_offer_flow(
    offer_id: str, email: str, phone: str, convid: str = "1204",
) -> None:
    """Launch browser, login, apply to a single offer, close. Used by non-Thursday callbacks."""
    from playwright.async_api import async_playwright

    from navarra_edu_bot.config.keychain import read_secret
    from navarra_edu_bot.scraper.login import login_educa

    username = read_secret("educa-username")
    password = read_secret("educa-password")
    if not username or not password:
        raise ApplicationError("Credentials not found in keychain.")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await login_educa(page, username=username, password=password)
            await apply_to_offers(
                page, offer_ids=[offer_id], email=email, phone=phone, convid=convid,
            )
        finally:
            await browser.close()
```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_apply_refactor.py -v`
Expected: 2 passed.

Adicionalmente, ejecutar el resto de tests para asegurar no-regresión:

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest -v`
Expected: todos verdes (los 24 anteriores + 2 nuevos = 26).

- [ ] **Step 5: Commit**

```bash
git add navarra_edu_bot/scraper/apply.py tests/test_apply_refactor.py
git commit -m "refactor(apply): split into prewarm_application_context + fire_submission"
```

---

### Task 4: Worker fast-path con retry infinito

**Files:**
- Create: `navarra_edu_bot/scheduler/fast_path_worker.py`
- Test: `tests/test_fast_path_worker.py`

- [ ] **Step 1: Escribir test que falla**

Crear `tests/test_fast_path_worker.py`:

```python
from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue


@pytest.fixture
def fake_browser():
    """Returns (async_playwright_cm, browser, context, page) all as AsyncMocks."""
    page = AsyncMock()
    context = AsyncMock()
    context.new_page = AsyncMock(return_value=page)
    browser = AsyncMock()
    browser.new_context = AsyncMock(return_value=context)
    browser.close = AsyncMock()
    chromium = AsyncMock()
    chromium.launch = AsyncMock(return_value=browser)
    pw = AsyncMock()
    pw.chromium = chromium
    cm = MagicMock()
    cm.__aenter__ = AsyncMock(return_value=pw)
    cm.__aexit__ = AsyncMock(return_value=None)
    return cm, browser, context, page


async def test_run_fast_path_succeeds_on_first_try(fake_browser):
    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=50)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()) as login, \
         patch(
             "navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context",
             new=AsyncMock(),
         ) as prewarm, \
         patch(
             "navarra_edu_bot.scheduler.fast_path_worker.fire_submission",
             new=AsyncMock(return_value=1),
         ) as fire, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=3,
        )

    assert added == 1
    assert login.await_count == 1
    assert prewarm.await_count == 1
    assert fire.await_count == 1


async def test_run_fast_path_retries_on_fire_failure(fake_browser):
    from navarra_edu_bot.scraper.apply import ApplicationError

    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=20)

    fire_mock = AsyncMock(side_effect=[ApplicationError("boom"), ApplicationError("boom"), 1])

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=fire_mock), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=5,
            retry_backoff_s=0.01,
        )

    assert added == 1
    assert fire_mock.await_count == 3


async def test_run_fast_path_aborts_when_queue_empty(fake_browser):
    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    target = datetime.now() + timedelta(milliseconds=20)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()) as login, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()) as prewarm, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=AsyncMock()) as fire, \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=3,
        )

    assert added == 0
    assert login.await_count == 0
    assert prewarm.await_count == 0
    assert fire.await_count == 0


async def test_run_fast_path_gives_up_after_max_retries(fake_browser):
    from navarra_edu_bot.scraper.apply import ApplicationError

    cm, browser, context, page = fake_browser
    queue = ThursdayQueue()
    await queue.add("121776")
    target = datetime.now() + timedelta(milliseconds=10)

    with patch("navarra_edu_bot.scheduler.fast_path_worker.async_playwright", return_value=cm), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.login_educa", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.prewarm_application_context", new=AsyncMock()), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.fire_submission", new=AsyncMock(side_effect=ApplicationError("boom"))), \
         patch("navarra_edu_bot.scheduler.fast_path_worker.get_ntp_offset", return_value=0.0):
        added = await run_fast_path(
            queue=queue,
            target_ts=target,
            username="u", password="p",
            email="e@x", phone="1",
            convid="1204",
            max_retries=2,
            retry_backoff_s=0.01,
        )

    assert added == 0
```

- [ ] **Step 2: Ejecutar tests y verificar que fallan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_fast_path_worker.py -v`
Expected: `ModuleNotFoundError: No module named 'navarra_edu_bot.scheduler.fast_path_worker'`

- [ ] **Step 3: Implementar worker**

Crear `navarra_edu_bot/scheduler/fast_path_worker.py`:

```python
from __future__ import annotations

import asyncio
import logging
from datetime import datetime

from playwright.async_api import async_playwright

from navarra_edu_bot.scheduler.ntp_sync import get_ntp_offset, precise_sleep_until
from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.scraper.apply import (
    ApplicationError,
    fire_submission,
    prewarm_application_context,
)
from navarra_edu_bot.scraper.login import login_educa

logger = logging.getLogger(__name__)


async def run_fast_path(
    *,
    queue: ThursdayQueue,
    target_ts: datetime,
    username: str,
    password: str,
    email: str,
    phone: str,
    convid: str = "1204",
    max_retries: int = 10,
    retry_backoff_s: float = 0.5,
    headless: bool = True,
) -> int:
    """Run the Thursday fast-path:
      - Launch browser, login, prewarm page (navigate + fill + open modal).
      - precise_sleep_until(target_ts).
      - Fire submission with queue snapshot.
      - On any ApplicationError after fire, retry: relogin + prewarm + fire, up to max_retries.

    Returns the number of offers successfully submitted.
    """
    offer_ids = await queue.snapshot()
    if not offer_ids:
        logger.warning("fast_path: queue is empty, aborting")
        return 0

    ntp_offset = get_ntp_offset()
    logger.info(f"fast_path: starting with {len(offer_ids)} offers, ntp_offset={ntp_offset:.3f}s")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        try:
            attempt = 0
            prewarmed = False
            page = None
            while attempt < max_retries:
                attempt += 1
                try:
                    if not prewarmed:
                        context = await browser.new_context()
                        page = await context.new_page()
                        await login_educa(page, username=username, password=password)
                        await prewarm_application_context(
                            page, email=email, phone=phone, convid=convid,
                        )
                        prewarmed = True
                        logger.info(f"fast_path: prewarmed on attempt {attempt}")

                    if attempt == 1:
                        await precise_sleep_until(target_ts, ntp_offset=ntp_offset)

                    current_ids = await queue.snapshot()
                    if not current_ids:
                        logger.warning("fast_path: queue emptied before fire, aborting")
                        return 0

                    added = await fire_submission(page, offer_ids=current_ids)
                    logger.info(f"fast_path: submitted {added} offers on attempt {attempt}")
                    return added

                except ApplicationError as exc:
                    logger.warning(f"fast_path: attempt {attempt} failed: {exc}")
                    prewarmed = False
                    if attempt >= max_retries:
                        logger.error("fast_path: exhausted retries")
                        return 0
                    await asyncio.sleep(retry_backoff_s)
                except Exception as exc:
                    logger.exception(f"fast_path: unexpected error on attempt {attempt}: {exc}")
                    prewarmed = False
                    if attempt >= max_retries:
                        return 0
                    await asyncio.sleep(retry_backoff_s)
            return 0
        finally:
            await browser.close()
```

- [ ] **Step 4: Ejecutar tests y verificar que pasan**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest tests/test_fast_path_worker.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add navarra_edu_bot/scheduler/fast_path_worker.py tests/test_fast_path_worker.py
git commit -m "feat(scheduler): fast_path_worker with NTP-timed trigger and infinite retry"
```

---

### Task 5: Callback Telegram diferencia jueves

**Files:**
- Modify: `navarra_edu_bot/telegram_bot/callbacks.py`

La idea es que el callback reciba una `ThursdayQueue` opcional. Si hoy es jueves y la cola existe → encolar. Si no → comportamiento actual (apply inmediato).

- [ ] **Step 1: Modificar `build_callback_handler`**

Reemplazar contenido de `navarra_edu_bot/telegram_bot/callbacks.py` por:

```python
from __future__ import annotations

from datetime import datetime

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
from navarra_edu_bot.storage.db import Storage

log = structlog.get_logger()


def build_callback_handler(
    storage: Storage,
    thursday_queue: ThursdayQueue | None = None,
) -> CallbackQueryHandler:
    async def _handle(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        if query is None or query.data is None:
            return
        await query.answer()

        try:
            action, offer_id = query.data.split(":", 1)
        except ValueError:
            log.warning("bad_callback_data", data=query.data)
            return

        if action == "apply":
            storage.mark_preselected(offer_id, preselected=True)

            is_thursday = datetime.now().weekday() == 3
            if is_thursday and thursday_queue is not None:
                await thursday_queue.add(offer_id)
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n⏳ <b>Encolada para las 14:00</b>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
                log.info("thursday_queued", offer_id=offer_id)
                return

            await query.edit_message_text(
                f"{query.message.text_html}\n\n⏳ <b>Aplicando...</b>",
                parse_mode="HTML",
                reply_markup=None,
            )
            try:
                from navarra_edu_bot.scraper.apply import apply_single_offer_flow
                await apply_single_offer_flow(
                    offer_id=offer_id,
                    email="vicente.tanco@edu.uah.es",
                    phone="681864143",
                )
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n✅ <b>Solicitud Presentada</b>",
                    parse_mode="HTML",
                    reply_markup=None,
                )
            except Exception as e:
                log.error("apply_failed", error=str(e))
                await query.edit_message_text(
                    f"{query.message.text_html}\n\n❌ <b>Error al aplicar:</b> {e}",
                    parse_mode="HTML",
                    reply_markup=None,
                )
        elif action == "discard":
            storage.mark_preselected(offer_id, preselected=False)
            await query.edit_message_text(
                f"{query.message.text_html}\n\n❌ Descartada",
                parse_mode="HTML",
                reply_markup=None,
            )
        else:
            log.warning("unknown_action", action=action)

    return CallbackQueryHandler(_handle)
```

- [ ] **Step 2: Ejecutar tests y verificar no-regresión**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest -v`
Expected: todo verde. `build_callback_handler(storage)` sigue funcionando (el parámetro nuevo tiene default `None`).

- [ ] **Step 3: Commit**

```bash
git add navarra_edu_bot/telegram_bot/callbacks.py
git commit -m "feat(telegram): Thursday callbacks enqueue instead of applying immediately"
```

---

### Task 6: Comando CLI `run-thursday`

**Files:**
- Modify: `navarra_edu_bot/cli.py`

- [ ] **Step 1: Añadir comando `run-thursday` al final de cli.py**

Editar `navarra_edu_bot/cli.py` y añadir antes de la línea `if __name__ == "__main__":`:

```python
@main.command("run-thursday")
@click.option("--headless/--headed", default=True)
@click.option("--target-hour", default=14, type=int, help="Hora objetivo (default 14)")
@click.option("--target-minute", default=0, type=int, help="Minuto objetivo (default 0)")
@click.option("--prewarm-seconds-before", default=300, type=int,
              help="Segundos antes del target para iniciar prewarm (default 300 = 5min)")
@click.option("--convid", default="1204")
@click.option("--email", default="vicente.tanco@edu.uah.es")
@click.option("--phone", default="681864143")
def run_thursday(
    headless: bool,
    target_hour: int,
    target_minute: int,
    prewarm_seconds_before: int,
    convid: str,
    email: str,
    phone: str,
) -> None:
    """Thursday fast-path: poll + notify 13:30-14:00, prewarm at 13:55, fire at 14:00."""
    from datetime import datetime, timedelta
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scheduler.fast_path_worker import run_fast_path
    from navarra_edu_bot.scheduler.thursday_queue import ThursdayQueue
    from navarra_edu_bot.scraper.fetch import fetch_offers
    from navarra_edu_bot.storage.db import Storage
    from navarra_edu_bot.telegram_bot.callbacks import build_callback_handler
    from navarra_edu_bot.telegram_bot.client import build_bot_app
    from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

    cfg = load_config(Path("~/.navarra-edu-bot/config.yaml").expanduser())
    storage = Storage(cfg.runtime.storage_path)
    storage.init_schema()

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    queue = ThursdayQueue()
    app = build_bot_app(token=token, chat_id=chat_id)
    app.add_handler(build_callback_handler(storage, thursday_queue=queue))

    now = datetime.now()
    target_ts = now.replace(hour=target_hour, minute=target_minute, second=0, microsecond=0)
    if target_ts <= now:
        target_ts = target_ts + timedelta(days=1)
    prewarm_start = target_ts - timedelta(seconds=prewarm_seconds_before)

    click.echo(f"Target: {target_ts.isoformat()}  Prewarm start: {prewarm_start.isoformat()}")

    async def _poll_until(deadline: datetime) -> None:
        seen: set[str] = set()
        while datetime.now() < deadline:
            try:
                offers = await fetch_offers(
                    username=username, password=password, headless=headless,
                )
                async def _send(offer):
                    if offer.offer_id in seen:
                        return
                    seen.add(offer.offer_id)
                    await app.bot.send_message(
                        chat_id=chat_id,
                        text=format_offer_message(offer),
                        reply_markup=offer_buttons(offer),
                        parse_mode="HTML",
                    )
                await notify_new_offers(
                    offers=offers, now=datetime.now(), config=cfg,
                    storage=storage, send=_send,
                )
            except Exception as exc:
                click.echo(f"poll error: {exc}")
            await asyncio.sleep(60)

    async def _run() -> None:
        async with app:
            await app.start()
            await app.updater.start_polling()
            try:
                await _poll_until(prewarm_start)

                click.echo("Starting prewarm + fast-path...")
                submitted = await run_fast_path(
                    queue=queue,
                    target_ts=target_ts,
                    username=username,
                    password=password,
                    email=email,
                    phone=phone,
                    convid=convid,
                    max_retries=60,
                    retry_backoff_s=1.0,
                    headless=headless,
                )
                click.echo(f"fast-path submitted {submitted} offers")

                await asyncio.sleep(60)
            finally:
                await app.updater.stop()
                await app.stop()

    asyncio.run(_run())
```

- [ ] **Step 2: Verificar que el comando aparece en `--help`**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run navarra-edu-bot --help`
Expected: aparece `run-thursday` en la lista de comandos.

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run navarra-edu-bot run-thursday --help`
Expected: ayuda del comando con todas las opciones.

- [ ] **Step 3: Ejecutar toda la suite de tests**

Run: `cd /Users/vicente.tancoedu.uah.es/educacion && uv run pytest -v`
Expected: todos verdes.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/cli.py
git commit -m "feat(cli): run-thursday orchestrates poll + prewarm + fire"
```

---

### Task 7: Prueba de integración manual (dry-check)

**Files:**
- Create: `scripts/test_fast_path_dry.py`

Este script valida el flujo completo **sin llegar a `doSaveSolicitudBtn`**. Es la última línea de defensa antes de confiar en el bot un jueves real.

- [ ] **Step 1: Crear el script**

Crear `scripts/test_fast_path_dry.py`:

```python
"""Dry-run del flujo fast-path jueves (sin submit final).

Uso:
    uv run python scripts/test_fast_path_dry.py <offer_id>

Lo que hace:
    1. Login headed (visible).
    2. prewarm_application_context (navega, rellena, abre modal).
    3. Espera 3 segundos.
    4. fire_submission MODIFICADO: sólo clicks anadir + presentar. NO confirma.
    5. Deja el browser abierto 15 segundos para inspección visual.
"""
from __future__ import annotations

import asyncio
import logging
import sys

from playwright.async_api import async_playwright

from navarra_edu_bot.config.keychain import read_secret
from navarra_edu_bot.scraper.apply import prewarm_application_context
from navarra_edu_bot.scraper.login import login_educa

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


async def main(offer_id: str) -> None:
    username = read_secret("educa-username")
    password = read_secret("educa-password")
    if not username or not password:
        logger.error("Missing credentials in keychain")
        sys.exit(1)

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await login_educa(page, username=username, password=password)
            await prewarm_application_context(
                page,
                email="vicente.tanco@edu.uah.es",
                phone="681864143",
            )
            logger.info("Prewarm OK. Waiting 3s to simulate trigger delay.")
            await asyncio.sleep(3)

            rows = page.locator("#ofertasDisponiblesDtId_data > tr")
            row_count = await rows.count()
            clicked = False
            for i in range(row_count):
                cells = rows.nth(i).locator("td")
                if await cells.count() <= 1:
                    continue
                row_id = (await cells.nth(1).inner_text()).strip()
                if row_id == offer_id:
                    add_btn = rows.nth(i).locator("a[id$=':anadirOfertaBtn']")
                    if await add_btn.count() > 0:
                        await add_btn.click()
                        clicked = True
                        break
            if not clicked:
                logger.warning(f"Offer {offer_id} not found in modal")
            else:
                logger.info(f"Added offer {offer_id}. STOPPING HERE (no presentar, no confirm).")

            logger.info("Keeping browser open 15s for visual inspection.")
            await asyncio.sleep(15)
        finally:
            await browser.close()


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Usage: python scripts/test_fast_path_dry.py <offer_id>")
        sys.exit(1)
    asyncio.run(main(sys.argv[1]))
```

- [ ] **Step 2: Ejecutar el script manualmente (sólo el humano)**

Este paso requiere una oferta activa y validación humana visual. **No lo ejecuta el subagent**, se anota como TODO para el usuario.

```bash
cd /Users/vicente.tancoedu.uah.es/educacion
mkdir -p scripts
# Ejecutar con offer_id real:
uv run python scripts/test_fast_path_dry.py 121776
```

Comprobar visualmente:
- Login correcto.
- Página `solicitud.xhtml` cargada.
- Email y teléfono rellenados.
- Modal `ofertasDisponiblesDialog` abierto.
- La oferta objetivo aparece listada.
- Al click en "añadir", la oferta pasa al panel de ofertas seleccionadas.
- El browser permanece abierto 15s sin llegar a presentar ni confirmar.

- [ ] **Step 3: Commit del script**

```bash
git add scripts/test_fast_path_dry.py
git commit -m "chore(scripts): dry-run script for Thursday fast-path without submit"
```

---

## Post-Implementation Notes

**Uso real el jueves:**
```bash
# Lanzar a las 13:25 del jueves (da 5 min de colchón):
uv run navarra-edu-bot run-thursday --headless
```

**Limitaciones conocidas (aceptadas en esta fase):**
- La cola vive en memoria: si el proceso muere entre 13:30 y 14:00, se pierden las confirmaciones.
- Retry serial (no contextos paralelos). Si la carrera lo requiere, añadir `N` contextos warm en una iteración futura.
- `convid=1204` sigue siendo default; el jueves relevante habrá que ajustarlo si cambia de convocatoria.
- Email/phone hardcodeados como valores default del CLI (decisión consciente del usuario).

**Tras ejecutar el primer jueves real:**
- Medir latencia entre `target_ts` y el timestamp del primer click (loggear).
- Si >500ms, evaluar pasar a POST directo (skip clicks) vía `page.request.post()` con tokens de JSF.
