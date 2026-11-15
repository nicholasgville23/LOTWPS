from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from typing import Any


class AlertPriority(IntEnum):
    STATEMENT = 10
    ADVISORY = 20
    WATCH = 30
    WARNING = 40
    EMERGENCY = 50


EVENT_PRIORITY = {
    "Tornado Emergency": AlertPriority.EMERGENCY,
    "Flash Flood Emergency": AlertPriority.EMERGENCY,
    "Civil Emergency Message": AlertPriority.EMERGENCY,
    "Evacuation Immediate": AlertPriority.EMERGENCY,
    "Tornado Warning": AlertPriority.WARNING,
    "Severe Thunderstorm Warning": AlertPriority.WARNING,
    "Flash Flood Warning": AlertPriority.WARNING,
    "Extreme Wind Warning": AlertPriority.WARNING,
    "Winter Storm Warning": AlertPriority.WARNING,
    "Blizzard Warning": AlertPriority.WARNING,
    "Tornado Watch": AlertPriority.WATCH,
    "Severe Thunderstorm Watch": AlertPriority.WATCH,
    "Flood Watch": AlertPriority.WATCH,
    "Winter Storm Watch": AlertPriority.WATCH,
    "Heat Advisory": AlertPriority.ADVISORY,
    "Wind Advisory": AlertPriority.ADVISORY,
    "Dense Fog Advisory": AlertPriority.ADVISORY,
    "Special Weather Statement": AlertPriority.STATEMENT,
    "Hazardous Weather Outlook": AlertPriority.STATEMENT,
}


@dataclass(slots=True)
class Alert:
    identifier: str
    event: str
    headline: str = ""
    description: str = ""
    instruction: str = ""
    area_desc: str = ""
    sent: datetime | None = None
    effective: datetime | None = None
    expires: datetime | None = None
    ugc_codes: list[str] = field(default_factory=list)
    fips_codes: list[str] = field(default_factory=list)
    source: str = "NWS API"
    raw: dict[str, Any] = field(default_factory=dict, repr=False)

    @property
    def priority(self) -> AlertPriority:
        if "Tornado Emergency" in self.event or "Flash Flood Emergency" in self.event:
            return AlertPriority.EMERGENCY
        if self.event in EVENT_PRIORITY:
            return EVENT_PRIORITY[self.event]
        severity = str(self.raw.get("properties", {}).get("severity", "")).lower()
        if severity in {"extreme", "severe"}:
            return AlertPriority.WARNING
        if severity == "moderate":
            return AlertPriority.ADVISORY
        return AlertPriority.STATEMENT


@dataclass(slots=True)
class WeatherProduct:
    product_id: str
    category: str
    title: str
    text: str
    created_at: datetime
    station_id: str
    source: str = "LOTWPS"
    alert_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(slots=True)
class Station:
    station_id: str
    name: str
    location: str
    timezone: str
    latitude: float | None = None
    longitude: float | None = None
    frequency_mhz: float | None = None
    host: str = "127.0.0.1"
    port: int = 6000
    listening_area_ugc: list[str] = field(default_factory=list)
    same_fips: list[str] = field(default_factory=list)
    coastal: bool = False
    simulated: bool = True

    @classmethod
    def from_dict(cls, value: dict[str, Any]) -> "Station":
        return cls(
            station_id=str(value["station_id"]),
            name=str(value.get("name", value["station_id"])),
            location=str(value.get("location", "")),
            timezone=str(value.get("timezone", "America/Chicago")),
            latitude=float(value["latitude"]) if value.get("latitude") is not None else None,
            longitude=float(value["longitude"]) if value.get("longitude") is not None else None,
            frequency_mhz=float(value["frequency_mhz"]) if value.get("frequency_mhz") is not None else None,
            host=str(value.get("host", "127.0.0.1")),
            port=int(value.get("port", 6000)),
            listening_area_ugc=list(value.get("listening_area_ugc", [])),
            same_fips=list(value.get("same_fips", [])),
            coastal=bool(value.get("coastal", False)),
            simulated=bool(value.get("simulated", True)),
        )
