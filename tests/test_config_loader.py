from pathlib import Path

import yaml

from navarra_edu_bot.config.loader import load_config


def test_load_config_from_file(tmp_path: Path, valid_config_dict: dict):
    cfg_path = tmp_path / "config.yaml"
    cfg_path.write_text(yaml.safe_dump(valid_config_dict))

    cfg = load_config(cfg_path)
    assert cfg.runtime.dry_run is True
    assert cfg.portal.base_url == "https://example.test/"
