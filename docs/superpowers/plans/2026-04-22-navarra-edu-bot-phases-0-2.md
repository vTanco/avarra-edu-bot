# Navarra Edu Bot — Plan de Implementación (Fases 0–2)

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar un bot local en macOS que, de L–V entre 13:30 y 14:00, detecte ofertas en el portal de adjudicación telemática de Navarra, las filtre según elegibilidad y ranking, y notifique al usuario por Telegram con botones inline — **sin aplicar todavía** (submit llegará en Fases 3–5).

**Architecture:** Python 3.12 + Playwright (Chromium) para scraping, python-telegram-bot v21 (async) para notificación interactiva, SQLite para persistencia, macOS Keychain para credenciales, Pydantic v2 para config validada. Módulos desacoplados por responsabilidad (`scraper`, `filter`, `telegram_bot`, `config`, `storage`), cada uno testeado en aislamiento con fixtures HTML.

**Tech Stack:** Python 3.12, uv (package manager), Playwright, python-telegram-bot 21.x, Pydantic 2.x, pytest + pytest-asyncio, aiohttp, structlog.

**Spec de referencia:** [`docs/superpowers/specs/2026-04-22-navarra-edu-bot-design.md`](../specs/2026-04-22-navarra-edu-bot-design.md)

---

## Estructura de ficheros

```
educacion/
├── pyproject.toml                    # uv + dependencias + pytest config
├── .gitignore
├── .python-version                   # 3.12
├── config.example.yaml               # Plantilla de configuración
├── README.md                         # Setup y uso
├── navarra_edu_bot/
│   ├── __init__.py
│   ├── __main__.py                   # `python -m navarra_edu_bot`
│   ├── cli.py                        # Subcomandos: fetch, ping, test
│   ├── config/
│   │   ├── __init__.py
│   │   ├── schema.py                 # Pydantic models
│   │   ├── loader.py                 # Carga YAML + valida
│   │   └── keychain.py               # Wrapper `security` CLI
│   ├── storage/
│   │   ├── __init__.py
│   │   ├── db.py                     # Conexión SQLite + migraciones
│   │   └── models.py                 # Dataclasses Offer, Decision
│   ├── scraper/
│   │   ├── __init__.py
│   │   ├── browser.py                # Contexto Playwright
│   │   ├── login.py                  # Login Educa
│   │   ├── parser.py                 # HTML → Offer
│   │   └── fetch.py                  # Orquesta login + parse
│   ├── filter/
│   │   ├── __init__.py
│   │   ├── eligibility.py            # Reglas por día de la semana
│   │   └── ranker.py                 # Ordena y puntúa
│   ├── telegram_bot/
│   │   ├── __init__.py
│   │   ├── client.py                 # Inicialización bot
│   │   ├── formatter.py              # Oferta → mensaje + botones
│   │   └── callbacks.py              # Manejo pulsaciones
│   └── orchestrator.py               # Integra fetch→filter→notify
├── tests/
│   ├── conftest.py
│   ├── fixtures/
│   │   ├── login_page.html
│   │   ├── offers_list.html
│   │   ├── offers_empty.html
│   │   └── session_expired.html
│   ├── test_config_schema.py
│   ├── test_keychain.py
│   ├── test_storage.py
│   ├── test_scraper_parser.py
│   ├── test_filter_eligibility.py
│   ├── test_filter_ranker.py
│   ├── test_telegram_formatter.py
│   └── test_orchestrator.py
└── docs/
    ├── formacion-especialidades.md   # Investigación RD 276/2007, RD 800/2022
    ├── superpowers/
    │   ├── specs/…
    │   └── plans/…
    └── runbook.md                    # Cómo arrancar, debug, restaurar
```

---

## FASE 0 — Scaffold (Tareas 1–5)

### Task 1: Inicializar repositorio y dependencias

**Files:**
- Create: `pyproject.toml`
- Create: `.gitignore`
- Create: `.python-version`
- Create: `README.md`

- [ ] **Step 1: Inicializar Git**

```bash
cd /Users/vicente.tancoedu.uah.es/educacion
git init
git branch -M main
```

- [ ] **Step 2: Crear `.python-version`**

Crea `/Users/vicente.tancoedu.uah.es/educacion/.python-version` con contenido:

```
3.12
```

- [ ] **Step 3: Crear `pyproject.toml`**

Crea `/Users/vicente.tancoedu.uah.es/educacion/pyproject.toml`:

```toml
[project]
name = "navarra-edu-bot"
version = "0.1.0"
description = "Automated bidding for Navarra education telematic adjudication"
requires-python = ">=3.12"
dependencies = [
    "playwright>=1.44.0",
    "python-telegram-bot>=21.0",
    "pydantic>=2.7.0",
    "pyyaml>=6.0.1",
    "aiohttp>=3.9.0",
    "structlog>=24.1.0",
    "click>=8.1.7",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.2.0",
    "pytest-asyncio>=0.23.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.4.0",
]

[project.scripts]
navarra-edu-bot = "navarra_edu_bot.cli:main"

[tool.pytest.ini_options]
asyncio_mode = "auto"
testpaths = ["tests"]

[tool.ruff]
line-length = 100
target-version = "py312"
```

- [ ] **Step 4: Crear `.gitignore`**

Crea `/Users/vicente.tancoedu.uah.es/educacion/.gitignore`:

```
__pycache__/
*.py[cod]
*.egg-info/
.venv/
.pytest_cache/
.coverage
htmlcov/
*.db
*.log
.DS_Store
config.yaml
!config.example.yaml
```

- [ ] **Step 5: Crear README.md mínimo**

Crea `/Users/vicente.tancoedu.uah.es/educacion/README.md`:

```markdown
# Navarra Edu Bot

Local macOS automation for the Navarra education telematic adjudication portal.

See [design spec](docs/superpowers/specs/2026-04-22-navarra-edu-bot-design.md) for details.

## Setup

```bash
uv venv
uv pip install -e ".[dev]"
playwright install chromium
```

## Usage

TBD during implementation.
```

- [ ] **Step 6: Instalar uv y crear venv**

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
cd /Users/vicente.tancoedu.uah.es/educacion
uv venv
source .venv/bin/activate
uv pip install -e ".[dev]"
playwright install chromium
```

Expected: venv created, deps installed, Chromium downloaded.

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .python-version README.md
git commit -m "chore: initialize project with pyproject.toml and deps"
```

---

### Task 2: Crear estructura de paquetes

**Files:**
- Create: `navarra_edu_bot/__init__.py`
- Create: `navarra_edu_bot/__main__.py`
- Create: `navarra_edu_bot/cli.py`
- Create: `navarra_edu_bot/config/__init__.py`
- Create: `navarra_edu_bot/storage/__init__.py`
- Create: `navarra_edu_bot/scraper/__init__.py`
- Create: `navarra_edu_bot/filter/__init__.py`
- Create: `navarra_edu_bot/telegram_bot/__init__.py`
- Create: `tests/__init__.py`
- Create: `tests/conftest.py`

- [ ] **Step 1: Crear todos los `__init__.py` vacíos**

```bash
cd /Users/vicente.tancoedu.uah.es/educacion
mkdir -p navarra_edu_bot/{config,storage,scraper,filter,telegram_bot}
mkdir -p tests/fixtures
touch navarra_edu_bot/__init__.py
touch navarra_edu_bot/config/__init__.py
touch navarra_edu_bot/storage/__init__.py
touch navarra_edu_bot/scraper/__init__.py
touch navarra_edu_bot/filter/__init__.py
touch navarra_edu_bot/telegram_bot/__init__.py
touch tests/__init__.py
```

- [ ] **Step 2: Crear `navarra_edu_bot/cli.py` con stub**

Contenido:

```python
import click


@click.group()
def main() -> None:
    """Navarra Edu Bot CLI."""


@main.command()
def ping() -> None:
    """Healthcheck ping."""
    click.echo("pong")


if __name__ == "__main__":
    main()
```

- [ ] **Step 3: Crear `navarra_edu_bot/__main__.py`**

Contenido:

