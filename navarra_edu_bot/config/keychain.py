from __future__ import annotations

import os
from pathlib import Path
import subprocess

_SERVICE = "navarra-edu-bot"


class KeychainError(RuntimeError):
    pass


def _load_env_file_if_present() -> None:
    env_file = os.environ.get("ENV_FILE")
    candidates = (
        [Path(env_file)]
        if env_file
        else [Path(".env"), Path("~/.navarra-edu-bot/.env").expanduser()]
    )
    for candidate in candidates:
        if candidate.is_file():
            try:
                for line in candidate.read_text().splitlines():
                    line = line.strip()
                    if line and not line.startswith("#") and "=" in line:
                        k, v = line.split("=", 1)
                        k = k.strip()
                        v = v.strip().strip("'\"")
                        if k and k not in os.environ:
                            os.environ[k] = v
            except Exception:
                pass


def read_secret(account: str) -> str:
    env_key = account.replace("-", "_").upper()
    if env_value := os.environ.get(env_key):
        return env_value

    _load_env_file_if_present()
    if env_value := os.environ.get(env_key):
        return env_value

    try:
        output = subprocess.check_output(
            ["security", "find-generic-password", "-s", _SERVICE, "-a", account, "-w"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise KeychainError(f"Keychain entry not found: service={_SERVICE} account={account}") from exc
    return output.strip()
