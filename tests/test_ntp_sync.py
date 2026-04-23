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