```python
from navarra_edu_bot.cli import main

if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Crear `tests/conftest.py`**

Contenido:

```python
from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR
```

- [ ] **Step 5: Verificar CLI arranca**

```bash
python -m navarra_edu_bot ping
```

Expected: `pong`

- [ ] **Step 6: Commit**

```bash
git add navarra_edu_bot tests
git commit -m "feat(scaffold): create package structure and CLI stub"
```

---

### Task 3: Crear bot de Telegram y guardar token en Keychain

**Files:**
- Modify: `README.md` (añadir setup Telegram)
- Create: `config.example.yaml`

- [ ] **Step 1: Crear bot con @BotFather en Telegram (manual)**

Instrucciones para el usuario (documentar en el commit message):

1. Abrir Telegram, buscar `@BotFather`.
2. Enviar `/newbot`.
3. Nombre del bot: "Navarra Edu Bot".
4. Username (debe terminar en `bot`): p. ej. `navarra_edu_vt_bot`.
5. Copiar el token que devuelve (formato `123456789:ABC-DEF…`).
6. Enviar `/setprivacy` → seleccionar el bot → `Disable` (para que reciba callbacks en grupos, opcional).

- [ ] **Step 2: Guardar token en Keychain**

```bash
security add-generic-password \
  -s "navarra-edu-bot" \
  -a "telegram-token" \
  -w "TOKEN_AQUI" \
  -U
```

- [ ] **Step 3: Guardar chat_id del usuario**

El usuario tiene que enviar `/start` al bot primero. Luego:

```bash
TOKEN=$(security find-generic-password -s "navarra-edu-bot" -a "telegram-token" -w)
curl -s "https://api.telegram.org/bot${TOKEN}/getUpdates" | python3 -m json.tool
```

Buscar `"chat":{"id":123456789,…}`. Guardar ese id en Keychain:

```bash
security add-generic-password \
  -s "navarra-edu-bot" \
  -a "telegram-chat-id" \
  -w "123456789" \
  -U
```

- [ ] **Step 4: Guardar credenciales Educa en Keychain**

```bash
security add-generic-password \
  -s "navarra-edu-bot" \
  -a "educa-username" \
  -w "vtancoagua" \
  -U

security add-generic-password \
  -s "navarra-edu-bot" \
  -a "educa-password" \
  -w "TU_PASSWORD_NUEVA" \
  -U
```

⚠️ Usar la contraseña **nueva** (recordar cambiar la del mensaje inicial).

- [ ] **Step 5: Crear `config.example.yaml`**

Crea `/Users/vicente.tancoedu.uah.es/educacion/config.example.yaml`:

```yaml
# Copy this file to ~/.navarra-edu-bot/config.yaml and edit.
# Secrets (token, chat_id, credentials) live in macOS Keychain, NOT here.

portal:
  base_url: "https://appseducacion.navarra.es/atp/"
  login_path: "index.xhtml"

user:
  preferred_localities:
    - "Pamplona"
    - "Orkoien"
    - "Orcoyen"
    - "Barañáin"
    - "Baranain"
  specialty_preference_order:
    - "Tecnología"
    - "Matemáticas"
    - "Dibujo"

# Listas donde el usuario está "Disponible" (L/M/X/V).
available_lists:
  - body: "0590"
    specialty: "Equipos Electrónicos"
  - body: "0590"
    specialty: "Organización y Proyectos de Fabricación Mecánica"
  - body: "0590"
    specialty: "Sistemas Electrotécnicos y Automáticos"
  - body: "0590"
    specialty: "Sistemas Electrónicos"
  - body: "0590"
    specialty: "Tecnología"
    list_type: "CONVOCATORIA"
  - body: "0598"
    specialty: "Fabricación e Instalación de Carpintería y Mueble"
  - body: "0598"
    specialty: "Mantenimiento de Vehículos"

# Listas abiertas los jueves según formación (confirmar con RD).
thursday_open_specialties:
  - body: "0590"
    specialty: "Tecnología"
  - body: "0590"
    specialty: "Matemáticas"
  - body: "0590"
    specialty: "Dibujo"
  - body: "0590"
    specialty: "Física y Química"
  # (completar tras revisar docs/formacion-especialidades.md)

scheduler:
  daily_start: "13:25"
  daily_end: "14:05"
  poll_interval_seconds: 15

runtime:
  dry_run: true
  log_level: "INFO"
  storage_path: "~/.navarra-edu-bot/state.db"
  log_path: "~/.navarra-edu-bot/logs/"
```

- [ ] **Step 6: Verificar Keychain**

```bash
security find-generic-password -s "navarra-edu-bot" -a "telegram-token" -w
security find-generic-password -s "navarra-edu-bot" -a "telegram-chat-id" -w
security find-generic-password -s "navarra-edu-bot" -a "educa-username" -w
```

Expected: cada comando imprime el valor correspondiente (no la contraseña, que confirmaremos en Task 5).

- [ ] **Step 7: Commit**

```bash
git add config.example.yaml
git commit -m "feat(config): add example config template"
```

---

### Task 4: Ping Telegram — primer mensaje del bot

**Files:**
- Create: `navarra_edu_bot/telegram_bot/client.py`
- Modify: `navarra_edu_bot/cli.py`

- [ ] **Step 1: Escribir test**

Crea `tests/test_telegram_client.py`:

```python
import pytest

from navarra_edu_bot.telegram_bot.client import build_bot_app


def test_build_bot_app_requires_token():
    with pytest.raises(ValueError, match="token"):
        build_bot_app(token="", chat_id=1)


def test_build_bot_app_returns_configured_app():
    app = build_bot_app(token="FAKE_TOKEN", chat_id=12345)
    assert app.bot.token == "FAKE_TOKEN"
```

- [ ] **Step 2: Run test — debe fallar**

```bash
pytest tests/test_telegram_client.py -v
```

Expected: FAIL (`build_bot_app` no existe).

- [ ] **Step 3: Implementar `client.py`**

Crea `navarra_edu_bot/telegram_bot/client.py`:

```python
from __future__ import annotations

from telegram.ext import Application, ApplicationBuilder


def build_bot_app(token: str, chat_id: int) -> Application:
    if not token:
        raise ValueError("Telegram token is required")
    if not chat_id:
        raise ValueError("Telegram chat_id is required")
    return ApplicationBuilder().token(token).build()
```

- [ ] **Step 4: Run test — debe pasar**

```bash
pytest tests/test_telegram_client.py -v
```

Expected: 2 passed.

- [ ] **Step 5: Añadir comando `ping-telegram` al CLI**

Sustituye el contenido de `navarra_edu_bot/cli.py`:

```python
import asyncio
import subprocess

import click

from navarra_edu_bot.telegram_bot.client import build_bot_app


def _keychain_read(account: str) -> str:
    return subprocess.check_output(
        ["security", "find-generic-password", "-s", "navarra-edu-bot", "-a", account, "-w"],
        text=True,
    ).strip()


@click.group()
def main() -> None:
    """Navarra Edu Bot CLI."""


@main.command()
def ping() -> None:
    """Healthcheck ping."""
    click.echo("pong")


@main.command("ping-telegram")
def ping_telegram() -> None:
    """Send a test message to the configured Telegram chat."""
    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    app = build_bot_app(token=token, chat_id=chat_id)

    async def _send() -> None:
        async with app:
            await app.bot.send_message(chat_id=chat_id, text="Hola desde Navarra Edu Bot ✅")

    asyncio.run(_send())
    click.echo("sent")


if __name__ == "__main__":
    main()
```

- [ ] **Step 6: Ejecutar ping real contra Telegram**

```bash
python -m navarra_edu_bot ping-telegram
```

Expected: el usuario recibe "Hola desde Navarra Edu Bot ✅" en Telegram.

- [ ] **Step 7: Commit**

```bash
git add navarra_edu_bot/telegram_bot/client.py navarra_edu_bot/cli.py tests/test_telegram_client.py
git commit -m "feat(telegram): add build_bot_app and ping-telegram CLI command"
```

---

### Task 5: launchd plist preparado (inactivo)

**Files:**
- Create: `deploy/navarra-edu-bot.plist.template`
- Modify: `README.md`

- [ ] **Step 1: Crear plist template**

Crea `/Users/vicente.tancoedu.uah.es/educacion/deploy/navarra-edu-bot.plist.template`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.vtanco.navarra-edu-bot</string>

    <key>ProgramArguments</key>
    <array>
        <string>{{VENV_PYTHON}}</string>
        <string>-m</string>
        <string>navarra_edu_bot</string>
        <string>run-daily</string>
    </array>

    <key>WorkingDirectory</key>
    <string>{{PROJECT_DIR}}</string>

    <key>StartCalendarInterval</key>
    <array>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>25</integer></dict>
        <dict><key>Weekday</key><integer>5</integer><key>Hour</key><integer>13</integer><key>Minute</key><integer>25</integer></dict>
    </array>

    <key>StandardOutPath</key>
    <string>{{LOG_DIR}}/launchd.stdout.log</string>

    <key>StandardErrorPath</key>
    <string>{{LOG_DIR}}/launchd.stderr.log</string>

    <key>RunAtLoad</key>
    <false/>
</dict>
</plist>
```

