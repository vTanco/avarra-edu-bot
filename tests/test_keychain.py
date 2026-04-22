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
