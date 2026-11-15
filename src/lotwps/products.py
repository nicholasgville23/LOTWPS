from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

from .models import Alert, WeatherProduct
from .priority import sort_alerts


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def alerts_from_geojson(payload: dict[str, Any]) -> list[Alert]:
    alerts: list[Alert] = []
    for feature in payload.get("features", []):
        p = feature.get("properties", {})
        alerts.append(Alert(
            identifier=str(feature.get("id") or p.get("id") or f"ALERT-{len(alerts)+1}"),
            event=str(p.get("event", "Unknown Alert")),
            headline=str(p.get("headline") or ""),
            description=str(p.get("description") or ""),
            instruction=str(p.get("instruction") or ""),
            area_desc=str(p.get("areaDesc") or ""),
            sent=_parse_dt(p.get("sent")),
            effective=_parse_dt(p.get("effective")),
            expires=_parse_dt(p.get("expires")),
            ugc_codes=[str(x).upper() for x in p.get("geocode", {}).get("UGC", [])],
            fips_codes=[str(x) for x in p.get("geocode", {}).get("SAME", [])],
            source="NWS API",
            raw=feature,
        ))
    return sort_alerts(alerts)


def forecast_text(payload: dict[str, Any], timezone_name: str, maximum_periods: int = 14) -> str:
    tz = ZoneInfo(timezone_name)
    periods = payload.get("properties", {}).get("periods", [])[:maximum_periods]
    if not periods:
        return "The National Weather Service forecast is not available at this time."
    lines = ["THE NATIONAL WEATHER SERVICE HAS ISSUED THE FOLLOWING FORECAST:"]
    for period in periods:
        start = _parse_dt(period.get("startTime"))
        local_day = start.astimezone(tz).strftime("%A") if start else str(period.get("name", "Forecast period"))
        detail = (period.get("detailedForecast") or period.get("shortForecast") or "").strip()
        lines.append(f"{period.get('name') or local_day}. {detail}".strip())
    return "\n".join(lines)


def alert_summary(alerts: list[Alert]) -> str:
    if not alerts:
        return "There are no active watches, warnings, or advisories in the selected listening area."
    lines = ["THE FOLLOWING ALERTS ARE IN EFFECT FOR THE LISTENING AREA:"]
    for alert in sort_alerts(alerts):
        location = f" for {alert.area_desc}" if alert.area_desc else ""
        expiration = f" until {alert.expires:%I:%M %p %Z}" if alert.expires else ""
        lines.append(f"{alert.event}{location}{expiration}.")
    return "\n".join(lines)


def climate_summary(normals: dict[str, Any], records: dict[str, Any], month_key: str | None = None) -> str:
    if not normals and not records:
        return "Climate normals and record data have not been configured for this station."
    key = month_key or datetime.now().strftime("%m")
    normal, record = normals.get(key, {}), records.get(key, {})
    parts = ["CLIMATE SUMMARY:"]
    if normal:
        parts.append("Normals: " + "; ".join(f"{k} {v}" for k, v in normal.items()) + ".")
    if record:
        parts.append("Records: " + "; ".join(f"{k} {v}" for k, v in record.items()) + ".")
    return "\n".join(parts)


def make_product(product_id: str, category: str, title: str, body: str, station_id: str) -> WeatherProduct:
    return WeatherProduct(product_id, category, title, body, datetime.now().astimezone(), station_id)
