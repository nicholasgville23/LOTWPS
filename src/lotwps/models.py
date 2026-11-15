"""Core data models shared by LOTWPS, LOTIEM and BMH."""
from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import IntEnum
from zoneinfo import ZoneInfo

class AlertPriority(IntEnum):
    EMERGENCY = 0
    WARNING = 1
    WATCH = 2
    ADVISORY = 3
    STATEMENT = 4

@dataclass(slots=True)
class Station:
    station_id: str
    display_name: str
    timezone: str
    frequency_mhz: float | None = None
    coverage: list[str] = field(default_factory=list)
    enabled: bool = True

    def local_time(self, instant: datetime | None = None) -> datetime:
        now = instant or datetime.now().astimezone()
        if now.tzinfo is None:
            raise ValueError("instant must be timezone-aware")
        return now.astimezone(ZoneInfo(self.timezone))

@dataclass(slots=True)
class WeatherProduct:
    product_id: str
    title: str
    text: str
    priority: AlertPriority = AlertPriority.STATEMENT
    issued_at: datetime = field(default_factory=lambda: datetime.now().astimezone())
    expires_at: datetime | None = None
    station_ids: tuple[str, ...] = ()
    test_only: bool = True

    def __post_init__(self) -> None:
        if not self.product_id.strip() or not self.title.strip() or not self.text.strip():
            raise ValueError("product_id, title and text are required")
        if not self.test_only:
            raise ValueError("public transmission is not enabled in this foundation")