- [ ] **Step 2: Añadir sección launchd al README**

Añade al final de `README.md`:

```markdown
## launchd scheduling (Phase 3+)

The plist template lives in `deploy/navarra-edu-bot.plist.template`. It is NOT
installed during phases 0–2 (no `run-daily` command exists yet). Installation
instructions will appear in the Phase 3 plan.
```

- [ ] **Step 3: Commit**

```bash
git add deploy/ README.md
git commit -m "feat(deploy): add launchd plist template (not activated yet)"
```

---

## FASE 1 — Login + fetch dry-run (Tareas 6–13)

### Task 6: Config schema con Pydantic

**Files:**
- Create: `navarra_edu_bot/config/schema.py`
- Create: `tests/test_config_schema.py`

- [ ] **Step 1: Escribir tests**

Crea `tests/test_config_schema.py`:

```python
import pytest
from pydantic import ValidationError

from navarra_edu_bot.config.schema import AppConfig, ListEntry


def test_list_entry_minimal():
    entry = ListEntry(body="0590", specialty="Tecnología")
    assert entry.body == "0590"
    assert entry.list_type is None


def test_list_entry_with_type():
    entry = ListEntry(body="0590", specialty="Tecnología", list_type="CONVOCATORIA")
    assert entry.list_type == "CONVOCATORIA"


def test_app_config_loads_valid_dict(valid_config_dict):
    cfg = AppConfig.model_validate(valid_config_dict)
    assert cfg.runtime.dry_run is True
    assert cfg.user.specialty_preference_order[0] == "Tecnología"
    assert len(cfg.available_lists) == 7


def test_app_config_rejects_invalid_body(valid_config_dict):
    valid_config_dict["available_lists"][0]["body"] = "9999"
    with pytest.raises(ValidationError, match="body"):
        AppConfig.model_validate(valid_config_dict)
```

Y añade al `conftest.py`:

```python
@pytest.fixture
def valid_config_dict() -> dict:
    return {
        "portal": {"base_url": "https://example.test/", "login_path": "index.xhtml"},
        "user": {
            "preferred_localities": ["Pamplona"],
            "specialty_preference_order": ["Tecnología", "Matemáticas", "Dibujo"],
        },
        "available_lists": [
            {"body": "0590", "specialty": "Equipos Electrónicos"},
            {"body": "0590", "specialty": "Organización y Proyectos de Fabricación Mecánica"},
            {"body": "0590", "specialty": "Sistemas Electrotécnicos y Automáticos"},
            {"body": "0590", "specialty": "Sistemas Electrónicos"},
            {"body": "0590", "specialty": "Tecnología", "list_type": "CONVOCATORIA"},
            {"body": "0598", "specialty": "Fabricación e Instalación de Carpintería y Mueble"},
            {"body": "0598", "specialty": "Mantenimiento de Vehículos"},
        ],
        "thursday_open_specialties": [
            {"body": "0590", "specialty": "Tecnología"},
        ],
        "scheduler": {
            "daily_start": "13:25",
            "daily_end": "14:05",
            "poll_interval_seconds": 15,
        },
        "runtime": {
            "dry_run": True,
            "log_level": "INFO",
            "storage_path": "~/.navarra-edu-bot/state.db",
            "log_path": "~/.navarra-edu-bot/logs/",
        },
    }
```

- [ ] **Step 2: Run tests — deben fallar**

```bash
pytest tests/test_config_schema.py -v
```

Expected: FAIL (módulo no existe).

- [ ] **Step 3: Implementar schema**

Crea `navarra_edu_bot/config/schema.py`:

```python
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

BodyCode = Literal["0590", "0598"]


class ListEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")

    body: BodyCode
    specialty: str
    list_type: str | None = None

    @field_validator("specialty")
    @classmethod
    def _non_empty(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("specialty must not be empty")
        return v


class UserSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    preferred_localities: list[str] = Field(default_factory=list)
    specialty_preference_order: list[str] = Field(default_factory=list)


class PortalSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    base_url: str
    login_path: str


class SchedulerSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    daily_start: str
    daily_end: str
    poll_interval_seconds: int = Field(ge=5, le=60)


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="forbid")

    dry_run: bool = True
    log_level: str = "INFO"
    storage_path: str
    log_path: str


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    portal: PortalSettings
    user: UserSettings
    available_lists: list[ListEntry]
    thursday_open_specialties: list[ListEntry]
    scheduler: SchedulerSettings
    runtime: RuntimeSettings
```

- [ ] **Step 4: Run tests — deben pasar**

```bash
pytest tests/test_config_schema.py -v
```

Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add navarra_edu_bot/config/schema.py tests/test_config_schema.py tests/conftest.py
git commit -m "feat(config): add Pydantic schema for app configuration"
```

---

### Task 7: Config loader + Keychain wrapper

**Files:**
- Create: `navarra_edu_bot/config/keychain.py`
- Create: `navarra_edu_bot/config/loader.py`
- Create: `tests/test_keychain.py`
- Create: `tests/test_config_loader.py`

- [ ] **Step 1: Test Keychain wrapper (con mock de subprocess)**

Crea `tests/test_keychain.py`:

```python
from unittest.mock import patch

import pytest

from navarra_edu_bot.config.keychain import KeychainError, read_secret


def test_read_secret_returns_value():
    with patch("subprocess.check_output", return_value="abc123\n"):
        assert read_secret("x") == "abc123"


def test_read_secret_raises_on_missing():
    from subprocess import CalledProcessError

    with patch("subprocess.check_output", side_effect=CalledProcessError(44, "security")):
        with pytest.raises(KeychainError):
            read_secret("missing")
```

- [ ] **Step 2: Implementar keychain.py**

Crea `navarra_edu_bot/config/keychain.py`:

```python
from __future__ import annotations

import subprocess

_SERVICE = "navarra-edu-bot"


class KeychainError(RuntimeError):
    pass


