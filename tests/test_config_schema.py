import pytest
from pydantic import ValidationError

from navarra_edu_bot.config.schema import AppConfig, ListEntry


def test_list_entry_minimal():
    entry = ListEntry(body="0590", specialty="Tecnología")
    assert entry.body == "0590"
    assert entry.list_type is None


def test_list_entry_with_type():
    entry = ListEntry(body="0590", specialty="Tecnología", list_type="CONVOCATORIA")
    assert entry.list_type == "CONVOCATORIA"


def test_app_config_loads_valid_dict(valid_config_dict):
    cfg = AppConfig.model_validate(valid_config_dict)
    assert cfg.runtime.dry_run is True
    assert cfg.user.specialty_preference_order[0] == "Tecnología"
    assert len(cfg.available_lists) == 7


def test_app_config_rejects_invalid_body(valid_config_dict):
    valid_config_dict["available_lists"][0]["body"] = "9999"
    with pytest.raises(ValidationError, match="body"):
        AppConfig.model_validate(valid_config_dict)
