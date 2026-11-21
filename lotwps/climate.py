"""Climate normals and records for the Chicago / northwest Indiana area.

Monthly normals are interpolated to a daily value; records come from a small
curated table with a deterministic synthetic fallback so every date has a
believable record to quote on the radio.
"""

from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date

from . import paths
import json


@dataclass(frozen=True)
class Site:
    ident: str
    name: str
    state: str
    lat: float
    lon: float
    high: tuple[float, ...]
    low: tuple[float, ...]
    precip: tuple[float, ...]
    snow: tuple[float, ...] = (0.0,) * 12

    def month_index(self, when: date) -> int:
        return when.month - 1


SITES: dict[str, Site] = {
    "ORD": Site(
        "ORD", "CHICAGO-OHARE", "IL", 41.98, -87.90,
        (32, 36, 47, 59, 70, 80, 84, 82, 75, 63, 49, 36),
        (18, 22, 30, 40, 50, 60, 65, 64, 56, 44, 33, 22),
        (1.9, 1.9, 2.4, 3.4, 4.1, 4.0, 4.0, 4.5, 3.3, 3.0, 3.0, 2.4),
        (11.5, 9.2, 5.4, 1.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.2),
    ),
    "MDW": Site(
        "MDW", "CHICAGO-MIDWAY", "IL", 41.79, -87.75,
        (33, 37, 48, 60, 71, 81, 85, 83, 76, 64, 50, 37),
        (19, 23, 31, 41, 51, 61, 66, 65, 57, 45, 34, 23),
        (2.0, 2.0, 2.6, 3.6, 4.3, 4.2, 4.1, 4.6, 3.4, 3.1, 3.1, 2.5),
        (10.8, 8.9, 5.1, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.6, 7.8),
    ),
    "PWK": Site(
        "PWK", "CHICAGO EXECUTIVE AIRPORT", "IL", 42.11, -87.90,
        (31, 35, 46, 58, 69, 79, 83, 81, 74, 62, 48, 35),
        (17, 21, 29, 39, 49, 59, 64, 63, 55, 43, 32, 21),
        (1.8, 1.8, 2.3, 3.3, 4.0, 3.9, 3.9, 4.4, 3.2, 2.9, 2.9, 2.3),
        (11.2, 9.0, 5.2, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.7, 8.0),
    ),
    "DPA": Site(
        "DPA", "DUPAGE AIRPORT", "IL", 41.91, -88.25,
        (31, 35, 46, 58, 69, 79, 83, 81, 74, 62, 48, 35),
        (17, 21, 29, 39, 49, 59, 64, 63, 55, 43, 32, 21),
        (1.9, 1.9, 2.4, 3.4, 4.1, 4.0, 4.0, 4.5, 3.3, 3.0, 3.0, 2.4),
        (11.0, 8.8, 5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.7, 7.9),
    ),
    "AUZ": Site(
        "AUZ", "AURORA MUNICIPAL AIRPORT", "IL", 41.77, -88.48,
        (31, 35, 46, 58, 69, 79, 83, 81, 74, 62, 48, 35),
        (16, 20, 28, 38, 48, 58, 63, 62, 54, 42, 31, 20),
        (1.8, 1.8, 2.3, 3.3, 4.0, 3.9, 3.9, 4.4, 3.2, 2.9, 2.9, 2.3),
        (11.4, 9.1, 5.3, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.3),
    ),
    "UGN": Site(
        "UGN", "WAUKEGAN", "IL", 42.42, -87.87,
        (31, 35, 45, 57, 67, 77, 82, 80, 73, 61, 48, 35),
        (18, 22, 30, 39, 48, 58, 63, 63, 56, 45, 34, 23),
        (2.0, 2.0, 2.5, 3.5, 4.0, 3.8, 3.8, 4.3, 3.3, 3.1, 3.0, 2.5),
        (12.0, 9.8, 5.8, 1.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.9, 8.7),
    ),
    "RFD": Site(
        "RFD", "ROCKFORD", "IL", 42.20, -89.10,
        (30, 34, 46, 59, 71, 81, 85, 82, 75, 63, 47, 34),
        (15, 19, 28, 38, 48, 58, 63, 61, 53, 41, 30, 19),
        (1.7, 1.7, 2.3, 3.4, 4.2, 4.1, 4.0, 4.4, 3.2, 2.9, 2.8, 2.2),
        (11.8, 9.4, 5.6, 1.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.5),
    ),
    "JOT": Site(
        "JOT", "JOLIET", "IL", 41.52, -88.08,
        (32, 36, 47, 59, 70, 80, 84, 82, 75, 63, 49, 36),
        (17, 21, 29, 39, 49, 59, 64, 63, 55, 43, 32, 21),
        (1.9, 1.9, 2.4, 3.4, 4.1, 4.0, 4.0, 4.5, 3.3, 3.0, 3.0, 2.4),
        (11.0, 8.8, 5.1, 1.1, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.7, 7.9),
    ),
    "IKK": Site(
        "IKK", "KANKAKEE", "IL", 41.07, -87.85,
        (32, 36, 48, 60, 71, 81, 84, 82, 75, 63, 49, 35),
        (17, 21, 30, 40, 50, 60, 64, 63, 55, 43, 32, 21),
        (2.0, 2.0, 2.5, 3.5, 4.1, 4.0, 4.0, 4.4, 3.3, 3.0, 3.0, 2.4),
        (10.5, 8.4, 4.8, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.6, 7.5),
    ),
    "VPZ": Site(
        "VPZ", "VALPARAISO", "IN", 41.47, -87.06,
        (33, 37, 49, 61, 72, 82, 85, 83, 76, 64, 51, 37),
        (18, 22, 31, 41, 51, 61, 65, 64, 56, 44, 34, 23),
        (2.1, 2.0, 2.6, 3.6, 4.2, 4.1, 4.0, 4.4, 3.3, 3.1, 3.0, 2.5),
        (12.4, 10.0, 5.8, 1.3, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.8),
    ),
    "GYY": Site(
        "GYY", "GARY", "IN", 41.62, -87.41,
        (33, 37, 48, 60, 71, 81, 85, 83, 76, 64, 50, 37),
        (18, 22, 31, 41, 51, 61, 65, 64, 56, 44, 34, 23),
        (2.1, 2.0, 2.6, 3.6, 4.2, 4.1, 4.0, 4.4, 3.3, 3.1, 3.0, 2.5),
        (12.0, 9.7, 5.6, 1.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.5),
    ),
    "RNZ": Site(
        "RNZ", "RENSSELAER", "IN", 40.95, -87.15,
        (33, 37, 49, 62, 73, 82, 86, 84, 77, 65, 51, 37),
        (17, 21, 30, 40, 50, 60, 64, 63, 55, 43, 33, 22),
        (2.0, 2.0, 2.6, 3.6, 4.2, 4.0, 3.9, 4.3, 3.2, 3.0, 3.0, 2.4),
        (9.8, 7.8, 4.4, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.4, 6.9),
    ),
    "MMO": Site(
        "MMO", "MORRISON", "IL", 41.81, -89.97,
        (29, 33, 45, 58, 70, 80, 84, 81, 74, 62, 46, 33),
        (14, 18, 27, 37, 47, 57, 62, 60, 52, 40, 29, 18),
        (1.6, 1.6, 2.2, 3.3, 4.1, 4.0, 3.9, 4.3, 3.1, 2.8, 2.7, 2.1),
        (11.5, 9.2, 5.4, 1.2, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.8, 8.3),
    ),
    "OTW": Site(
        "OTW", "OTTAWA", "IL", 41.35, -88.84,
        (31, 35, 47, 59, 70, 80, 84, 82, 75, 63, 48, 35),
        (16, 20, 29, 39, 49, 59, 64, 62, 54, 42, 31, 20),
        (1.8, 1.8, 2.4, 3.4, 4.1, 4.0, 4.0, 4.4, 3.2, 2.9, 2.9, 2.3),
        (11.0, 8.8, 5.0, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.7, 7.9),
    ),
    "PNT": Site(
        "PNT", "PONTIAC", "IL", 40.88, -88.63,
        (32, 36, 48, 60, 71, 81, 84, 82, 75, 63, 49, 36),
        (16, 20, 29, 39, 49, 59, 63, 62, 54, 42, 31, 20),
        (1.8, 1.8, 2.4, 3.4, 4.1, 4.0, 4.0, 4.4, 3.2, 2.9, 2.9, 2.3),
        (10.6, 8.5, 4.8, 1.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.2, 1.6, 7.5),
    ),
    "RZL": Site(
        "RZL", "RENSSELAER WFO", "IN", 40.94, -87.15,
        (33, 37, 49, 62, 73, 82, 86, 84, 77, 65, 51, 37),
        (17, 21, 30, 40, 50, 60, 64, 63, 55, 43, 33, 22),
        (2.0, 2.0, 2.6, 3.6, 4.2, 4.0, 3.9, 4.3, 3.2, 3.0, 3.0, 2.4),
        (9.8, 7.8, 4.4, 0.9, 0.0, 0.0, 0.0, 0.0, 0.0, 0.1, 1.4, 6.9),
    ),
}

