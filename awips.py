"""AWIPS product catalog, WMO/PIL headers, warnings and message segments."""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from datetime import datetime, timedelta

from . import same, tz, zones

# ---------------------------------------------------------------------------
# catalog
# ---------------------------------------------------------------------------

PRIORITY_EMERGENCY = 100
PRIORITY_WARNING = 70
PRIORITY_WATCH = 50
PRIORITY_ADVISORY = 30
PRIORITY_STATEMENT = 20
PRIORITY_ROUTINE = 10


@dataclass(frozen=True)
class Product:
    pil: str
    name: str
    wmo: str
    category: str
    designator: str
    eas_code: str
    priority: int
    duration: int
    kind: str
    ugc: tuple[str, ...] = ()
    cccc: str = "KLOT"
    bulletin: str = ""
    voice_id: str = ""

    @property
    def awips_id(self) -> str:
        if self.pil.endswith(self.designator):
            return self.pil
        return f"{self.pil}{self.designator}"

    @property
    def tier(self) -> str:
        p = self.priority
        if p >= 95:
            return "Emergency"
        if p >= 65:
            return "Warning"
        if p >= 45:
            return "Watch"
        if p >= 25:
            return "Advisory"
        if p >= 15:
            return "Statement"
        return "Routine"


CATALOG: dict[str, Product] = {
    # -- convective / hydrologic warnings --------------------------------
    "TOR": Product("TOR", "Tornado Warning", "WFUS53", "EAS", "LOT", "TOR",
                   PRIORITY_EMERGENCY, 45, "warning",
                   ("INZ001", "INZ002"), bulletin="BULLETIN - EAS ACTIVATION REQUESTED"),
    "SVR": Product("SVR", "Severe Thunderstorm Warning", "WWUS53", "EAS", "LOT", "SVR",
                   PRIORITY_WARNING, 45, "warning",
                   ("INZ001", "INZ002", "ILZ012"), bulletin="BULLETIN - EAS ACTIVATION REQUESTED"),
    "FFW": Product("FFW", "Flash Flood Warning", "WGUS53", "EAS", "LOT", "FFW",
                   PRIORITY_WARNING, 60, "warning",
                   ("INZ001", "INZ002", "ILZ012"), bulletin="BULLETIN - EAS ACTIVATION REQUESTED"),
    "EWW": Product("EWW", "Extreme Wind Warning", "WWUS73", "EAS", "LOT", "EWW",
                   PRIORITY_WARNING, 30, "warning",
                   ("INZ001", "INZ002"), bulletin="BULLETIN - EAS ACTIVATION REQUESTED"),
    "SVS": Product("SVS", "Severe Weather Statement", "WWUS53", "Weather", "LOT", "SVS",
                   PRIORITY_WARNING, 30, "statement", ("INZ001", "INZ002")),
    "SPS": Product("SPS", "Special Weather Statement", "WWUS83", "Weather", "LOT", "SPS",
                   PRIORITY_STATEMENT, 60, "statement", ("INZ001", "INZ002")),
    # -- watches (issued by SPC for the local area) ----------------------
    "TOA": Product("TOA", "Tornado Watch", "WWUS20", "Weather", "KWNS", "TOA",
                   PRIORITY_WATCH, 240, "watch", ("INZ001", "INZ002", "ILZ012"), cccc="KWNS"),
    "SVA": Product("SVA", "Severe Thunderstorm Watch", "WWUS20", "Weather", "KWNS", "SVA",
                   PRIORITY_WATCH, 240, "watch", ("INZ001", "INZ002", "ILZ012"), cccc="KWNS"),
    # -- EAS tests -------------------------------------------------------
    "RWT": Product("RWT", "Required Weekly Test", "WOUS21", "EAS", "LOT", "RWT",
                   PRIORITY_STATEMENT, 15, "test", ("INZ001", "INZ002")),
    "RMT": Product("RMT", "Required Monthly Test", "WOUS21", "EAS", "LOT", "RMT",
                   PRIORITY_STATEMENT, 15, "test", ("INZ001", "INZ002")),
    # -- routine products ------------------------------------------------
    "ZFPLOT": Product("ZFPLOT", "Zone Forecast Product", "FPUS53", "Weather", "LOT", "ZFP",
                      PRIORITY_ROUTINE, 360, "forecast", tuple(z.ugc for z in zones.LAND_ZONES)),
    "AFDLOT": Product("AFDLOT", "Area Forecast Discussion", "FXUS63", "Weather", "LOT", "AFD",
                      PRIORITY_ROUTINE, 360, "forecast", ()),
    "HWOLOT": Product("HWOLOT", "Hazardous Weather Outlook", "FLUS43", "Weather", "LOT", "HWO",
                      PRIORITY_ROUTINE, 720, "forecast", tuple(z.ugc for z in zones.LAND_ZONES)),
    "RWRLOT": Product("RWRLOT", "Regional Weather Roundup", "ASUS63", "Weather", "LOT", "RWR",
                      PRIORITY_ROUTINE, 120, "observation", ()),
    "CLILOT": Product("CLILOT", "Climate Report", "CLIUS53", "Weather", "LOT", "CLI",
                      PRIORITY_ROUTINE, 720, "climate", ()),
    "MFMLOT": Product("MFMLOT", "Marine Weather Forecast", "FZUS53", "Weather", "LOT", "MFM",
                      PRIORITY_ROUTINE, 360, "marine", tuple(z.ugc for z in zones.MARINE_ZONES)),
}