def read_secret(account: str) -> str:
    try:
        output = subprocess.check_output(
            ["security", "find-generic-password", "-s", _SERVICE, "-a", account, "-w"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise KeychainError(f"Keychain entry not found: service={_SERVICE} account={account}") from exc
    return output.strip()
```

- [ ] **Step 3: Run test — debe pasar**

```bash
pytest tests/test_keychain.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Test loader**

Crea `tests/test_config_loader.py`:

```python
from pathlib import Path

import yaml

from navarra_edu_bot.config.loader import load_config


def test_load_config_from_file(tmp_path: Path, valid_config_dict: dict):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(valid_config_dict))

    cfg = load_config(cfg_path)
    assert cfg.runtime.dry_run is True
    assert cfg.portal.base_url == "https://example.test/"
```

- [ ] **Step 5: Implementar loader**

Crea `navarra_edu_bot/config/loader.py`:

```python
from __future__ import annotations

from pathlib import Path

import yaml

from navarra_edu_bot.config.schema import AppConfig


def load_config(path: Path | str) -> AppConfig:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text())
    return AppConfig.model_validate(data)
```

- [ ] **Step 6: Run test — debe pasar**

```bash
pytest tests/test_config_loader.py -v
```

Expected: 1 passed.

- [ ] **Step 7: Copiar config de ejemplo a `~/.navarra-edu-bot/`**

```bash
mkdir -p ~/.navarra-edu-bot/logs
cp /Users/vicente.tancoedu.uah.es/educacion/config.example.yaml ~/.navarra-edu-bot/config.yaml
```

- [ ] **Step 8: Commit**

```bash
git add navarra_edu_bot/config tests/test_keychain.py tests/test_config_loader.py
git commit -m "feat(config): add keychain wrapper and YAML loader"
```

---

### Task 8: Storage — SQLite + modelos

**Files:**
- Create: `navarra_edu_bot/storage/models.py`
- Create: `navarra_edu_bot/storage/db.py`
- Create: `tests/test_storage.py`

- [ ] **Step 1: Test modelos**

Crea `tests/test_storage.py`:

```python
from datetime import datetime
from pathlib import Path

from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer


def _sample_offer(offer_id: str = "O1") -> Offer:
    return Offer(
        offer_id=offer_id,
        body="0590",
        specialty="Tecnología",
        locality="Pamplona",
        center="IES Example",
        hours_per_week=20,
        duration="Curso completo",
        raw_html_hash="abc",
        seen_at=datetime(2026, 4, 23, 13, 32),
    )


def test_storage_roundtrip(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()

    offer = _sample_offer()
    storage.upsert_offer(offer)

    loaded = storage.get_offer("O1")
    assert loaded is not None
    assert loaded.specialty == "Tecnología"


def test_storage_mark_preselected(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_sample_offer())

    storage.mark_preselected("O1", preselected=True)
    assert storage.is_preselected("O1") is True

    storage.mark_preselected("O1", preselected=False)
    assert storage.is_preselected("O1") is False


def test_storage_list_preselected_for_today(tmp_path: Path):
    storage = Storage(tmp_path / "test.db")
    storage.init_schema()
    storage.upsert_offer(_sample_offer("O1"))
    storage.upsert_offer(_sample_offer("O2"))
    storage.mark_preselected("O1", preselected=True)

    ids = storage.list_preselected_today(now=datetime(2026, 4, 23, 13, 59))
    assert ids == ["O1"]
```

- [ ] **Step 2: Implementar modelos**

Crea `navarra_edu_bot/storage/models.py`:

```python
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(slots=True)
class Offer:
    offer_id: str
    body: str
    specialty: str
    locality: str
    center: str
    hours_per_week: int
    duration: str
    raw_html_hash: str
    seen_at: datetime
```

- [ ] **Step 3: Implementar Storage**

Crea `navarra_edu_bot/storage/db.py`:

```python
from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

from navarra_edu_bot.storage.models import Offer

_SCHEMA = """
CREATE TABLE IF NOT EXISTS offers (
    offer_id TEXT PRIMARY KEY,
    body TEXT NOT NULL,
    specialty TEXT NOT NULL,
    locality TEXT NOT NULL,
    center TEXT NOT NULL,
    hours_per_week INTEGER NOT NULL,
    duration TEXT NOT NULL,
    raw_html_hash TEXT NOT NULL,
    seen_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS decisions (
    offer_id TEXT PRIMARY KEY,
    preselected INTEGER NOT NULL,
    decided_at TEXT NOT NULL,
    FOREIGN KEY (offer_id) REFERENCES offers(offer_id)
);

CREATE INDEX IF NOT EXISTS idx_offers_seen_at ON offers(seen_at);
CREATE INDEX IF NOT EXISTS idx_decisions_decided_at ON decisions(decided_at);
"""


class Storage:
    def __init__(self, path: Path | str) -> None:
        self._path = Path(path).expanduser()
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _conn(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

    def init_schema(self) -> None:
        with self._conn() as conn:
            conn.executescript(_SCHEMA)

    def upsert_offer(self, offer: Offer) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO offers(offer_id, body, specialty, locality, center,
                                   hours_per_week, duration, raw_html_hash, seen_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    body=excluded.body,
                    specialty=excluded.specialty,
                    locality=excluded.locality,
                    center=excluded.center,
                    hours_per_week=excluded.hours_per_week,
                    duration=excluded.duration,
                    raw_html_hash=excluded.raw_html_hash,
                    seen_at=excluded.seen_at
                """,
                (
                    offer.offer_id,
                    offer.body,
                    offer.specialty,
                    offer.locality,
                    offer.center,
                    offer.hours_per_week,
                    offer.duration,
                    offer.raw_html_hash,
                    offer.seen_at.isoformat(),
                ),
            )

    def get_offer(self, offer_id: str) -> Offer | None:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT * FROM offers WHERE offer_id = ?", (offer_id,)
            ).fetchone()
        if row is None:
            return None
        return Offer(
            offer_id=row["offer_id"],
            body=row["body"],
            specialty=row["specialty"],
            locality=row["locality"],
            center=row["center"],
            hours_per_week=row["hours_per_week"],
            duration=row["duration"],
            raw_html_hash=row["raw_html_hash"],
            seen_at=datetime.fromisoformat(row["seen_at"]),
        )

    def mark_preselected(self, offer_id: str, *, preselected: bool) -> None:
        with self._conn() as conn:
            conn.execute(
                """
                INSERT INTO decisions(offer_id, preselected, decided_at)
                VALUES (?, ?, ?)
                ON CONFLICT(offer_id) DO UPDATE SET
                    preselected=excluded.preselected,
                    decided_at=excluded.decided_at
                """,
                (offer_id, int(preselected), datetime.now().isoformat()),
            )

    def is_preselected(self, offer_id: str) -> bool:
        with self._conn() as conn:
            row = conn.execute(
                "SELECT preselected FROM decisions WHERE offer_id = ?", (offer_id,)
            ).fetchone()
        return bool(row and row["preselected"])

    def list_preselected_today(self, *, now: datetime) -> list[str]:
        start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end_of_day = start_of_day + timedelta(days=1)
        with self._conn() as conn:
            rows = conn.execute(
                """
                SELECT offer_id FROM decisions
                WHERE preselected = 1
                  AND decided_at >= ? AND decided_at < ?
                ORDER BY decided_at ASC
                """,
                (start_of_day.isoformat(), end_of_day.isoformat()),
            ).fetchall()
        return [r["offer_id"] for r in rows]
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_storage.py -v
```

Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add navarra_edu_bot/storage tests/test_storage.py
git commit -m "feat(storage): SQLite storage for offers and decisions"
```

---

### Task 9: Capturar fixtures HTML del portal real

**Files:**
- Create: `tests/fixtures/login_page.html`
- Create: `tests/fixtures/offers_list.html`
- Create: `tests/fixtures/offers_empty.html`
- Create: `tests/fixtures/session_expired.html`
- Create: `scripts/capture_fixtures.py`

- [ ] **Step 1: Script para capturar fixtures**

Crea `/Users/vicente.tancoedu.uah.es/educacion/scripts/capture_fixtures.py`:

```python
"""Capture HTML fixtures from the real portal for use in tests.

Run OUTSIDE the 13:30-14:00 window. Requires credentials in Keychain.
"""

import asyncio
from pathlib import Path

from playwright.async_api import async_playwright

from navarra_edu_bot.config.keychain import read_secret

FIXTURES_DIR = Path(__file__).resolve().parents[1] / "tests" / "fixtures"
PORTAL_URL = "https://appseducacion.navarra.es/atp/index.xhtml"


async def main() -> None:
    username = read_secret("educa-username")
    password = read_secret("educa-password")

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        ctx = await browser.new_context()
        page = await ctx.new_page()

        await page.goto(PORTAL_URL)
        (FIXTURES_DIR / "login_page.html").write_text(await page.content())

        # Click "Usuario Educa" — SELECTOR TBD by human on first run.
        print("Opened login page. Log in manually in the opened browser window.")
        print("Press Enter here once you are on the offers list page.")
        input()

        (FIXTURES_DIR / "offers_list.html").write_text(await page.content())

        print("Now navigate to a day with no offers (or trigger session expiry) and press Enter.")
        input()
        (FIXTURES_DIR / "offers_empty.html").write_text(await page.content())

        await browser.close()


if __name__ == "__main__":
    asyncio.run(main())
```

- [ ] **Step 2: Ejecutar script (manual, con el usuario delante)**

```bash
cd /Users/vicente.tancoedu.uah.es/educacion
python scripts/capture_fixtures.py
```

Expected: se abren 3 HTMLs en `tests/fixtures/`. Durante la captura, el **ingeniero toma notas** de los selectores CSS/name de:

- Campo username (p. ej. `input[name="username"]`).
- Campo password.
- Botón de login.
- Tabla/lista de ofertas (contenedor).
- Cada fila de oferta: cuerpo, especialidad, localidad, centro, horas, duración, botón "solicitar".
- Indicador de sesión expirada (p. ej. presencia del botón de login en HTML autenticado).

Guardar estas notas en comentarios de las tareas siguientes (parser, login).

- [ ] **Step 3: Crear fixture `session_expired.html` manualmente**

Esperar a que expire la sesión (o cerrar sesión manualmente) y capturar:

```bash
curl -s https://appseducacion.navarra.es/atp/index.xhtml > tests/fixtures/session_expired.html
```

(O copiar y pegar desde el navegador si el curl no devuelve la misma página).

- [ ] **Step 4: Commit**

```bash
git add scripts/capture_fixtures.py tests/fixtures/
git commit -m "test: add HTML fixtures captured from real portal"
```

---

### Task 10: Parser de ofertas

**Files:**
- Create: `navarra_edu_bot/scraper/parser.py`
- Create: `tests/test_scraper_parser.py`

⚠️ **Nota:** los selectores exactos dependen de los fixtures capturados en Task 9. El código siguiente usa selectores **placeholder** que el ingeniero debe ajustar tras inspeccionar `tests/fixtures/offers_list.html`. Deja TODOs visibles si un selector no está claro — pero **sí** implementa la estructura completa y los tests pasan contra fixtures reales.

- [ ] **Step 1: Inspeccionar `offers_list.html`**

Abrir el fichero capturado. Identificar:

- Contenedor de ofertas (p. ej. `<table id="offersTable">`).
- Cada fila de oferta y sus columnas.
- Cómo se identifica unívocamente una oferta (atributo `data-id`? número de plaza? índice de fila?).

Anotar los selectores exactos. Se usan en el siguiente step.

- [ ] **Step 2: Test parser**

Crea `tests/test_scraper_parser.py`:

```python
from pathlib import Path

from navarra_edu_bot.scraper.parser import parse_offers


def test_parse_offers_list(fixtures_dir: Path):
    html = (fixtures_dir / "offers_list.html").read_text()
    offers = parse_offers(html)
    assert len(offers) > 0
    first = offers[0]
    assert first.body in {"0590", "0598"}
    assert first.specialty != ""
    assert first.locality != ""


def test_parse_offers_empty(fixtures_dir: Path):
    html = (fixtures_dir / "offers_empty.html").read_text()
    assert parse_offers(html) == []


def test_parse_offers_session_expired(fixtures_dir: Path):
    from navarra_edu_bot.scraper.parser import SessionExpiredError

    html = (fixtures_dir / "session_expired.html").read_text()
    import pytest

    with pytest.raises(SessionExpiredError):
        parse_offers(html)
```

- [ ] **Step 3: Implementar parser**

Crea `navarra_edu_bot/scraper/parser.py`:

```python
from __future__ import annotations

import hashlib
from datetime import datetime

from bs4 import BeautifulSoup

from navarra_edu_bot.storage.models import Offer


class SessionExpiredError(RuntimeError):
    pass


# Selectors extracted from captured fixtures. Adjust after Task 9.
# Document here the exact path used, e.g.:
# - Offers table: table#offersTable
# - Row: tbody > tr
# - Cells: td:nth-child(1) body, (2) specialty, (3) locality, (4) center,
#          (5) hours, (6) duration, (7) apply button
# - Login presence indicator (session expired): div.login-form
_OFFERS_TABLE_SELECTOR = "table#offersTable tbody tr"  # TODO: confirm
_LOGIN_INDICATOR = "div.login-form"  # TODO: confirm


def parse_offers(html: str) -> list[Offer]:
    soup = BeautifulSoup(html, "html.parser")

    if soup.select_one(_LOGIN_INDICATOR):
        raise SessionExpiredError("Session expired: login form detected")

    rows = soup.select(_OFFERS_TABLE_SELECTOR)
    now = datetime.now()
    offers: list[Offer] = []
    for idx, row in enumerate(rows):
        cells = [c.get_text(strip=True) for c in row.find_all("td")]
        if len(cells) < 6:
            continue
        offer_id = row.get("data-id") or f"row-{idx}-{_hash(cells)}"
        offers.append(
            Offer(
                offer_id=str(offer_id),
                body=cells[0],
                specialty=cells[1],
                locality=cells[2],
                center=cells[3],
                hours_per_week=_parse_int(cells[4]),
                duration=cells[5],
                raw_html_hash=_hash(cells),
                seen_at=now,
            )
        )
    return offers


def _hash(parts: list[str]) -> str:
    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]


def _parse_int(text: str) -> int:
    digits = "".join(c for c in text if c.isdigit())
    return int(digits) if digits else 0
```

- [ ] **Step 4: Añadir BeautifulSoup como dependencia**

Edita `pyproject.toml` añadiendo a `dependencies`:

```toml
    "beautifulsoup4>=4.12.0",
```

Luego:

```bash
uv pip install -e ".[dev]"
```

- [ ] **Step 5: Run tests**

```bash
pytest tests/test_scraper_parser.py -v
```

Expected: 3 passed. Si falla, ajustar selectores en `parser.py` mirando el fixture real.

- [ ] **Step 6: Commit**

```bash
git add navarra_edu_bot/scraper/parser.py tests/test_scraper_parser.py pyproject.toml
git commit -m "feat(scraper): parse offers HTML with BeautifulSoup"
```

---

### Task 11: Login Educa con Playwright

**Files:**
- Create: `navarra_edu_bot/scraper/browser.py`
- Create: `navarra_edu_bot/scraper/login.py`

⚠️ Esta tarea es **solo integración con portal real** (no tests unitarios con fixtures — el login requiere el portal). Se valida manualmente en Task 13.

- [ ] **Step 1: Implementar browser context**

Crea `navarra_edu_bot/scraper/browser.py`:

```python
from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from playwright.async_api import Browser, BrowserContext, Page, async_playwright


@asynccontextmanager
async def browser_context(
    *, headless: bool = True, user_agent: str | None = None
) -> AsyncIterator[tuple[Browser, BrowserContext, Page]]:
    ua = user_agent or (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_0) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
    )
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(user_agent=ua)
        page = await ctx.new_page()
        try:
            yield browser, ctx, page
        finally:
            await browser.close()
