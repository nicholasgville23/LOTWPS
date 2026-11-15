from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any


DEFAULT_CONFIG: dict[str, Any] = {
    "app": {"name": "BMH NOAA Weather Radio - LOTWPS / LOTIEM", "office": "LOT", "wmo_origin": "KLOT", "wsfo_id": "CHI", "timezone": "America/Chicago", "language": "en", "refresh_seconds": 300, "manual_broadcast_loop": True},
    "nws": {"base_url": "https://api.weather.gov", "user_agent": "LOTWPS-Lab/0.1 (configure-contact@example.invalid)", "timeout_seconds": 15, "points": []},
    "region": {"name": "Northeast Illinois and Northwest Indiana", "ugc_codes": [], "allow_routine_without_codes": True, "coastal_stations_only_marine": True},
    "voices": {"backend": "sapi", "profiles": {"paul": {"display_name": "NeoSpeech Paul / VoiceText Paul", "match": ["paul"]}, "david": {"display_name": "David", "match": ["david"]}, "zira": {"display_name": "Zira", "match": ["zira"]}}, "voicetext_executable": "", "voicetext_command": []},
    "broadcast": {"lab_audio_only": True, "require_test_label_for_manual_eas": True, "header_repeats": 3, "eom_repeats": 3, "attention_tone_hz": 1050, "attention_tone_seconds": 8, "sample_rate": 48000, "output_dir": "output", "cycle_order": ["STATION_ID", "CURRENT_TIME", "ACTIVE_ALERTS", "FORECAST", "OBSERVATIONS", "HWO"]},
    "network": {"enabled": False, "transport": "simulation", "bind_host": "127.0.0.1", "bind_port": 6000, "stations": []},
    "climate": {"normals": {}, "records": {}},
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    merged = dict(base)
    for key, value in override.items():
        if isinstance(value, dict) and isinstance(merged.get(key), dict):
            merged[key] = deep_merge(merged[key], value)
        else:
            merged[key] = value
    return merged


def load_config(path: str | Path = "config.json") -> dict[str, Any]:
    config_path = Path(path)
    if not config_path.exists():
        example = Path("config.example.json")
        source = example.read_text(encoding="utf-8") if config_path.name == "config.json" and example.exists() else json.dumps(DEFAULT_CONFIG, indent=2)
        config_path.write_text(source, encoding="utf-8")
    try:
        user_config = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"Invalid JSON in {config_path}: {exc}") from exc
    if not isinstance(user_config, dict):
        raise ValueError("Configuration root must be a JSON object")
    config = deep_merge(DEFAULT_CONFIG, user_config)
    if config["broadcast"].get("lab_audio_only") is not True:
        raise ValueError("lab_audio_only must remain true in this build")
    if config["network"].get("transport") != "simulation":
        raise ValueError("Only the simulation network transport is supported")
    return config


def env_override(config: dict[str, Any]) -> dict[str, Any]:
    if os.getenv("LOTWPS_NWS_USER_AGENT"):
        config["nws"]["user_agent"] = os.environ["LOTWPS_NWS_USER_AGENT"]
    if os.getenv("LOTWPS_OUTPUT_DIR"):
        config["broadcast"]["output_dir"] = os.environ["LOTWPS_OUTPUT_DIR"]
    return config