PRODUCT_ORDER = [
    "TOR", "SVR", "FFW", "EWW", "SVS", "SPS", "TOA", "SVA",
    "RWT", "RMT", "ZFPLOT", "AFDLOT", "HWOLOT", "RWRLOT", "CLILOT", "MFMLOT",
]

EAS_EVENTS = {
    "TOR": "Tornado Warning",
    "SVR": "Severe Thunderstorm Warning",
    "FFW": "Flash Flood Warning",
    "EWW": "Extreme Wind Warning",
    "SPS": "Special Weather Statement",
    "SVS": "Severe Weather Statement",
    "TOA": "Tornado Watch",
    "SVA": "Severe Thunderstorm Watch",
    "RWT": "Required Weekly Test",
    "RMT": "Required Monthly Test",
}

BBB_OPTIONS = ["NOR", "A", "B", "C", "COR"]


def product(pid: str) -> Product:
    key = pid.strip().upper()
    if key in CATALOG:
        return CATALOG[key]
    for k, p in CATALOG.items():
        if p.awips_id == key:
            return p
    for k, p in CATALOG.items():
        if k.startswith(key) or p.pil == key:
            return p
    raise KeyError(f"unknown product {pid!r}")


def awips_header(
    prod: Product,
    when_utc: datetime | None = None,
    bbb: str = "NOR",
    cccc: str | None = None,
    wsfo: str = "",
) -> str:
    """``WMO CCCC DDhhmm [BBB]`` plus the AWIPS ID line."""
    when_utc = when_utc or tz.utc_now()
    line = f"{prod.wmo} {cccc or prod.cccc} {tz.awips_timestamp(when_utc)}"
    if bbb and bbb.upper() not in ("NOR", "NONE", "-"):
        line += f" {bbb.upper()}"
    pil = prod.awips_id
    if wsfo:
        pil = f"{pil}"  # WSFO is informational only
    return f"{line}\n{pil}"


def compose(
    prod: Product,
    body: str,
    ugc: list[str] | None = None,
    when_utc: datetime | None = None,
    bbb: str = "NOR",
    headline: str = "",
    wsfo: str = "",
) -> str:
    when_utc = when_utc or tz.utc_now()
    local, label = tz.central_from_utc(when_utc)
    ugc_line = zones.ugc_block(ugc or list(prod.ugc), tz.awips_timestamp(when_utc))
    head = f"{prod.name}\nNational Weather Service Chicago/Romeoville IL\n{local:%I:%M %p} {label} {local:%a %b} {local.day} {local.year}"
    parts = [awips_header(prod, when_utc, bbb, wsfo=wsfo)]
    if ugc_line:
        parts.append(ugc_line)
    parts.append(headline or head)
    parts.append(body.strip())
    parts.append("$$")
    return "\n\n".join(parts)


