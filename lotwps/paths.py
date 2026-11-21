"""Filesystem layout for the LOTWPS / LOTIEM / BMH build.

Every runtime artifact lives under ``var/`` so the source tree stays clean.
"""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CONFIG = ROOT / "config"
VAR = ROOT / "var"
BUS = VAR / "bus"
AUDIO_CACHE = VAR / "audio"
PRODUCTS_OUT = VAR / "products"
EXPORTS = VAR / "export"
LOGS = VAR / "logs"
STATE = VAR / "state"

for _d in (DATA, CONFIG, VAR, BUS, AUDIO_CACHE, PRODUCTS_OUT, EXPORTS, LOGS, STATE):
    _d.mkdir(parents=True, exist_ok=True)

SETTINGS_FILE = CONFIG / "settings.json"


def bus_file(seq: int, token: str) -> Path:
    return BUS / f"{seq:012d}-{token}.json"


def rel(path: Path) -> str:
    """Path relative to the project root when possible (for display)."""
    try:
        return str(Path(path).resolve().relative_to(ROOT))
    except ValueError:
        return str(path)
