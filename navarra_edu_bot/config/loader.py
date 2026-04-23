from __future__ import annotations

from pathlib import Path

import yaml

from navarra_edu_bot.config.schema import AppConfig


def load_config(path: Path | str) -> AppConfig:
    path = Path(path).expanduser()
    
    # If config doesn't exist in the persistent volume, try to copy it from the app source
    if not path.exists():
        import shutil
        local_config = Path("config.yaml")
        if local_config.exists():
            path.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(local_config, path)
        else:
            raise FileNotFoundError(f"Config file not found: {path} (and no fallback config.yaml found)")
            
    data = yaml.safe_load(path.read_text())
    return AppConfig.model_validate(data)