# ---------------------------------------------------------------------------
# storm polygons
# ---------------------------------------------------------------------------

@dataclass
class StormCell:
    lat: float
    lon: float
    motion_deg: int = 45
    speed_kt: int = 35
    hail_in: float = 1.0
    wind_mph: int = 60
    rotation: bool = False
    name: str = ""

    def destination(self, minutes: int) -> tuple[float, float]:
        radians = math.radians(self.motion_deg)
        nm = self.speed_kt * minutes / 60.0
        dlat = nm * math.cos(radians) / 60.0
        dlon = nm * math.sin(radians) / (60.0 * math.cos(math.radians(self.lat)))
        return round(self.lat + dlat, 4), round(self.lon + dlon, 4)


def latlon_block(points: list[tuple[float, float]]) -> str:
    """NWS ``LAT...LON`` block using hundredths of a degree."""
    tokens = []
    for lat, lon in points:
        tokens.append(f"{int(round(abs(lat) * 100)):04d}")
        tokens.append(f"{int(round(abs(lon) * 100)):04d}")
    pairs = " ".join(
        f"{tokens[i]} {tokens[i + 1]}" for i in range(0, len(tokens) - 1, 2)
    )
    return f"LAT...LON {pairs}"


def time_motion_block(cell: StormCell, when_utc: datetime | None = None) -> str:
    when_utc = when_utc or tz.utc_now()
    return (
        f"TIME...MOT...LOC {when_utc:%H%M}Z "
        f"{cell.motion_deg:03d}DEG {cell.speed_kt}KT "
        f"{int(round(cell.lat * 100)):04d} {int(round(abs(cell.lon) * 100)):04d}"
    )


def parse_latlon_text(text: str) -> list[tuple[float, float]]:
    """Parse ``4134 8734 4149 8733`` (or decimal lat/lon pairs) into points."""
    numbers = [t for t in text.replace(",", " ").split() if t.replace(".", "").isdigit()]
    if len(numbers) < 4:
        return []
    if any("." in n for n in numbers):
        values = [float(n) for n in numbers]
    else:
        values = [float(n) / 100.0 for n in numbers]
    points = []
    for i in range(0, len(values) - 1, 2):
        lat = values[i]
        lon = -abs(values[i + 1])
        points.append((round(lat, 4), round(lon, 4)))
    return points


def format_latlon_text(points: list[tuple[float, float]]) -> str:
    return "  ".join(
        f"{int(round(lat * 100)):04d} {int(round(abs(lon) * 100)):04d}" for lat, lon in points
    )


def polygon_centroid(points: list[tuple[float, float]]) -> tuple[float, float]:
    if not points:
        return 0.0, 0.0
    return (
        round(sum(p[0] for p in points) / len(points), 4),
        round(sum(p[1] for p in points) / len(points), 4),
    )


def cities_near(lat: float, lon: float, count: int = 6) -> list[str]:
    ranked = sorted(
        zones.CITY_COORDS.items(),
        key=lambda kv: (kv[1][0] - lat) ** 2 + (kv[1][1] - lon) ** 2,
    )
    return [name for name, _ in ranked[:count]]


def city_list_phrase(names: list[str]) -> str:
    if not names:
        return "Valparaiso, Portage, and Chesterton"
    if len(names) == 1:
        return names[0]
    if len(names) == 2:
        return f"{names[0]} and {names[1]}"
    return ", ".join(names[:-1]) + f", and {names[-1]}"


def awips_city_list(points: list[tuple[float, float]], cell: "StormCell | None" = None) -> str:
    """Locations impacted - nearest cities inside the polygon's neighbourhood."""
    lat, lon = polygon_centroid(points) if points else (
        (cell.lat, cell.lon) if cell else (41.47, -87.06)
    )
    names = cities_near(lat, lon, 7)
    if cell and cell.name and cell.name not in names:
        names.insert(0, cell.name)
    return city_list_phrase(names[:7])


# ---------------------------------------------------------------------------
# warning / watch composition
# ---------------------------------------------------------------------------

