from pathlib import Path

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def valid_config_dict() -> dict:
    return {
        "portal": {"base_url": "https://example.test/", "login_path": "index.xhtml"},
        "user": {
            "preferred_localities": ["Pamplona"],
            "specialty_preference_order": ["Tecnología", "Matemáticas", "Dibujo"],
        },
        "available_lists": [
            {"body": "0590", "specialty": "Equipos Electrónicos"},
            {"body": "0590", "specialty": "Organización y Proyectos de Fabricación Mecánica"},
            {"body": "0590", "specialty": "Sistemas Electrotécnicos y Automáticos"},
            {"body": "0590", "specialty": "Sistemas Electrónicos"},
            {"body": "0590", "specialty": "Tecnología", "list_type": "CONVOCATORIA"},
            {"body": "0598", "specialty": "Fabricación e Instalación de Carpintería y Mueble"},
            {"body": "0598", "specialty": "Mantenimiento de Vehículos"},
        ],
        "thursday_open_specialties": [
            {"body": "0590", "specialty": "Tecnología"},
        ],
        "scheduler": {
            "daily_start": "13:25",
            "daily_end": "14:05",
            "poll_interval_seconds": 15,
        },
        "runtime": {
            "dry_run": True,
            "log_level": "INFO",
            "storage_path": "~/.navarra-edu-bot/state.db",
            "log_path": "~/.navarra-edu-bot/logs/",
        },
    }
