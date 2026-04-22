import pytest

from navarra_edu_bot.telegram_bot.client import build_bot_app


def test_build_bot_app_requires_token():
    with pytest.raises(ValueError, match="token"):
        build_bot_app(token="", chat_id=1)


def test_build_bot_app_returns_configured_app():
    app = build_bot_app(token="FAKE_TOKEN", chat_id=12345)
    assert app.bot.token == "FAKE_TOKEN"
