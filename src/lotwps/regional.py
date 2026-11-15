from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from .models import Alert, Station


def station_local_time(station: Station, instant: datetime | None = None) -> datetime:
    instant = instant or datetime.now().astimezone()
    return instant.astimezone(ZoneInfo(station.timezone))


def alert_matches_station(alert: Alert, station: Station, allow_routine_without_codes: bool = True) -> bool:
    if not alert.ugc_codes:
        return allow_routine_without_codes
    return bool({x.upper() for x in alert.ugc_codes} & {x.upper() for x in station.listening_area_ugc})


def marine_allowed(station: Station, coastal_only: bool = True) -> bool:
    return station.coastal or not coastal_only


def season_for_station(station: Station, instant: datetime | None = None) -> str:
    month = station_local_time(station, instant).month
    return "winter" if month in (12, 1, 2) else "spring" if month in (3, 4, 5) else "summer" if month in (6, 7, 8) else "autumn"