```

- [ ] **Step 2: Implementar login**

Crea `navarra_edu_bot/scraper/login.py`:

```python
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
```

- [ ] **Step 3: Commit**

```bash
git add navarra_edu_bot/scraper/browser.py navarra_edu_bot/scraper/login.py
git commit -m "feat(scraper): add Playwright login flow for Educa portal"
```

---

### Task 12: Fetch orchestrator + CLI `fetch --dry`

**Files:**
- Create: `navarra_edu_bot/scraper/fetch.py`
- Modify: `navarra_edu_bot/cli.py`

- [ ] **Step 1: Implementar fetch**

Crea `navarra_edu_bot/scraper/fetch.py`:

```python
from __future__ import annotations

from navarra_edu_bot.scraper.browser import browser_context
from navarra_edu_bot.scraper.login import login_educa
from navarra_edu_bot.scraper.parser import parse_offers
from navarra_edu_bot.storage.models import Offer

OFFERS_PAGE_PATH = "/atp/index.xhtml"  # Same page post-login in most cases; adjust.


async def fetch_offers(
    *, username: str, password: str, headless: bool = True
) -> list[Offer]:
    async with browser_context(headless=headless) as (_browser, _ctx, page):
        await login_educa(page, username=username, password=password)
        # Assumes after login the offers page is the current page.
        html = await page.content()
    return parse_offers(html)
```

- [ ] **Step 2: Añadir comando CLI**

Añade a `navarra_edu_bot/cli.py` (debajo de `ping_telegram`):

```python
@main.command()
@click.option("--headless/--headed", default=True)
def fetch(headless: bool) -> None:
    """Login to Educa, fetch offers, print them. Does NOT apply."""
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    from navarra_edu_bot.scraper.fetch import fetch_offers

    offers = asyncio.run(fetch_offers(username=username, password=password, headless=headless))
    click.echo(f"Found {len(offers)} offers:")
    for o in offers:
        click.echo(f"  [{o.body}] {o.specialty} @ {o.locality} — {o.center} ({o.hours_per_week}h, {o.duration})")