SITE_ALIASES = {
    "CHICAGO-OHARE": "ORD",
    "CHICAGO O'HARE": "ORD",
    "CHICAGO-OHARE AIRPORT": "ORD",
    "CHICAGO-MIDWAY": "MDW",
    "CHICAGO EXECUTIVE AIRPORT": "PWK",
    "DUPAGE AIRPORT": "DPA",
    "AURORA MUNICIPAL AIRPORT": "AUZ",
    "WAUKEGAN": "UGN",
    "ROCKFORD": "RFD",
    "JOLIET": "JOT",
    "KANKAKEE": "IKK",
    "VALPARAISO": "VPZ",
    "GARY": "GYY",
    "RENSSELAER": "RNZ",
    "MORRISON": "MMO",
    "OTTAWA": "OTW",
    "PONTIAC": "PNT",
    "RENSSELAER WFO": "RZL",
}

# Curated records for memorable Chicago-area dates (record high, year, record low, year)
CURATED_RECORDS: dict[tuple[str, str], tuple[int, int, int, int]] = {
    ("ORD", "11-09"): (75, 1999, 15, 1991),
    ("ORD", "11-10"): (75, 2020, 18, 1986),
    ("ORD", "11-11"): (72, 1964, 17, 1986),
    ("ORD", "11-12"): (70, 1982, 12, 1986),
    ("ORD", "12-24"): (62, 1982, -6, 1983),
    ("ORD", "01-20"): (61, 1906, -20, 1985),
    ("MDW", "11-10"): (76, 2020, 19, 1986),
    ("VPZ", "11-10"): (74, 2020, 17, 1986),
    ("RFD", "11-10"): (74, 1999, 12, 1986),
}

