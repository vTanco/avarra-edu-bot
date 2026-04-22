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
