from __future__ import annotations

from pathlib import Path

import yaml

from navarra_edu_bot.config.schema import AppConfig


def load_config(path: Path | str) -> AppConfig:
    path = Path(path).expanduser()
    if not path.exists():
        raise FileNotFoundError(f"Config file not found: {path}")
    data = yaml.safe_load(path.read_text())
    return AppConfig.model_validate(data)
