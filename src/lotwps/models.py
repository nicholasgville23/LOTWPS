"""Shared data models and alert-priority rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import IntEnum
from typing import Any
from zoneinfo import ZoneInfo


class AlertPriority(IntEnum):
    EMERGENCY = 0
    WARNING = 1
    WATCH = 2
    ADVISORY = 3
    STATEMENT = 4
    OTHER = 5


def alert_priority(event: str, headline: str = "") -> AlertPriority:
    """Return the requested editorial order; this is not an NWS severity field."""
    text = f"{event} {headline}".casefold()
    if "tornado emergency" in text or "emergency" in text:
        return AlertPriority.EMERGENCY
    if "warning" in text:
        return AlertPriority.WARNING
    if "watch" in text:
        return AlertPriority.WATCH
    if "advisory" in text:
        return AlertPriority.ADVISORY
    if "statement" in text:
        return AlertPriority.STATEMENT
    return AlertPriority.OTHER


@dataclass(frozen=True, slots=True)
class Station:
    station_id: str
    location: str
    latitude: float
    longitude: float
    timezone: str = "America/Chicago"
    frequency_mhz: float | None = None
    coverage: tuple[str, ...] = ()
    marine_enabled: bool = False
    extra_observation_stations: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Station":
        return cls(
            station_id=str(data["station_id"]).upper(),
            location=str(data["location"]),
            latitude=float(data["latitude"]),
            longitude=float(data["longitude"]),
            timezone=str(data.get("timezone", "America/Chicago")),
            frequency_mhz=float(data["frequency_mhz"]) if data.get("frequency_mhz") is not None else None,
            coverage=tuple(str(item) for item in data.get("coverage", [])),
            marine_enabled=bool(data.get("marine_enabled", False)),
            extra_observation_stations=tuple(str(item).upper() for item in data.get("extra_observation_stations", [])),
        )

    def local_time(self, instant: datetime | None = None) -> datetime:
        zone = ZoneInfo(self.timezone)
        if instant is None:
            return datetime.now(zone)
        if instant.tzinfo is None:
            raise ValueError("instant must be timezone-aware")
        return instant.astimezone(zone)


@dataclass(frozen=True, slots=True)
class WeatherAlert:
    identifier: str
    event: str
    headline: str
    area: str
    severity: str
    effective: str
    expires: str
    description: str
    instruction: str

    @property
    def priority(self) -> AlertPriority:
        return alert_priority(self.event, self.headline)

    @classmethod
    def from_feature(cls, feature: dict[str, Any]) -> "WeatherAlert":
        properties = feature.get("properties") or {}
        return cls(
            identifier=str(feature.get("id") or properties.get("id") or ""),
            event=str(properties.get("event") or "Unknown alert"),
            headline=str(properties.get("headline") or ""),
            area=str(properties.get("areaDesc") or ""),
            severity=str(properties.get("severity") or "Unknown"),
            effective=str(properties.get("effective") or properties.get("onset") or ""),
            expires=str(properties.get("expires") or ""),
            description=str(properties.get("description") or ""),
            instruction=str(properties.get("instruction") or ""),
        )


def sort_alerts(alerts: list[WeatherAlert]) -> list[WeatherAlert]:
    return sorted(alerts, key=lambda item: (item.priority, item.expires or "", item.event))