```

- [ ] **Step 3: Ejecutar con navegador visible (primera vez)**

```bash
python -m navarra_edu_bot fetch --headed
```

Expected: navegador se abre, login exitoso, ofertas listadas en terminal. Si falla, revisar selectores en `login.py` y `parser.py`.

- [ ] **Step 4: Ejecutar headless**

```bash
python -m navarra_edu_bot fetch
```

Expected: mismo resultado, sin navegador visible.

- [ ] **Step 5: Commit**

```bash
git add navarra_edu_bot/scraper/fetch.py navarra_edu_bot/cli.py
git commit -m "feat(cli): add `fetch` command that logs in and lists offers"
```

---

### Task 13: Checkpoint Fase 1 — verificación manual

- [ ] **Step 1: Ejecutar `fetch` cada día laborable durante 3 días**

Entre las 13:35 y 13:55, ejecutar:

```bash
python -m navarra_edu_bot fetch --headed 2>&1 | tee ~/.navarra-edu-bot/logs/fetch-$(date +%F-%H%M).log
```

Validar contra el portal real que las ofertas mostradas por el CLI **coinciden exactamente** con las visibles en la web.

- [ ] **Step 2: Criterio de éxito**

3 días consecutivos sin discrepancias → Fase 1 cerrada. Si hay discrepancias, ajustar selectores en `parser.py` (puede necesitar nuevos fixtures).

- [ ] **Step 3: Tag de versión**

```bash
cd /Users/vicente.tancoedu.uah.es/educacion
git tag v0.1.0-phase1 -m "Phase 1: login + fetch dry verified"
```

---

## FASE 2 — Filter + ranking + Telegram interactivo (Tareas 14–22)

### Task 14: Investigación formal formación → especialidades

**Files:**
- Create: `docs/formacion-especialidades.md`

- [ ] **Step 1: Investigación**

Fuentes oficiales a consultar:
- **RD 276/2007** (BOE): Reglamento de ingreso en cuerpos docentes — Anexo de titulaciones.
- **RD 800/2022** (BOE): Especialidades de los cuerpos de FP (0598 y el nuevo 0599).
- **Orden EFP/498/2020** y modificaciones posteriores.
- Portal de Educación de Navarra: requisitos de acceso a cada lista.

- [ ] **Step 2: Redactar documento**

Crea `/Users/vicente.tancoedu.uah.es/educacion/docs/formacion-especialidades.md`:

Estructura:
1. Titulaciones del usuario (Grado + Máster Ing. Industrial).
2. Para cada especialidad de 0590/0598, tabla con:
   - Acceso permitido (sí/no/condicional).
   - Fuente normativa citada (RD, art., anexo).
   - Requisitos adicionales (p. ej. MUFPS obligatorio para Secundaria).
3. Notas sobre el MUFPS.
4. Fecha de revisión y disclaimer ("al implementador: confirmar antes de activar Fase 5").

- [ ] **Step 3: Revisión por el usuario (asíncrono)**

Pedir al usuario que revise el documento y corrija/confirme. **Esta revisión es bloqueante para Fase 5**, no para Fase 2.

- [ ] **Step 4: Commit**

```bash
git add docs/formacion-especialidades.md
git commit -m "docs: research and document formation→specialties mapping"
```

---

### Task 15: Filtro de elegibilidad por día de la semana

**Files:**
- Create: `navarra_edu_bot/filter/eligibility.py`
- Create: `tests/test_filter_eligibility.py`

- [ ] **Step 1: Test**

Crea `tests/test_filter_eligibility.py`:

```python
from datetime import datetime

from navarra_edu_bot.filter.eligibility import is_eligible
from navarra_edu_bot.config.schema import ListEntry
from navarra_edu_bot.storage.models import Offer


def _offer(body="0590", specialty="Tecnología") -> Offer:
    return Offer(
        offer_id="X",
        body=body,
        specialty=specialty,
        locality="Pamplona",
        center="IES",
        hours_per_week=20,
        duration="Curso",
        raw_html_hash="h",
        seen_at=datetime.now(),
    )


AVAILABLE = [ListEntry(body="0590", specialty="Tecnología", list_type="CONVOCATORIA")]
THURSDAY_OPEN = [
    ListEntry(body="0590", specialty="Tecnología"),
    ListEntry(body="0590", specialty="Matemáticas"),
]


