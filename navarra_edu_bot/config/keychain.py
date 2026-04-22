from __future__ import annotations

import subprocess

_SERVICE = "navarra-edu-bot"


class KeychainError(RuntimeError):
    pass


def read_secret(account: str) -> str:
    try:
        output = subprocess.check_output(
            ["security", "find-generic-password", "-s", _SERVICE, "-a", account, "-w"],
            text=True,
            stderr=subprocess.PIPE,
        )
    except subprocess.CalledProcessError as exc:
        raise KeychainError(f"Keychain entry not found: service={_SERVICE} account={account}") from exc
    return output.strip()
