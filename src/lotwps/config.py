"""Configuration loading and persistence for the LOTWPS desktop client."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "config"
STATIONS_FILE = CONFIG_DIR / "stations.json"
APP_SETTINGS_FILE = CONFIG_DIR / "app.json"

DEFAULT_APP_SETTINGS: dict[str, Any] = {
    "window_title": "KLOT LOTIEM TEXT WORKSTATION",
    "nws_user_agent": "LOTWPS/0.1 (configure a contact address in local settings)",
    "refresh_seconds": 300,
    "broadcast_interval_seconds": 900,
    "default_voice": "David",
    "voicetext_exe": "",
    "bmh_target_host": "127.0.0.1",
    "bmh_target_port": 6000,
    "bmh_enabled": False,
    "default_bbb": "NOR",
    "default_wfo": "LOT",
    "language": "en-US",
}


def read_json(path: Path, fallback: dict[str, Any]) -> dict[str, Any]:
    if not path.exists():
        return fallback.copy()
    try:
        with path.open("r", encoding="utf-8") as stream:
            value = json.load(stream)
        if not isinstance(value, dict):
            raise ValueError(f"{path.name} must contain a JSON object")
        return value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        raise RuntimeError(f"Unable to read configuration {path}: {exc}") from exc


def write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as stream:
        json.dump(value, stream, indent=2, ensure_ascii=False)
        stream.write("\n")
    temporary.replace(path)


def load_app_settings() -> dict[str, Any]:
    settings = DEFAULT_APP_SETTINGS.copy()
    settings.update(read_json(APP_SETTINGS_FILE, {}))
    return settings


def load_stations() -> list[dict[str, Any]]:
    data = read_json(STATIONS_FILE, {"stations": []})
    stations = data.get("stations", [])
    if not isinstance(stations, list):
        raise RuntimeError("config/stations.json: 'stations' must be a list")
    return [station for station in stations if isinstance(station, dict) and station.get("enabled", True)]
