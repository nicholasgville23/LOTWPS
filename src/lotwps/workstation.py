"""Text workstation helpers: draft WMO headers, products and broadcast scripts."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .models import Station, WeatherAlert, sort_alerts


def make_wmo_header(
    header_type: str = "TTAAii",
    cccc: str = "KLOT",
    bbb: str = "NOR",
    instant: datetime | None = None,
) -> str:
    """Create a WMO-style header line for an editable, non-operational draft."""
    header_type = header_type.strip().upper()
    cccc = cccc.strip().upper()
    bbb = bbb.strip().upper()
    if len(header_type) != 6 or not header_type.isalnum():
        raise ValueError("Header type must be a six-character alphanumeric code")
    if len(cccc) != 4 or not cccc.isalnum():
        raise ValueError("CCCC must be a four-character alphanumeric office code")
    if bbb and (len(bbb) != 3 or not bbb.isalnum()):
        raise ValueError("BBB must be blank or a three-character alphanumeric code")
    instant = instant or datetime.now(timezone.utc)
    stamp = instant.astimezone(timezone.utc).strftime("%d%H%M")
    return " ".join(part for part in (header_type, cccc, stamp, bbb) if part)


def make_product_id(category: str, designator: str = "LOT") -> str:
    category = category.strip().upper()
    designator = designator.strip().upper()
    if not category or not category.isalnum():
        raise ValueError("Product category must be alphanumeric")
    if len(designator) != 3 or not designator.isalnum():
        raise ValueError("Product designator must be three alphanumeric characters")
    return f"{category}{designator}"


def build_product_draft(
    body: str,
    category: str = "SPS",
    designator: str = "LOT",
    addressee: str = "ALL",
    header_type: str = "TTAAii",
    cccc: str = "KLOT",
    bbb: str = "NOR",
) -> str:
    header = make_wmo_header(header_type, cccc, bbb)
    product_id = make_product_id(category, designator)
    return (
        "DRAFT ONLY — NOT AN OFFICIAL NWS PRODUCT OR PUBLIC ALERT\n"
        f"{header}\n"
        f"PRODUCT: {product_id}    ADDRESSEE: {addressee.strip().upper()}\n"
        f"ORIGIN: {cccc.strip().upper()}\n\n"
        f"{body.strip()}\n"
    )


def build_broadcast_script(
    station: Station,
    alerts: list[WeatherAlert],
    forecast_periods: list[dict[str, Any]],
    cycle_number: int = 0,
) -> str:
    """Create a spoken local information script from NWS API data."""
    local_now = station.local_time()
    opening_lines = (
        f"This is the local weather information service for {station.location}.",
        f"Weather information for {station.location}, updated at {local_now:%I:%M %p}.",
        f"Here is the latest weather briefing for {station.location}.",
    )
    parts = [opening_lines[cycle_number % len(opening_lines)]]
    parts.append(f"The local time is {local_now:%I:%M %p} Central Daylight or Central Standard Time, as applicable.")
    ordered_alerts = sort_alerts(alerts)
    if ordered_alerts:
        top = ordered_alerts[0]
        area_text = f" for {top.area}" if top.area else ""
        parts.append(f"Active alert: {top.event}{area_text}.")
        if top.headline:
            parts.append(top.headline)
        if len(ordered_alerts) > 1:
            parts.append(f"There are {len(ordered_alerts)} active alerts affecting this listening area.")
    else:
        parts.append("No active National Weather Service alerts were returned for this station's point location.")
    if forecast_periods:
        period = forecast_periods[0]
        name = str(period.get("name") or "The current forecast period")
        detail = str(period.get("detailedForecast") or period.get("shortForecast") or "")
        parts.append(f"{name}. {detail}")
    else:
        parts.append("The forecast service did not return a period for this update.")
    parts.append("Stay aware of changing weather conditions and follow instructions from local emergency officials.")
    return " ".join(part for part in parts if part)
