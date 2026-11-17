"""Configuration for the KLOT LOTWPS build.

The JSON file under ``config/settings.json`` is created on first run from the
defaults below and then owned by the user (edited by the GUIs or by hand).
"""

from __future__ import annotations

import copy
import json
import threading
from typing import Any

from . import paths

DEFAULTS: dict[str, Any] = {
    "app": {
        "name": "LOTWPS",
        "long_name": "LOT Weather Processing System",
        "wfo": "LOT",
        "wfo_name": "Chicago",
        "wfo_city": "Romeoville, Illinois",
        "version": "3.1.0",
        "build": "BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS",
        "timezone": "America/Chicago",
        "jurisdiction": "Chicago, Illinois and Northwest Indiana",
    },
    "text_workstation": {
        "title": "KLOT LOTIEM TEXT WORKSTATION",
        "host": "192.168.10.144",
        "ip": "192.168.10.144",
        "port": 6000,
        "settings_port": 2601,
        "callsign": "KLOT",
        "product_designator": "LOT",
        "addressee": "ALL",
        "wsfo_id": "CHI",
        "wrap": 69,
        "default_voice": "paul",
        "auto_wrap": True,
    },
    "lotiem": {
        "name": "LOTIEM",
        "long_name": "Chicago Illinois Iowa Environmental Mesonet",
        "future_name": "Chicago Illinois Integrated Emergency Manager",
        "station_id": "KLOT",
        "host": "127.0.0.1",
        "port": 6000,
        "transport": "file",  # "file" bus (default) or "tcp"
        "routes": {
            "BMH": True,
            "WWA": True,
            "LOCAL_OFFICIALS": True,
            "PUBLIC": True,
            "IEMBOT": True,
            "EMAIL": False,
            "WEBSITES": True,
        },
        "subscribers": {
            "IEMBOT": "iem@lot.noaa.gov",
            "EMAIL": "nws-chicago@noaa.gov",
            "WEBSITES": "https://weather.gov/chicago",
        },
    },
    "bmh": {
        "title": "BMH Network",
        "location": "Valparaiso, Indiana",
        "ip": "192.168.10.144",
        "port": 6000,
        "network_status": "ONLINE (1)",
        "default_hazard": "Tornado Warning",
        "ticker": "This is a test. 162.400 MHz WXJ75 Valparaiso IN",
    },
    "audio": {
        "sample_rate": 16000,
        "tone_seconds": 8.0,
        "tone_short_seconds": 3.0,
        "same_tone_hz": 1050,
        "same_mark_hz": 2083.3,
        "same_space_hz": 1562.5,
        "same_baud": 520.83,
        "same_repeat": 3,
        "pause_ms": 1000,
        "output_device": "default",
    },
    "voices": {
        "default": "paul",
        "order": ["paul", "david", "zira"],
        "paul": {
            "label": "VoiceText Paul",
            "engine": "voicetext",
            "exe": r"C:\Users\nicho\Downloads\nws-paul\nws-paul\bin\VTEditor_ENG.exe",
            "assets_dir": r"C:\Users\nicho\Downloads\nws-paul\nws-paul\bin",
            "fallback_sapi": "Microsoft David Desktop",
            "rate": -1,
            "pitch": "-3%",
            "render_mode": "auto",  # assets (all Paul) | auto (static IDs) | sapi
        },
        "david": {
            "label": "Microsoft David",
            "engine": "sapi",
            "sapi_name": "Microsoft David Desktop",
            "rate": -1,
            "volume": 100,
        },
        "zira": {
            "label": "Microsoft Zira",
            "engine": "sapi",
            "sapi_name": "Microsoft Zira Desktop",
            "rate": 0,
            "volume": 100,
        },
    },
    "broadcast": {
        "default_mode": "General",
        "modes": {
            "Winter Weather": [
                "ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:ZFPLOT",
                "@PRODUCT:HWOLOT", "OBSERVATIONS", "LONG_ID",
            ],
            "Flooding": [
                "ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:ZFPLOT",
                "@PRODUCT:HWOLOT", "@ACTIVE_ALERTS", "OBSERVATIONS", "LONG_ID",
            ],
            "Severe Weather": [
                "SEVERE_MESSAGE", "@AUTO_ID", "CURRENT_TIME", "@SEVERE_DYNAMIC",
                "@PRODUCT:ZFPLOT", "@PRODUCT:HWOLOT", "@ACTIVE_ALERTS", "LONG_ID",
            ],
            "Severe Weather Possible": [
                "ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:HWOLOT",
                "@PRODUCT:ZFPLOT", "OBSERVATIONS", "LONG_ID",
            ],
            "Off the Air": ["OFF_AIR", "OFF_AIR"],
            "Station ID Only": ["STATION_ID", "SHORT_ID", "EMR_STATION_ID"],
            "Current Time Only": ["CURRENT_TIME", "CURRENT_TIME"],
            "General": [
                "ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:ZFPLOT",
                "@PRODUCT:AFDLOT", "OBSERVATIONS", "@PRODUCT:HWOLOT", "LONG_ID",
            ],
            "Zone Forecast": [
                "ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:ZFPLOT",
                "OBSERVATIONS", "LONG_ID",
            ],
            "Severe Weather and Alert Summary": [
                "ADVANCE", "@AUTO_ID", "@ACTIVE_ALERTS", "@SEVERE_DYNAMIC", "LONG_ID",
            ],
        },
        "special_entries": [
            "@AUTO_ID", "@ACTIVE_ALERTS", "@SEVERE_DYNAMIC", "@PRODUCT:ZFPLOT",
            "@PRODUCT:AFDLOT", "@AUTO_SEVERE_ID", "@NEW_CON_ALERTS",
            "@CAN_EXP_ALERTS",
        ],
        "static_entries": [
            "ADVANCE", "EMR_STATION_ID", "PREPAREDNESS_ACTIONS", "SLGT_STATION_ID",
            "OFF_AIR", "STATION_ID", "SHORT_ID", "LONG_ID", "SEVERE_MESSAGE",
            "CURRENT_TIME",
        ],
        "queue_entries": [
            "ADVANCE", "EMR_STATION_ID", "PREPAREDNESS_ACTIONS", "SLGT_STATION_ID",
            "OFF_AIR", "STATION_ID", "SHORT_ID", "LONG_ID", "SEVERE_MESSAGE",
            "FORECAST", "OBSERVATIONS", "HWO", "CURRENT_TIME",
        ],
        "cycle_length": 8,
        "wednesday_test": True,
        "static_overrides": {},
        "listening_area": {
            "enable_filter": True,
            "allow_uncoded": True,
            "states": ["IL", "IN"],
            "ugc": [
                "ILZ003", "ILZ004", "ILZ005", "ILZ006", "ILZ007", "ILZ008",
                "ILZ009", "ILZ010", "ILZ011", "ILZ012", "ILZ013", "ILZ014",
                "ILZ015", "ILZ016", "ILZ017", "ILZ018", "ILZ019", "ILZ020",
                "ILZ021", "ILZ022", "ILZ023", "ILZ024", "ILZ025", "ILZ026",
                "ILZ027", "ILZ028", "ILZ029", "ILZ030", "ILZ031", "ILZ032",
                "ILZ033", "ILZ034", "ILZ035", "ILZ036", "ILZ037", "ILZ038",
                "ILZ039", "ILZ040", "ILZ041", "INZ001", "INZ002", "INZ003",
                "INZ004", "INZ005", "INZ006", "INZ007", "INZ008", "INZ009",
                "INZ010", "INZ011", "INZ012", "INZ013", "INZ014", "INZ015",
                "INZ016", "INZ017", "INZ018", "INZ019", "INZ020", "INZ021",
                "INZ022", "INZ023", "INZ024", "INZ025", "INZ026", "INZ027",
                "INZ028", "INZ029", "INZ030", "INZ031", "INZ032", "LMZ740",
                "LMZ741", "LMZ742", "LMZ743", "LMZ744", "LMZ745",
            ],
            "text": (
                "Listening area: northeast Illinois and northwest Indiana. "
                "Lake and Porter counties in Indiana are the primary service area "
                "for WXJ75 Valparaiso and KBB58 Gary. Coastal marine zones "
                "LMZ740 through LMZ745 are included for the Illinois and Indiana "
                "nearshore waters of Lake Michigan."
            ),
        },
    },
    "stations": [
        {
            "id": "WXJ75",
            "name": "WXJ75",
            "city": "Valparaiso",
            "state": "IN",
            "frequency": "162.400",
            "township": "Porter Township",
            "coverage": "Porter Township, Valparaiso, Chesterton, and Portage",
            "cities": [
                "Valparaiso", "Hebron", "Rensselaer", "Chesterton", "Portage",
                "Dyer", "Schererville", "Merrillville", "Crown Point",
            ],
            "counties": ["Lake", "Porter"],
            "ugc": ["INZ001", "INZ002"],
            "same": ["018089", "018127"],
            "lat": 41.4731,
            "lon": -87.0611,
            "ip": "192.168.10.144",
            "port": 6000,
            "active": True,
            "voice": "paul",
            "paul_assets": {
                "STATION_ID": "WXJ75_ID.wav",
                "SHORT_ID": "WXJ75_ID.wav",
                "LONG_ID": "WXJ75_Long_ID.wav",
                "CURRENT_TIME": "Current_Time.wav",
                "FORECAST": "Forecast.wav",
                "OBSERVATIONS": "Observations.wav",
                "AFD": "AFD.wav",
            },
        },
        {
            "id": "KBB58",
            "name": "KBB58",
            "city": "Gary",
            "state": "IN",
            "frequency": "162.425",
            "township": "Lake Township",
            "coverage": "Lake Township, Gary, Merrillville, and Hammond",
            "cities": [
                "Gary", "Merrillville", "Schererville", "Dyer", "St John",
                "Crown Point", "Hammond", "Valparaiso",
            ],
            "counties": ["Lake", "Porter"],
            "ugc": ["INZ001", "INZ002"],
            "same": ["018089", "018127"],
            "lat": 41.5645,
            "lon": -87.3365,
            "ip": "192.168.10.144",
            "port": 6000,
            "active": True,
            "voice": "paul",
            "paul_assets": {
                "STATION_ID": "KBB58_ID.wav",
                "SHORT_ID": "KBB58_ID.wav",
                "LONG_ID": "KBB58_Long_ID.wav",
                "CURRENT_TIME": "Current_Time.wav",
                "FORECAST": "Forecast.wav",
                "OBSERVATIONS": "Observations.wav",
            },
        },
        {
            "id": "WNG689",
            "name": "WNG689",
            "city": "Valparaiso",
            "state": "IN",
            "frequency": "162.450",
            "township": "Porter Township",
            "coverage": "Porter Township, Valparaiso, Chesterton, and Portage",
            "cities": ["Valparaiso", "Chesterton", "Portage"],
            "counties": ["Lake", "Porter"],
            "ugc": ["INZ001", "INZ002"],
            "same": ["018089", "018127"],
            "lat": 41.51,
            "lon": -87.02,
            "ip": "192.168.10.144",
            "port": 6000,
            "active": False,
            "voice": "paul",
            "paul_assets": {},
        },
    ],
    "network": {
        "bmh_host": "192.168.10.144",
        "bmh_port": 6000,
        "wwa_host": "192.168.10.144",
        "wwa_port": 6001,
        "poll_seconds": 2.0,
    },
    "output": {
        "write_products": True,
        "write_audio": True,
        "keep_renders": 64,
    },
}