WARNING_DETAILS = {
    "TOR": {
        "hazard": "Tornado.",
        "source": "Radar indicated rotation.",
        "impact": (
            "Flying debris will be dangerous to those caught without shelter. "
            "Mobile homes will be damaged or destroyed. Damage to roofs, windows, "
            "and vehicles will occur. Tree damage is likely."
        ),
        "actions": (
            "TAKE COVER NOW! Move to a basement or an interior room on the lowest "
            "floor of a sturdy building. Avoid windows. If you are outdoors, in a "
            "mobile home, or in a vehicle, move to the closest substantial shelter "
            "and protect yourself from flying debris."
        ),
    },
    "SVR": {
        "hazard": "60 mile per hour wind gusts and quarter size hail.",
        "source": "Radar indicated.",
        "impact": (
            "Hail damage to vehicles is expected. Expect wind damage to roofs, "
            "siding, and trees."
        ),
        "actions": (
            "For your protection move to an interior room on the lowest floor of a "
            "building. Prepare for possible power outages."
        ),
    },
    "FFW": {
        "hazard": "Flash flooding caused by heavy rain.",
        "source": "Doppler radar.",
        "impact": (
            "Flooding of small creeks and streams, urban areas, highways, streets, "
            "and underpasses is expected, along with flooding of farmland and other "
            "low lying areas."
        ),
        "actions": (
            "Turn around, do not drown when encountering flooded roads. Most flood "
            "deaths occur in vehicles. Move to higher ground now."
        ),
    },
    "EWW": {
        "hazard": "Extreme sustained winds of 100 miles per hour or greater.",
        "source": "Radar and surface observations.",
        "impact": (
            "Extensive damage to buildings is likely, along with numerous downed "
            "trees and power lines. Travel will be extremely dangerous."
        ),
        "actions": (
            "Treat this warning as a life threatening situation. Take shelter in an "
            "interior room away from windows. Do not go outside until officials say "
            "it is safe."
        ),
    },
}


def warning_product(
    prod: Product,
    ugc: list[str],
    cell: StormCell,
    points: list[tuple[float, float]],
    when_utc: datetime | None = None,
    bbb: str = "NOR",
    lead_minutes: int = 30,
    custom_headline: str = "",
    line_of_storms: bool = False,
    extra_actions: str = "",
) -> str:
    when_utc = when_utc or tz.utc_now()
    local, label = tz.central_from_utc(when_utc)
    until_local, until_label = tz.central_from_utc(when_utc + timedelta(minutes=lead_minutes))
    area = zones.describe_area(ugc)
    detail = WARNING_DETAILS.get(prod.pil, WARNING_DETAILS["SVR"])
    motion = (
        f"A line of severe thunderstorms was located near {cell.name or 'the area'}, "
        f"moving northeast at {cell.speed_kt} miles per hour."
        if line_of_storms
        else f"A severe thunderstorm was located near {cell.name or 'the area'}, "
        f"moving northeast at {cell.speed_kt} miles per hour."
    )
    if prod.pil == "TOR":
        motion = (
            f"At {local:%I:%M %p} {label}, a severe thunderstorm capable of producing a "
            f"tornado was located near {cell.name or 'the area'}, moving northeast at "
            f"{cell.speed_kt} miles per hour."
        )
    elif prod.pil == "FFW":
        motion = (
            f"At {local:%I:%M %p} {label}, Doppler radar indicated thunderstorms "
            f"producing heavy rain across the warned area. Between 1 and 2 inches of "
            f"rain have fallen."
        )
    locations = awips_city_list(points, cell)
    actions = detail["actions"]
    if extra_actions:
        actions = f"{actions}\n\n{extra_actions}"
    body = f"""The National Weather Service in Chicago has issued a

* {prod.name} for...
  {area}...

* Until {until_local:%I:%M %p} {until_label}.

* {motion}

HAZARD...{detail['hazard']}

SOURCE...{detail['source']}

IMPACT...{detail['impact']}

* Locations impacted include...
  {locations}.

PRECAUTIONARY/PREPAREDNESS ACTIONS...

{actions}

&&
{latlon_block(points)}
{time_motion_block(cell, when_utc)}"""
    return compose(prod, body, ugc, when_utc, bbb, headline=custom_headline or "")


