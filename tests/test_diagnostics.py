"""Tests for the diagnostics package: snapshot, healthcheck, canary, backup."""
from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from navarra_edu_bot.diagnostics.backup import _make_local_copy, daily_backup
from navarra_edu_bot.diagnostics.canary import (
    CanaryResult,
    run_polling_canary,
)
from navarra_edu_bot.diagnostics.healthcheck import (
    ping,
    ping_fail,
    ping_start,
    ping_success,
)
from navarra_edu_bot.diagnostics.snapshot import capture_failure


# ---------- snapshot ----------

async def test_snapshot_writes_context_only_when_no_page_or_html(tmp_path):
    out = await capture_failure(
        base=tmp_path,
        label="poll_error",
        context={"error": "boom"},
    )
    assert out.exists()
    ctx = (out / "context.json").read_text()
    assert "boom" in ctx
    assert "poll_error" in ctx


async def test_snapshot_writes_html_when_provided(tmp_path):
    out = await capture_failure(
        base=tmp_path,
        label="parse_fail",
        html="<html><body>raw</body></html>",
    )
    assert (out / "dump.html").read_text() == "<html><body>raw</body></html>"


# ---------- healthcheck ----------

async def test_ping_no_op_when_env_var_missing(monkeypatch):
    monkeypatch.delenv("HEALTHCHECK_PING_URL", raising=False)
    # No exception, returns False
    assert await ping() is False
    assert await ping_success() is False
    assert await ping_start() is False
    assert await ping_fail() is False


async def test_ping_returns_true_on_2xx(monkeypatch):
    monkeypatch.setenv("HEALTHCHECK_PING_URL", "https://hc-ping.com/uuid")

    class FakeResp:
        status = 200

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

    class FakeSession:
        def __init__(self, *a, **kw): ...

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return None

        def post(self, *a, **kw):
            return FakeResp()

    with patch("aiohttp.ClientSession", FakeSession):
        ok = await ping()
    assert ok is True


# ---------- canary ----------

async def test_polling_canary_ok_when_session_returns_real_html():
    fake = MagicMock()
    fake.fetch_areapersonal_html = AsyncMock(
        return_value="""
        <html><body>
            <a href='/atp/logout.xhtml'>Logout</a>
            <a href='/atp/private/solicitud.xhtml?convid=1234&action=new'>Solicitar</a>
            <div class='ui-datatable'>
              <tbody id='_data'></tbody>
            </div>
        </body></html>
        """
    )
    result = await run_polling_canary(fake)
    assert isinstance(result, CanaryResult)
    assert result.ok
    assert "convid=1234" in result.message


async def test_polling_canary_fails_on_http_error():
    fake = MagicMock()
    fake.fetch_areapersonal_html = AsyncMock(side_effect=Exception("network down"))
    result = await run_polling_canary(fake)
    assert result.ok is False
    assert "HTTP fetch failed" in result.message


async def test_polling_canary_ok_even_when_convid_missing():
    """No convid in the HTML (e.g. outside the publication window) is NOT a fail."""
    fake = MagicMock()
    fake.fetch_areapersonal_html = AsyncMock(
        return_value=(
            "<html><body>"
            "<a href='/atp/logout.xhtml'>Logout</a>"
            "<div class='ui-datatable'><tbody id='_data'></tbody></div>"
            "</body></html>"
        )
    )
    result = await run_polling_canary(fake)
    assert result.ok is True
    assert "convid=n/a" in result.message


async def test_polling_canary_detects_convocatoria_ended():
    fake = MagicMock()
    fake.fetch_areapersonal_html = AsyncMock(
        return_value=(
            "<html><body><p>Ha finalizado el plazo de participación</p>"
            "<a href='/atp/logout.xhtml'>Logout</a></body></html>"
        )
    )
    result = await run_polling_canary(fake)
    assert result.ok is False
    assert result.detail == "convocatoria_ended"


# ---------- backup ----------

def test_make_local_copy_creates_gzipped_file(tmp_path: Path):
    db = tmp_path / "state.db"
    db.write_bytes(b"sqlite-fake-bytes")
    backup_path = _make_local_copy(db)
    assert backup_path.exists()
    assert backup_path.suffix == ".gz"
    assert "state-" in backup_path.name


async def test_daily_backup_no_telegram_path(tmp_path: Path):
    db = tmp_path / "state.db"
    db.write_bytes(b"x")
    out = await daily_backup(storage_path=db)
    assert out is not None
    assert out.exists()
