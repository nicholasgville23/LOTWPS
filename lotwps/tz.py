"""US Central time handling.

The whole build runs on ``America/Chicago`` with the CST/CDT exception handled
explicitly.  ``zoneinfo`` is used when the IANA database is installed; Windows
without ``tzdata`` falls back to a dependency-free US DST calculator so the
clock is always correct.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

try:  # pragma: no cover - depends on the host
    from zoneinfo import ZoneInfo

    _CENTRAL = ZoneInfo("America/Chicago")
except Exception:  # pragma: no cover
    _CENTRAL = None

CENTRAL_LABEL = {"CST": "Central Standard Time", "CDT": "Central Daylight Time"}


def _nth_sunday(year: int, month: int, nth: int) -> datetime:
    d = datetime(year, month, 1)
    # weekday(): Monday == 0, Sunday == 6
    offset = (6 - d.weekday()) % 7
    return d + timedelta(days=offset + 7 * (nth - 1))


def _manual_central(utc: datetime) -> tuple[datetime, str]:
    """US DST rules: 2nd Sunday March 02:00 local -> 1st Sunday Nov 02:00 local."""
    year = utc.year
    dst_start_utc = _nth_sunday(year, 3, 2).replace(hour=8)  # 02:00 CST == 08:00 UTC
    dst_end_utc = _nth_sunday(year, 11, 1).replace(hour=7)  # 02:00 CDT == 07:00 UTC
    in_dst = dst_start_utc <= utc.replace(tzinfo=None) < dst_end_utc
    offset = -5 if in_dst else -6
    local = utc.replace(tzinfo=timezone.utc).astimezone(timezone(timedelta(hours=offset)))
    return local.replace(tzinfo=None), "CDT" if in_dst else "CST"


def central_now() -> tuple[datetime, str]:
    """Return naive Central local time plus the active ``CST``/``CDT`` label."""
    utc = datetime.now(timezone.utc)
    if _CENTRAL is not None:
        local = utc.astimezone(_CENTRAL)
        label = "CDT" if local.dst() else "CST"
        return local.replace(tzinfo=None), label
    return _manual_central(utc)


def central_from_utc(dt: datetime) -> tuple[datetime, str]:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    if _CENTRAL is not None:
        local = dt.astimezone(_CENTRAL)
        return local.replace(tzinfo=None), ("CDT" if local.dst() else "CST")
    return _manual_central(dt)


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def julian_day(dt: datetime) -> int:
    return dt.timetuple().tm_yday


def same_timestamp(dt_utc: datetime) -> str:
    """``JJJHHMM`` for the SAME header."""
    return f"{julian_day(dt_utc):03d}{dt_utc:%H%M}"


def awips_timestamp(dt_utc: datetime) -> str:
    """``DDhhmm`` for the WMO header."""
    return f"{dt_utc:%d%H%M}"


def central_stamp(prefix: str = "") -> str:
    local, label = central_now()
    stamp = f"{local:%I:%M %p}".lstrip("0")
    return f"{prefix}{stamp} {label}".strip()


def spoken_time(local: datetime | None = None, label: str | None = None) -> str:
    """Time phrased for the voice: ``12:41 PM``."""
    if local is None:
        local, label = central_now()
    label = label or "CST"
    hour = local.strftime("%I").lstrip("0") or "12"
    return f"{hour}:{local:%M} {local:%p} {label}"


def spoken_date(local: datetime | None = None) -> str:
    if local is None:
        local, _ = central_now()
    return f"{local:%A}, {local:%B} {local.day}, {local.year}"


def iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def parse_iso(text: str) -> datetime:
    return datetime.fromisoformat(text)