def test_monday_only_available_lists():
    # 2026-04-20 is a Monday
    day = datetime(2026, 4, 20, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Matemáticas"), day, AVAILABLE, THURSDAY_OPEN) is False


def test_thursday_open_call():
    # 2026-04-23 is a Thursday
    day = datetime(2026, 4, 23, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Matemáticas"), day, AVAILABLE, THURSDAY_OPEN) is True
    assert is_eligible(_offer(specialty="Inglés"), day, AVAILABLE, THURSDAY_OPEN) is False


def test_saturday_never():
    day = datetime(2026, 4, 25, 14, 0)
    assert is_eligible(_offer(specialty="Tecnología"), day, AVAILABLE, THURSDAY_OPEN) is False
```

- [ ] **Step 2: Implementar**

Crea `navarra_edu_bot/filter/eligibility.py`:

```python
from __future__ import annotations

from datetime import datetime

from navarra_edu_bot.config.schema import ListEntry
from navarra_edu_bot.storage.models import Offer

_THURSDAY = 3  # Monday=0 ... Sunday=6
_WEEKDAYS = {0, 1, 2, 4}  # Mon, Tue, Wed, Fri — "closed" days


def is_eligible(
    offer: Offer,
    now: datetime,
    available_lists: list[ListEntry],
    thursday_open_specialties: list[ListEntry],
) -> bool:
    weekday = now.weekday()
    if weekday == _THURSDAY:
        return _match_any(offer, thursday_open_specialties)
    if weekday in _WEEKDAYS:
        return _match_any(offer, available_lists)
    return False


def _match_any(offer: Offer, entries: list[ListEntry]) -> bool:
    return any(
        e.body == offer.body and e.specialty.lower() == offer.specialty.lower() for e in entries
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_filter_eligibility.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/filter/eligibility.py tests/test_filter_eligibility.py
git commit -m "feat(filter): eligibility by day of week and list membership"
```

---

### Task 16: Ranking de ofertas

**Files:**
- Create: `navarra_edu_bot/filter/ranker.py`
- Create: `tests/test_filter_ranker.py`

- [ ] **Step 1: Test**

Crea `tests/test_filter_ranker.py`:

```python
from datetime import datetime

from navarra_edu_bot.filter.ranker import rank_offers
from navarra_edu_bot.storage.models import Offer


def _offer(*, specialty="Tecnología", locality="Pamplona", hours=20) -> Offer:
    return Offer(
        offer_id=f"{specialty}-{locality}-{hours}",
        body="0590",
        specialty=specialty,
        locality=locality,
        center="IES",
        hours_per_week=hours,
        duration="Curso",
        raw_html_hash="h",
        seen_at=datetime.now(),
    )


PREFERRED_LOCALITIES = ["Pamplona", "Orkoien", "Barañáin"]
SPECIALTY_ORDER = ["Tecnología", "Matemáticas", "Dibujo"]


def test_full_time_ranks_higher_than_part_time():
    offers = [
        _offer(hours=10),
        _offer(hours=22),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert ranked[0].hours_per_week == 22


def test_preferred_locality_ranks_higher():
    offers = [
        _offer(locality="Tudela"),
        _offer(locality="Pamplona"),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert ranked[0].locality == "Pamplona"


def test_specialty_order_tiebreak():
    offers = [
        _offer(specialty="Dibujo"),
        _offer(specialty="Tecnología"),
        _offer(specialty="Matemáticas"),
    ]
    ranked = rank_offers(offers, PREFERRED_LOCALITIES, SPECIALTY_ORDER)
    assert [o.specialty for o in ranked] == ["Tecnología", "Matemáticas", "Dibujo"]
```

- [ ] **Step 2: Implementar**

Crea `navarra_edu_bot/filter/ranker.py`:

```python
from __future__ import annotations

from unicodedata import category, normalize

from navarra_edu_bot.storage.models import Offer

_FULL_TIME_HOURS = 18  # ≥ 18 h/week treated as full-time.


def rank_offers(
    offers: list[Offer],
    preferred_localities: list[str],
    specialty_order: list[str],
) -> list[Offer]:
    return sorted(offers, key=lambda o: _score(o, preferred_localities, specialty_order))


def _score(
    offer: Offer, preferred_localities: list[str], specialty_order: list[str]
) -> tuple[int, int, int]:
    # Lower score = higher rank.
    full_time_rank = 0 if offer.hours_per_week >= _FULL_TIME_HOURS else 1

    pref = _norm_list(preferred_localities)
    locality_rank = 0 if _norm(offer.locality) in pref else 1

    order = _norm_list(specialty_order)
    specialty = _norm(offer.specialty)
    specialty_rank = order.index(specialty) if specialty in order else len(order)

    return (full_time_rank, locality_rank, specialty_rank)


def _norm(s: str) -> str:
    return "".join(c for c in normalize("NFD", s) if not category(c).startswith("M")).lower().strip()


def _norm_list(items: list[str]) -> list[str]:
    return [_norm(i) for i in items]
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_filter_ranker.py -v
```

Expected: 3 passed.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/filter/ranker.py tests/test_filter_ranker.py
git commit -m "feat(filter): rank offers by full-time, locality, specialty preference"
```

---

### Task 17: Telegram formatter — mensaje con botones

**Files:**
- Create: `navarra_edu_bot/telegram_bot/formatter.py`
- Create: `tests/test_telegram_formatter.py`

- [ ] **Step 1: Test**

Crea `tests/test_telegram_formatter.py`:

```python
from datetime import datetime

from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons
from navarra_edu_bot.storage.models import Offer


def _offer() -> Offer:
    return Offer(
        offer_id="O-42",
        body="0590",
        specialty="Tecnología",
        locality="Pamplona",
        center="IES Example",
        hours_per_week=22,
        duration="Curso completo",
        raw_html_hash="h",
        seen_at=datetime.now(),
    )


def test_format_message_contains_key_fields():
    text = format_offer_message(_offer())
    assert "Tecnología" in text
    assert "Pamplona" in text
    assert "22" in text
    assert "O-42" in text or "IES Example" in text


def test_buttons_have_callback_data_with_offer_id():
    markup = offer_buttons(_offer())
    callbacks = [btn.callback_data for row in markup.inline_keyboard for btn in row]
    assert any("apply:O-42" == c for c in callbacks)
    assert any("discard:O-42" == c for c in callbacks)
```

- [ ] **Step 2: Implementar**

Crea `navarra_edu_bot/telegram_bot/formatter.py`:

```python
from __future__ import annotations

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from navarra_edu_bot.storage.models import Offer


def format_offer_message(offer: Offer) -> str:
    return (
        f"<b>{offer.specialty}</b> ({offer.body})\n"
        f"📍 {offer.locality} — {offer.center}\n"
        f"⏱ {offer.hours_per_week} h/semana · {offer.duration}\n"
        f"<code>{offer.offer_id}</code>"
    )


def offer_buttons(offer: Offer) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("✅ Aplicar", callback_data=f"apply:{offer.offer_id}"),
                InlineKeyboardButton("❌ Descartar", callback_data=f"discard:{offer.offer_id}"),
            ]
        ]
    )
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_telegram_formatter.py -v
```

Expected: 2 passed.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/telegram_bot/formatter.py tests/test_telegram_formatter.py
git commit -m "feat(telegram): format offers as messages with inline buttons"
```

---

### Task 18: Callbacks de botones → storage

**Files:**
- Create: `navarra_edu_bot/telegram_bot/callbacks.py`

- [ ] **Step 1: Implementar handler**

Crea `navarra_edu_bot/telegram_bot/callbacks.py`:

```python
from __future__ import annotations

import structlog
from telegram import Update
from telegram.ext import CallbackQueryHandler, ContextTypes

from navarra_edu_bot.storage.db import Storage

log = structlog.get_logger()


def build_callback_handler(storage: Storage) -> CallbackQueryHandler:
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
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text(f"{query.message.text_html}\n\n✅ <b>Pre-seleccionada</b>", parse_mode="HTML")
        elif action == "discard":
            storage.mark_preselected(offer_id, preselected=False)
            await query.edit_message_reply_markup(reply_markup=None)
            await query.edit_message_text(f"{query.message.text_html}\n\n❌ Descartada", parse_mode="HTML")
        else:
            log.warning("unknown_action", action=action)

    return CallbackQueryHandler(_handle)
```

- [ ] **Step 2: Commit**

```bash
git add navarra_edu_bot/telegram_bot/callbacks.py
git commit -m "feat(telegram): callback handler wires buttons to storage"
```

---

### Task 19: Orchestrator — integra fetch + filter + rank + notify

**Files:**
- Create: `navarra_edu_bot/orchestrator.py`
- Create: `tests/test_orchestrator.py`

- [ ] **Step 1: Test con dobles**

Crea `tests/test_orchestrator.py`:

```python
from datetime import datetime
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from navarra_edu_bot.config.schema import AppConfig, ListEntry
from navarra_edu_bot.orchestrator import notify_new_offers
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer


def _offer(oid: str, specialty: str = "Tecnología", locality: str = "Pamplona") -> Offer:
    return Offer(
        offer_id=oid, body="0590", specialty=specialty, locality=locality,
        center="IES", hours_per_week=22, duration="Curso", raw_html_hash="h",
        seen_at=datetime.now(),
    )


@pytest.mark.asyncio
async def test_notify_new_offers_sends_only_eligible(tmp_path: Path, valid_config_dict: dict):
    storage = Storage(tmp_path / "s.db")
    storage.init_schema()

    cfg = AppConfig.model_validate(valid_config_dict)
    offers = [
        _offer("OK", specialty="Tecnología"),
        _offer("NO", specialty="Nuclear"),
    ]
    notifier = AsyncMock()

    # 2026-04-20 = Monday
    await notify_new_offers(
        offers=offers,
        now=datetime(2026, 4, 20, 13, 35),
        config=cfg,
        storage=storage,
        send=notifier,
    )

    sent_ids = [call.args[0].offer_id for call in notifier.await_args_list]
    assert sent_ids == ["OK"]
```

- [ ] **Step 2: Implementar orchestrator**

Crea `navarra_edu_bot/orchestrator.py`:

```python
from __future__ import annotations

from datetime import datetime
from typing import Awaitable, Callable

from navarra_edu_bot.config.schema import AppConfig
from navarra_edu_bot.filter.eligibility import is_eligible
from navarra_edu_bot.filter.ranker import rank_offers
from navarra_edu_bot.storage.db import Storage
from navarra_edu_bot.storage.models import Offer

Sender = Callable[[Offer], Awaitable[None]]


async def notify_new_offers(
    *,
    offers: list[Offer],
    now: datetime,
    config: AppConfig,
    storage: Storage,
    send: Sender,
) -> None:
    eligible = [
        o
        for o in offers
        if is_eligible(o, now, config.available_lists, config.thursday_open_specialties)
    ]
    ranked = rank_offers(
        eligible,
        preferred_localities=config.user.preferred_localities,
        specialty_order=config.user.specialty_preference_order,
    )
    for offer in ranked:
        if storage.get_offer(offer.offer_id) is not None:
            continue  # ya notificada previamente
        storage.upsert_offer(offer)
        await send(offer)
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_orchestrator.py -v
```

Expected: 1 passed.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/orchestrator.py tests/test_orchestrator.py
git commit -m "feat(orchestrator): filter + rank + notify new offers"
```

---

### Task 20: CLI `run-once` — integración completa dry-run

**Files:**
- Modify: `navarra_edu_bot/cli.py`

- [ ] **Step 1: Añadir comando `run-once`**

Añade a `navarra_edu_bot/cli.py`:

```python
@main.command("run-once")
@click.option("--headless/--headed", default=True)
def run_once(headless: bool) -> None:
    """Execute one complete cycle: fetch, filter, notify (NO apply)."""
    from datetime import datetime
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.orchestrator import notify_new_offers
    from navarra_edu_bot.scraper.fetch import fetch_offers
    from navarra_edu_bot.storage.db import Storage
    from navarra_edu_bot.telegram_bot.callbacks import build_callback_handler
    from navarra_edu_bot.telegram_bot.client import build_bot_app
    from navarra_edu_bot.telegram_bot.formatter import format_offer_message, offer_buttons

    config_path = Path("~/.navarra-edu-bot/config.yaml").expanduser()
    cfg = load_config(config_path)

    storage = Storage(cfg.runtime.storage_path)
    storage.init_schema()

    token = _keychain_read("telegram-token")
    chat_id = int(_keychain_read("telegram-chat-id"))
    username = _keychain_read("educa-username")
    password = _keychain_read("educa-password")

    app = build_bot_app(token=token, chat_id=chat_id)
    app.add_handler(build_callback_handler(storage))

    async def _run() -> None:
        offers = await fetch_offers(username=username, password=password, headless=headless)
        async with app:
            async def _send(offer):
                await app.bot.send_message(
                    chat_id=chat_id,
                    text=format_offer_message(offer),
                    reply_markup=offer_buttons(offer),
                    parse_mode="HTML",
                )

            await notify_new_offers(
                offers=offers,
                now=datetime.now(),
                config=cfg,
                storage=storage,
                send=_send,
            )
            # Keep polling for callbacks for 60 s to capture user presses.
            await app.start()
            await app.updater.start_polling()
            await asyncio.sleep(60)
            await app.updater.stop()
            await app.stop()

    asyncio.run(_run())
    click.echo(f"run-once complete. Pre-selected today: {storage.list_preselected_today(now=datetime.now())}")
```

- [ ] **Step 2: Ejecutar manualmente dentro de la ventana 13:30-14:00 un día laborable**

```bash
python -m navarra_edu_bot run-once --headed
```

Expected: recibes mensajes Telegram con cada oferta elegible, pulsas botones, al final el CLI imprime los offer_id pre-seleccionados.

- [ ] **Step 3: Commit**

```bash
git add navarra_edu_bot/cli.py
git commit -m "feat(cli): add `run-once` command for end-to-end dry-run cycle"
```

---

### Task 21: Añadir logging estructurado

**Files:**
- Create: `navarra_edu_bot/logging_config.py`
- Modify: `navarra_edu_bot/cli.py`

- [ ] **Step 1: Implementar configuración de logging**

Crea `navarra_edu_bot/logging_config.py`:

```python
from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

import structlog


def configure_logging(log_path: Path | str, level: str = "INFO") -> None:
    log_dir = Path(log_path).expanduser()
    log_dir.mkdir(parents=True, exist_ok=True)

    handler = logging.handlers.TimedRotatingFileHandler(
        log_dir / "bot.log", when="midnight", backupCount=30, encoding="utf-8"
    )
    handler.setFormatter(logging.Formatter("%(message)s"))

    root = logging.getLogger()
    root.handlers.clear()
    root.addHandler(handler)
    root.addHandler(logging.StreamHandler())
    root.setLevel(level)

    structlog.configure(
        processors=[
            structlog.processors.TimeStamper(fmt="iso"),
            structlog.processors.add_log_level,
            structlog.processors.StackInfoRenderer(),
            structlog.processors.format_exc_info,
            structlog.processors.JSONRenderer(),
        ],
        wrapper_class=structlog.make_filtering_bound_logger(logging.getLevelName(level)),
    )
```

- [ ] **Step 2: Llamar a configure_logging al inicio del CLI**

Edita `navarra_edu_bot/cli.py` añadiendo a `main`:

```python
@click.group()
@click.pass_context
def main(ctx: click.Context) -> None:
    """Navarra Edu Bot CLI."""
    from pathlib import Path

    from navarra_edu_bot.config.loader import load_config
    from navarra_edu_bot.logging_config import configure_logging

    try:
        cfg = load_config(Path("~/.navarra-edu-bot/config.yaml").expanduser())
        configure_logging(cfg.runtime.log_path, cfg.runtime.log_level)
    except FileNotFoundError:
        # El comando ping no requiere config.
        pass
```

- [ ] **Step 3: Ejecutar algún comando y verificar log en fichero**

```bash
python -m navarra_edu_bot ping
tail ~/.navarra-edu-bot/logs/bot.log
```

Expected: ves líneas JSON.

- [ ] **Step 4: Commit**

```bash
git add navarra_edu_bot/logging_config.py navarra_edu_bot/cli.py
git commit -m "feat(logging): structlog with daily-rotated file handler"
```

---

### Task 22: Checkpoint Fase 2 — verificación integrada

- [ ] **Step 1: Ejecutar `run-once` una semana laborable completa**

Cada día L–V entre 13:35 y 14:00:

```bash
python -m navarra_edu_bot run-once 2>&1 | tee ~/.navarra-edu-bot/logs/run-$(date +%F-%H%M).log
```

Validar:
- [ ] Las ofertas notificadas coinciden con las visibles en el portal.
- [ ] El filtrado por día de la semana es correcto (L/M/X/V → solo `Disponible`; J → open).
- [ ] El ranking: jornada completa arriba, Pamplona/Orkoien/Barañáin preferidas, orden Tecnología > Matemáticas > Dibujo respetado.
- [ ] Los botones responden y `is_preselected` queda correcto en SQLite.
- [ ] Los logs diarios son legibles.

- [ ] **Step 2: Revisar `formacion-especialidades.md` con el usuario**

El usuario confirma o corrige la tabla de correspondencia. Si hay correcciones, actualizar `config.example.yaml` y el config activo.

- [ ] **Step 3: Tag de versión**

```bash
git tag v0.2.0-phase2 -m "Phase 2: filter + rank + Telegram interactive notifications"
```

- [ ] **Step 4: Iniciar plan de Fase 3**

Invocar al usuario: "Fase 2 completada y estable. ¿Procedemos a planificar Fase 3 (scheduler + launchd + watchdog + canary) en un plan nuevo?"

---

## Outline de Fases 3–5 (a redactar en planes propios)

Estas fases se planifican en documentos separados **tras completar Fase 2** con 5 días laborables de uso real sin incidencias. Aquí queda el esqueleto de alcance.

### Fase 3 — Scheduler, keep-awake, watchdog, canary

- Instalar `launchd` plist (rellenar placeholders del template de Task 5).
- Comando `run-daily`: gestiona la ventana 13:25-14:05, `caffeinate`, bucle de polling 15 s.
- `pmset schedule wake` 13:20.
- Health-check al arranque (red + auth).
- Canary diario 12:00: login + fetch + logout, notifica si falla.
- Comandos Telegram `/status` y `/test`.
- Watchdog externo en launchd (job secundario cada 5 min).
- Recordatorios Telegram si hay ofertas sin decidir a las 13:45 y 13:55.
- **Criterio de cierre:** una semana laborable completa en la que el bot arranca solo, notifica, recibe botones y se apaga limpiamente sin intervención.

### Fase 4 — Applicator en dry-run + fast-path jueves

- Módulo `applicator/`: pre-navegación desde 13:58, warm-standby dos contextos Playwright, NTP sync, `asyncio.gather` a las 14:00:00.000.
- Submit por POST directo con cookies (aiohttp) + fallback a click.
- Reconciliación post-disparo con "mis aplicaciones".
- `dry_run: true` por defecto: todo el flujo menos el último POST.
- Métricas: `t_trigger`, `t_submit_sent`, `t_response_received` por oferta.
- Tests con mock server que simula: éxito, 500, session-expired, timeout.
- **Criterio de cierre:** 10 días laborables en dry-run sin discrepancias. Latencia dry-run medida <500 ms.

### Fase 5 — Activación real (flip)

- `dry_run: false` en config activa.
- Primer día con el usuario presente, capacidad de Ctrl-C.
- Semana de observación con reporte diario por Telegram.
- Primera revisión post-mortem a los 10 días reales.
- **Criterio de cierre:** una semana en real sin incidencias. A partir de ahí, operación normal.

---

## Self-review

Cobertura del spec:

| Spec sección | Tareas que lo cubren |
|---|---|
| 2. Perfil usuario y datos estáticos | Task 3 (config example), Task 7 (loader) |
| 3. Flujo diario | Task 20 (integración end-to-end, sin launchd todavía) |
| 4. Stack y módulos | Tasks 1, 2 (scaffold) + módulos en Tasks 6-20 |
| 4. Decisiones clave | Playwright Task 11, polling en Fase 3, NTP en Fase 4 |
| 5. Resiliencia sesión | Parcial (parser detecta session-expired Task 10); reauth automático en Fase 3 |
| 6. Fast-path jueves | Fase 4 |
| 7. Seguridad | Task 3 (Keychain), Task 7 (loader sin secretos) |
| 8. Riesgos | Dry-run Task 20, logs Task 21, canary Fase 3, dry-run 10 días Fase 4 |
| 9. Modo dry-run | Todo Fases 0-2 es dry-run por construcción (no hay applicator) |
| 10. Plan de pruebas | Tasks 6, 8, 10, 15, 16, 17, 19 (unit); Task 13 integración real |
| 11. Fases | Fases 0-2 completas aquí; 3-5 como outline |
| 12. Fuera de alcance | Respetado |

Ningún placeholder en código crítico. Todos los selectores "TODO: confirm" quedan marcados explícitamente para ajuste tras Task 9.