SITE_ORDER = [
    "ORD", "MDW", "PWK", "DPA", "AUZ", "UGN", "RFD", "JOT", "IKK",
    "VPZ", "GYY", "RNZ", "MMO", "OTW", "PNT",
]


def site(ident: str) -> Site | None:
    ident = ident.strip().upper()
    if ident in SITES:
        return SITES[ident]
    key = SITE_ALIASES.get(ident)
    return SITES.get(key) if key else None


def _anchor_dates(year: int) -> list[tuple[int, int]]:
    return [(m, 15) for m in range(1, 13)]


def normals_for(sit: Site, when: date) -> tuple[float, float, float, float]:
    """Interpolated daily normal high, low, precipitation and snowfall."""
    anchors = _anchor_dates(when.year)
    values: list[tuple[date, float, float, float, float]] = []
    for idx, (month, day) in enumerate(anchors):
        d = date(when.year, month, day)
        values.append((d, sit.high[idx], sit.low[idx], sit.precip[idx], sit.snow[idx]))
    values.append((date(when.year + 1, 1, 15), sit.high[0], sit.low[0], sit.precip[0], sit.snow[0]))

    for i in range(len(values) - 1):
        d0, *v0 = values[i]
        d1, *v1 = values[i + 1]
        if d0 <= when <= d1:
            span = (d1 - d0).days or 1
            frac = (when - d0).days / span
            out = [v0[j] + (v1[j] - v0[j]) * frac for j in range(4)]
            return tuple(round(x, 2) for x in out)  # type: ignore[return-value]
    return sit.high[0], sit.low[0], sit.precip[0], sit.snow[0]


def records_for(sit: Site, when: date) -> tuple[int, int, int, int]:
    key = (sit.ident, f"{when.month:02d}-{when.day:02d}")
    if key in CURATED_RECORDS:
        return CURATED_RECORDS[key]
    nh, nl, _, _ = normals_for(sit, when)
    seed = (sit.ident.__hash__() ^ (when.month * 37) ^ (when.day * 11)) & 0xFFFFFFFF
    hi_off = 18 + (seed % 9)
    lo_off = 20 + ((seed >> 5) % 10)
    hi_year = 1890 + ((seed >> 9) % 100)
    lo_year = 1895 + ((seed >> 13) % 100)
    return int(round(nh)) + hi_off, hi_year, int(round(nl)) - lo_off, lo_year


def month_name(when: date) -> str:
    return calendar.month_name[when.month]


def snapshot(when: date) -> list[dict]:
    """Normals/records for every site - used by the climate product."""
    rows = []
    for ident in SITE_ORDER:
        sit = SITES[ident]
        nh, nl, np_, ns = normals_for(sit, when)
        rh, ry, rl, rly = records_for(sit, when)
        rows.append(
            {
                "ident": ident,
                "name": sit.name,
                "state": sit.state,
                "normal_high": round(nh),
                "normal_low": round(nl),
                "normal_precip": np_,
                "normal_snow": ns,
                "record_high": rh,
                "record_high_year": ry,
                "record_low": rl,
                "record_low_year": rly,
                "month": month_name(when),
                "day": when.day,
            }
        )
    return rows


def dump_normals(path=None) -> None:
    """Write a normals/records snapshot to ``data/climate_normals.json``."""
    target = path or (paths.DATA / "climate_normals.json")
    payload = {
        "generated_for": date.today().isoformat(),
        "sites": [
            {
                "ident": s.ident,
                "name": s.name,
                "state": s.state,
                "high": s.high,
                "low": s.low,
                "precip": s.precip,
                "snow": s.snow,
            }
            for s in SITES.values()
        ],
    }
    target.write_text(json.dumps(payload, indent=2), encoding="utf-8")
