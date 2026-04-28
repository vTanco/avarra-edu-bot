"""Tests for the new parser helpers added in the improvements pass:

- discover_active_convid
- is_convocatoria_ended
- parse_applied_offer_ids
"""
from __future__ import annotations

from pathlib import Path

import pytest

from navarra_edu_bot.scraper.parser import (
    discover_active_convid,
    is_convocatoria_ended,
    parse_applied_offer_ids,
)

FIXTURES = Path(__file__).parent / "fixtures"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# ---------- discover_active_convid ----------

def test_discover_active_convid_extracts_from_real_page():
    html = _read("offers_list.html")
    assert discover_active_convid(html) == "1204"


def test_discover_active_convid_returns_highest_when_multiple():
    html = (
        '<a href="/atp/foo?convid=1199">old</a>'
        '<a href="/atp/bar?convid=1207">new</a>'
        '<a href="/atp/baz?convid=1206">middle</a>'
    )
    assert discover_active_convid(html) == "1207"


def test_discover_active_convid_returns_none_when_absent():
    assert discover_active_convid("<html><body>no convid here</body></html>") is None


def test_discover_active_convid_handles_garbage_input():
    # Should not raise on weird input
    assert discover_active_convid("") is None
    assert discover_active_convid("convid=") is None


# ---------- is_convocatoria_ended ----------

def test_is_convocatoria_ended_detects_real_phrase():
    html = (
        "<html><body><p>Ha finalizado el plazo de participación de "
        "la convocatoria.</p></body></html>"
    )
    assert is_convocatoria_ended(html) is True


def test_is_convocatoria_ended_handles_accent_stripped():
    html = "<p>Ha finalizado el plazo de participacion</p>"
    assert is_convocatoria_ended(html) is True


def test_is_convocatoria_ended_false_on_normal_page():
    html = _read("offers_list.html")
    assert is_convocatoria_ended(html) is False


def test_is_convocatoria_ended_false_on_session_expired():
    html = _read("session_expired.html")
    # Session expired is a different state — the convocatoria itself isn't ended
    assert is_convocatoria_ended(html) is False


# ---------- parse_applied_offer_ids ----------

def test_parse_applied_offer_ids_returns_list_for_offers_listing_format():
    # offers_list.html is the same DataTable format used on solicitudes.xhtml,
    # so this exercises the same parsing path.
    html = _read("offers_list.html")
    ids = parse_applied_offer_ids(html)
    assert isinstance(ids, list)
    # Real fixture has at least one row with an offer id
    assert all(i.isdigit() for i in ids)


def test_parse_applied_offer_ids_empty_when_no_rows():
    # Bare authenticated page with no datatable rows
    html = "<html><body><a href='/atp/logout.xhtml'>Logout</a></body></html>"
    assert parse_applied_offer_ids(html) == []