def watch_product(
    prod: Product,
    ugc: list[str],
    when_utc: datetime | None = None,
    bbb: str = "NOR",
    hours: int = 4,
    discussion: str = "",
) -> str:
    when_utc = when_utc or tz.utc_now()
    until = when_utc + timedelta(hours=hours)
    local, label = tz.central_from_utc(when_utc)
    until_local, _ = tz.central_from_utc(until)
    area = zones.describe_area(ugc)
    body = f"""The Storm Prediction Center has issued a {prod.name} for

  {area}...

* Effective this {local:%A} afternoon and evening from {local:%I:%M %p} until
  {until_local:%I:%M %p} local time.

* Primary threats include...
  Scattered damaging wind gusts to 70 miles per hour likely.
  Isolated large hail events to 1.5 inches in diameter possible.
  A tornado or two possible.

{discussion or 'A line of thunderstorms will move across the region this evening.'}

The watch area is approximately along and 60 statute miles east and west of a
line from 30 miles north of Valparaiso to 20 miles south of Kankakee.

PRECAUTIONARY/PREPAREDNESS ACTIONS...

Remain alert for approaching storms, and be ready to act should a warning be
issued. Review severe weather safety rules now."""
    return compose(prod, body, ugc, when_utc, bbb)


# ---------------------------------------------------------------------------
# workstation segments
# ---------------------------------------------------------------------------

@dataclass
class Segment:
    kind: str
    title: str
    text: str = ""

    def clone(self) -> "Segment":
        return Segment(self.kind, self.title, self.text)


@dataclass
class Message:
    product_id: str = "SPS"
    ugc: list[str] = field(default_factory=lambda: ["INZ001", "INZ002"])
    bbb: str = "NOR"
    segments: list[Segment] = field(default_factory=list)
    created_utc: datetime = field(default_factory=tz.utc_now)
    author: str = "LOT"
    issued: bool = False
    message_id: str = ""

    def add(self, segment: Segment) -> Segment:
        self.segments.append(segment)
        return segment

    def remove(self, index: int) -> None:
        if 0 <= index < len(self.segments):
            del self.segments[index]

    def move(self, index: int, delta: int) -> int:
        new = max(0, min(len(self.segments) - 1, index + delta))
        if new != index:
            self.segments.insert(new, self.segments.pop(index))
        return new

    def combine(self, index: int) -> None:
        """Merge segment ``index`` into the one above it."""
        if 0 < index < len(self.segments):
            upper = self.segments[index - 1]
            lower = self.segments[index]
            joiner = "\n\n" if upper.text and lower.text else ""
            upper.text = f"{upper.text}{joiner}{lower.text}".strip()
            upper.title = f"{upper.title} / {lower.title}"
            del self.segments[index]

    def duplicate(self, index: int) -> None:
        if 0 <= index < len(self.segments):
            self.segments.insert(index + 1, self.segments[index].clone())

    def text(self) -> str:
        return "\n\n".join(s.text.strip() for s in self.segments if s.text.strip())

    def render(self) -> str:
        prod = product(self.product_id)
        body = self.text()
        return compose(prod, body, self.ugc, self.created_utc, self.bbb)

    def reset(self, product_id: str) -> None:
        self.product_id = product_id
        self.segments.clear()


def header_segment(
    product_id: str,
    when_utc: datetime | None = None,
    bbb: str = "NOR",
    wsfo: str = "CHI",
) -> Segment:
    prod = product(product_id)
    when_utc = when_utc or tz.utc_now()
    local, label = tz.central_from_utc(when_utc)
    return Segment(
        "header",
        "AWIPS Header Block",
        "\n".join(
            [
                awips_header(prod, when_utc, bbb),
                f"WSFO ID... {wsfo or 'CHI'}",
                f"ISSUED... {local:%I:%M %p} {label} {local:%a %b} {local.day} {local.year}",
                f"UGC... {zones.ugc_block(list(prod.ugc), tz.awips_timestamp(when_utc))}",
            ]
        ),
    )
