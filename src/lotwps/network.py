from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from .models import Station


@dataclass(slots=True)
class StationStatus:
    station_id: str
    status: str = "SIMULATED ONLINE"
    mode: str = "GENERAL"
    last_action: str = "Initialized in simulation mode"
    updated_at: str = ""


class BMHNetwork:
    """In-memory station registry. It deliberately does not open network sockets."""

    def __init__(self, station_values: list[dict[str, Any]]):
        self.stations = {station.station_id: station for station in (Station.from_dict(x) for x in station_values)}
        self.status = {key: StationStatus(key, updated_at=datetime.now().astimezone().isoformat()) for key in self.stations}

    def command(self, station_id: str, action: str) -> StationStatus:
        if station_id not in self.status:
            raise KeyError(f"Unknown station {station_id}")
        status = self.status[station_id]
        allowed = {"START TX", "STOP TX", "NEXT PRODUCT", "RESTART SERVICE", "STATION ID ONLY", "OFF THE AIR"}
        if action not in allowed:
            raise ValueError(f"Unsupported simulated station action: {action}")
        if action == "START TX":
            status.status = "SIMULATED PLAYOUT ACTIVE"
        elif action == "STOP TX":
            status.status = "SIMULATED PLAYOUT STOPPED"
        elif action == "OFF THE AIR":
            status.status = "SIMULATED OFF THE AIR"
        elif action == "STATION ID ONLY":
            status.mode = "STATION ID ONLY"
        elif action == "RESTART SERVICE":
            status.status = "SIMULATED ONLINE"
        status.last_action = action
        status.updated_at = datetime.now().astimezone().isoformat()
        return status

    def set_mode(self, station_id: str, mode: str) -> StationStatus:
        if station_id not in self.status:
            raise KeyError(f"Unknown station {station_id}")
        status = self.status[station_id]
        status.mode, status.last_action = mode, f"Mode set to {mode} (simulation)"
        status.updated_at = datetime.now().astimezone().isoformat()
        return status