class Settings:
    """Dict-backed settings with dotted access."""

    def __init__(self, data: dict[str, Any], path=None):
        self._data = data
        self._path = path or paths.SETTINGS_FILE
        self._lock = threading.RLock()

    # -- loading ---------------------------------------------------------
    @classmethod
    def load(cls) -> "Settings":
        data = copy.deepcopy(DEFAULTS)
        if paths.SETTINGS_FILE.exists():
            try:
                user = json.loads(paths.SETTINGS_FILE.read_text(encoding="utf-8"))
                _deep_merge(data, user)
            except (json.JSONDecodeError, OSError):
                pass
        obj = cls(data)
        obj.save()
        return obj

    def save(self) -> None:
        with self._lock:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False), encoding="utf-8"
            )

    # -- access ----------------------------------------------------------
    def get(self, dotted: str, default: Any = None) -> Any:
        node: Any = self._data
        for part in dotted.split("."):
            if not isinstance(node, dict) or part not in node:
                return default
            node = node[part]
        return node

    def set(self, dotted: str, value: Any) -> None:
        parts = dotted.split(".")
        node = self._data
        for part in parts[:-1]:
            node = node.setdefault(part, {})
        node[parts[-1]] = value

    def update(self, mapping: dict[str, Any]) -> None:
        for k, v in mapping.items():
            self.set(k, v)

    def to_dict(self) -> dict[str, Any]:
        return copy.deepcopy(self._data)

    # -- domain helpers --------------------------------------------------
    @property
    def raw(self) -> dict[str, Any]:
        return self._data

    def stations(self, active_only: bool = False) -> list[dict[str, Any]]:
        items = self.get("stations", []) or []
        return [s for s in items if s.get("active") or not active_only]

    def station(self, station_id: str) -> dict[str, Any]:
        for s in self.stations():
            if s.get("id") == station_id:
                return s
        raise KeyError(station_id)

    def modes(self) -> dict[str, list[str]]:
        return self.get("broadcast.modes", {})

    def mode_list(self) -> list[str]:
        return list(self.modes().keys())

    def listening_ugc(self) -> list[str]:
        return self.get("broadcast.listening_area.ugc", [])

    def listening_filter(self) -> bool:
        return bool(self.get("broadcast.listening_area.enable_filter", True))

    def voice_cfg(self, key: str) -> dict[str, Any]:
        return self.get(f"voices.{key}", {}) | {"key": key}

    def voice_keys(self) -> list[str]:
        return list(self.get("voices.order", ["paul", "david", "zira"]))


def _deep_merge(base: dict[str, Any], extra: dict[str, Any]) -> None:
    for key, value in extra.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_merge(base[key], value)
        else:
            base[key] = value


_SETTINGS: Settings | None = None
_SETTINGS_LOCK = threading.Lock()


def settings() -> Settings:
    global _SETTINGS
    with _SETTINGS_LOCK:
        if _SETTINGS is None:
            _SETTINGS = Settings.load()
        return _SETTINGS


def reload_settings() -> Settings:
    global _SETTINGS
    with _SETTINGS_LOCK:
        _SETTINGS = Settings.load()
        return _SETTINGS
