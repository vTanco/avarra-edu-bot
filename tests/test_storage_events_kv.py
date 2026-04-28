"""Tests for the events + kv_state additions to Storage."""
from __future__ import annotations

import time
from pathlib import Path

import pytest

from navarra_edu_bot.storage.db import Storage


@pytest.fixture
def storage(tmp_path: Path) -> Storage:
    s = Storage(tmp_path / "state.db")
    s.init_schema()
    return s


def test_log_event_and_recent(storage: Storage):
    storage.log_event(kind="poll_ok", payload={"fetched": 3})
    storage.log_event(kind="poll_error", level="error", payload={"error": "boom"})
    events = storage.recent_events(limit=10)
    assert len(events) == 2
    # Newest first
    assert events[0]["kind"] == "poll_error"
    assert events[1]["kind"] == "poll_ok"
    assert events[0]["payload"]["error"] == "boom"
    assert events[1]["payload"]["fetched"] == 3


def test_recent_events_filter_by_kind(storage: Storage):
    storage.log_event(kind="poll_ok", payload={})
    storage.log_event(kind="fast_path_done", payload={})
    storage.log_event(kind="poll_ok", payload={})
    only_polls = storage.recent_events(kind="poll_ok")
    assert len(only_polls) == 2
    assert all(e["kind"] == "poll_ok" for e in only_polls)


def test_recent_events_filter_by_level(storage: Storage):
    storage.log_event(kind="a", level="info", payload={})
    storage.log_event(kind="b", level="error", payload={})
    errors = storage.recent_events(level="error")
    assert len(errors) == 1
    assert errors[0]["kind"] == "b"


def test_kv_state_set_and_get(storage: Storage):
    assert storage.get_state("missing") is None
    storage.set_state("foo", "bar")
    assert storage.get_state("foo") == "bar"
    storage.set_state("foo", "baz")
    assert storage.get_state("foo") == "baz"


def test_kv_state_age_seconds(storage: Storage):
    assert storage.get_state_age_seconds("missing") is None
    storage.set_state("k", "v")
    age = storage.get_state_age_seconds("k")
    assert age is not None
    assert age < 1.0  # just set


def test_prune_events_keeps_recent_only(storage: Storage):
    # Two events
    storage.log_event(kind="x", payload={})
    storage.log_event(kind="y", payload={})
    # Prune anything older than 0 days — that effectively removes everything
    n = storage.prune_events(keep_days=0)
    assert n == 2
    assert storage.recent_events() == []
