"""Tests for the multi-source NTP helper."""
from __future__ import annotations

from unittest.mock import MagicMock, patch

from navarra_edu_bot.scheduler.ntp_sync import get_robust_ntp_offset


def _fake_response(offset: float):
    r = MagicMock()
    r.offset = offset
    return r


def test_robust_returns_median_of_three():
    """0.1, 0.2, 0.3 → median 0.2."""
    fake = MagicMock()
    fake.request.side_effect = [
        _fake_response(0.1),
        _fake_response(0.3),
        _fake_response(0.2),
    ]
    with patch(
        "navarra_edu_bot.scheduler.ntp_sync.ntplib.NTPClient", return_value=fake
    ):
        offset = get_robust_ntp_offset(servers=("a", "b", "c"))
    assert offset == 0.2


def test_robust_tolerates_one_failure():
    """Two succeed, one fails — median of the two successes."""
    fake = MagicMock()
    fake.request.side_effect = [
        _fake_response(0.1),
        Exception("timeout"),
        _fake_response(0.3),
    ]
    with patch(
        "navarra_edu_bot.scheduler.ntp_sync.ntplib.NTPClient", return_value=fake
    ):
        offset = get_robust_ntp_offset(servers=("a", "b", "c"))
    # Two values [0.1, 0.3] sorted → median index 1 → 0.3
    assert offset == 0.3


def test_robust_returns_zero_when_all_fail():
    fake = MagicMock()
    fake.request.side_effect = Exception("network down")
    with patch(
        "navarra_edu_bot.scheduler.ntp_sync.ntplib.NTPClient", return_value=fake
    ):
        offset = get_robust_ntp_offset(servers=("a", "b"))
    assert offset == 0.0
