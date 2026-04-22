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

## launchd scheduling (Phase 3+)

The plist template lives in `deploy/navarra-edu-bot.plist.template`. It is NOT
installed during phases 0–2 (no `run-daily` command exists yet). Installation
instructions will appear in the Phase 3 plan.
