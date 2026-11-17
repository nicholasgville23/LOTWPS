"""Weather content generation for LOTWPS.

Every product the radio reads and every product the text workstation issues is
built here from one deterministic daily model:

* a seasonal pattern (quiet, showery, foggy, arctic, severe ...)
* daily high/low anomalies that move smoothly from day to day
* sky / POP / wind / hazard derived consistently from that pattern
* NWS phrasing pools with a "no immediate repeat" selector
"""

from __future__ import annotations

import math
import random
import textwrap
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta

from . import climate, tz, zones
from .climate import SITES

# ---------------------------------------------------------------------------
# phrasing helpers
# ---------------------------------------------------------------------------


def temp_phrase(value: float, kind: str = "high") -> str:
    """NWS noun phrase: ``the lower 50s``, ``the mid 60s``, ``50``."""
    t = int(round(value))
    if t < 0:
        return f"{t}"
    if t < 10:
        return "the single digits"
    if t % 10 == 0:
        return f"{t}"
    decade = (t // 10) * 10
    unit = t - decade
    label = "teens" if decade == 10 else f"{decade}s"
    if unit <= 3:
        return f"the lower {label}"
    if unit <= 6:
        return f"the mid {label}"
    return f"the upper {label}"


def temp_in(value: float) -> str:
    """``in the lower 50s`` / ``around 50`` - ready to follow Highs/Lows."""
    phrase = temp_phrase(value)
    return f"around {phrase}" if phrase.isdigit() else f"in {phrase}"


def _pop_phrase(pop: int) -> str:
    if pop < 20:
        return "No precipitation is expected."
    if pop < 40:
        return f"A slight chance of precipitation near {pop} percent."
    return f"Precipitation chances peak near {pop} percent."


NIGHT_SKY = {
    "sunny": "clear",
    "mostly_sunny": "mostly_clear",
    "partly": "partly",
    "mostly_cloudy": "mostly_cloudy",
    "cloudy": "cloudy",
    "showers": "showers",
    "storms": "storms",
    "snow": "snow",
    "flurries": "flurries",
    "fog": "fog",
}


def sky_phrase(sky: str) -> str:
    return {
        "sunny": "Sunny",
        "mostly_sunny": "Mostly sunny",
        "clear": "Clear",
        "mostly_clear": "Mostly clear",
        "partly": "Partly cloudy",
        "mostly_cloudy": "Mostly cloudy",
        "cloudy": "Cloudy",
        "rain": "Rain",
        "showers": "Showers",
        "storms": "Showers and thunderstorms",
        "snow": "Snow",
        "flurries": "A chance of flurries",
        "fog": "Areas of fog",
    }.get(sky, "Partly cloudy")


def direction_phrase(text: str) -> str:
    return text


_used: dict[str, list[int]] = {}


def pick(pool: list[str], key: str, rng: random.Random) -> str:
    """Pick from a phrase pool, avoiding an immediate repeat for ``key``."""
    if not pool:
        return ""
    history = _used.setdefault(key, [])
    candidates = [i for i in range(len(pool)) if i not in history[-2:]] or list(range(len(pool)))
    idx = rng.choice(candidates)
    history.append(idx)
    del history[:-4]
    return pool[idx]


def morning_transition(rng: random.Random, start_sky: str, end_sky: str, afternoon: bool = False) -> str:
    templates = (
        ["{a} early, then becoming {b}.", "{a} early, then {b}."]
        if afternoon
        else [
            "{a} in the morning, then becoming {b}.",
            "{a} early, then becoming {b}.",
            "{a} through mid morning, then {b}.",
            "{a} in the morning, becoming {b} in the afternoon.",
        ]
    )
    if start_sky == end_sky:
        return f"{sky_phrase(end_sky)}."
    return rng.choice(templates).format(
        a=sky_phrase(start_sky).lower(), b=sky_phrase(end_sky).lower()
    )


def evening_transition(rng: random.Random, start_sky: str, end_sky: str) -> str:
    templates = [
        "{a} in the evening, then becoming {b}.",
        "{a} early, then becoming {b} overnight.",
        "{a} during the evening, then {b} after midnight.",
    ]
    if start_sky == end_sky:
        return f"{sky_phrase(end_sky)}."
    return rng.choice(templates).format(
        a=sky_phrase(start_sky).lower(), b=sky_phrase(end_sky).lower()
    )


# ---------------------------------------------------------------------------
# daily model
# ---------------------------------------------------------------------------

SEASON_PATTERNS: dict[str, list[dict]] = {
    "winter": [
        {
            "name": "arctic",
            "label": "Arctic high pressure",
            "anomaly": -14,
            "pop": (0, 15),
            "wind": ("northwest", 10, 20),
            "sky": "mostly_sunny",
            "hazard": "Wind chills of 10 below to 20 below zero are possible.",
            "keys": [
                "An arctic air mass will hold temperatures 15 to 20 degrees below normal through the period.",
                "Wind chills will fall well below zero each morning, so limit time outdoors.",
            ],
        },
        {
            "name": "clipper",
            "label": "Alberta clipper",
            "anomaly": -6,
            "pop": (40, 70),
            "wind": ("west", 15, 25),
            "sky": "snow",
            "hazard": "Accumulating snow is likely, with slippery travel during the evening commute.",
            "keys": [
                "A fast moving Alberta clipper will bring a period of snow late tonight into Wednesday.",
                "Snowfall amounts of 2 to 4 inches are possible, along with a gusty west wind.",
            ],
        },
        {
            "name": "lake_effect",
            "label": "Lake effect snow",
            "anomaly": -9,
            "pop": (30, 55),
            "wind": ("northwest", 10, 20),
            "sky": "flurries",
            "hazard": "Lake effect snow bands may produce locally heavy accumulation in northwest Indiana.",
            "keys": [
                "Cold northwesterly flow across Lake Michigan will support lake effect snow bands.",
                "The heaviest snow should remain near the lake shore in Lake and Porter counties.",
            ],
        },
        {
            "name": "quiet_cold",
            "label": "Quiet and cold",
            "anomaly": -3,
            "pop": (0, 20),
            "wind": ("west", 5, 15),
            "sky": "partly",
            "hazard": None,
            "keys": [
                "Generally dry conditions are expected through the upcoming work week.",
                "Temperatures will run a few degrees below normal with cold nights and light winds.",
            ],
        },
        {
            "name": "warm_sector",
            "label": "Mild southwesterly flow",
            "anomaly": 9,
            "pop": (15, 35),
            "wind": ("southwest", 10, 20),
            "sky": "mostly_cloudy",
            "hazard": None,
            "keys": [
                "Mild southwesterly flow will push temperatures well above normal for a couple of days.",
                "A few sprinkles or light showers cannot be ruled out late in the period.",
            ],
        },
    ],
    "spring": [
        {
            "name": "showers",
            "label": "Periods of showers",
            "anomaly": -2,
            "pop": (40, 70),
            "wind": ("southwest", 10, 20),
            "sky": "showers",
            "hazard": "Periods of showers, with a few embedded thunderstorms.",
            "keys": [
                "Periods of showers are expected as a slow moving front stalls across the region.",
                "A few thunderstorms are possible, mainly during the afternoon and evening.",
            ],
        },
        {
            "name": "severe",
            "label": "Severe weather threat",
            "anomaly": 8,
            "pop": (40, 70),
            "wind": ("south", 15, 30),
            "sky": "storms",
            "hazard": "Scattered severe thunderstorms with damaging wind and large hail are possible.",
            "keys": [
                "There is a threat for severe thunderstorms Tuesday afternoon and evening.",
                "Damaging winds, large hail and a few tornadoes are all possible with the strongest storms.",
            ],
        },
        {
            "name": "quiet",
            "label": "Quiet and dry",
            "anomaly": 2,
            "pop": (0, 20),
            "wind": ("northwest", 5, 15),
            "sky": "mostly_sunny",
            "hazard": None,
            "keys": [
                "A quiet and dry pattern is coming up over the next few days.",
                "High pressure will keep skies mostly clear with a gradual warming trend.",
            ],
        },
        {
            "name": "windy",
            "label": "Windy and warm",
            "anomaly": 10,
            "pop": (10, 30),
            "wind": ("south", 20, 35),
            "sky": "partly",
            "hazard": "South winds of 25 to 35 miles per hour are expected, with gusts to 45.",
            "keys": [
                "Strong southerly winds will develop Wednesday ahead of an approaching cold front.",
                "Wind gusts of 40 to 45 miles per hour are possible, along with a very high fire danger.",
            ],
        },
    ],
    "summer": [
        {
            "name": "hot",
            "label": "Hot and humid",
            "anomaly": 8,
            "pop": (10, 30),
            "wind": ("southwest", 5, 15),
            "sky": "mostly_sunny",
            "hazard": "Heat index values of 100 to 105 are expected during the afternoon.",
            "keys": [
                "Hot and humid conditions will continue, with heat index values near 100 each afternoon.",
                "Limit strenuous outdoor activity and drink plenty of water.",
            ],
        },
        {
            "name": "stormy",
            "label": "Daily storm chances",
            "anomaly": 4,
            "pop": (50, 80),
            "wind": ("west", 5, 15),
            "sky": "storms",
            "hazard": "Scattered thunderstorms may produce heavy downpours and brief gusty winds.",
            "keys": [
                "Scattered thunderstorms will develop each afternoon and evening.",
                "Storms will be slow moving, so locally heavy rainfall is possible.",
            ],
        },
        {
            "name": "quiet_summer",
            "label": "Pleasant high pressure",
            "anomaly": 0,
            "pop": (0, 15),
            "wind": ("northeast", 5, 15),
            "sky": "mostly_sunny",
            "hazard": None,
            "keys": [
                "Drier and more tranquil weather will spread across the region after midnight.",
                "Expect comfortable humidity and plenty of sunshine through the weekend.",
            ],
        },
        {
            "name": "cool",
            "label": "Cool northwest flow",
            "anomaly": -6,
            "pop": (10, 30),
            "wind": ("northwest", 10, 20),
            "sky": "partly",
            "hazard": None,
            "keys": [
                "A cool northwest flow will bring below normal temperatures and low humidity.",
                "Nights will be comfortably cool with lows in the 50s.",
            ],
        },
    ],
    "fall": [
        {
            "name": "quiet_dry",
            "label": "Quiet and dry",
            "anomaly": 2,
            "pop": (0, 20),
            "wind": ("southwest", 5, 15),
            "sky": "mostly_sunny",
            "hazard": None,
            "keys": [
                "Generally dry conditions are expected through the upcoming work week.",
                "A slow warming trend will return temperatures to above average by mid to late week.",
            ],
        },
        {
            "name": "showers",
            "label": "Periods of showers",
            "anomaly": -1,
            "pop": (40, 70),
            "wind": ("southwest", 10, 20),
            "sky": "showers",
            "hazard": "Periods of showers, with a few thunderstorms possible.",
            "keys": [
                "Periods of showers or sprinkles will continue this afternoon.",
                "Additional showers and drizzle are possible this evening and through the day on Monday.",
            ],
        },
        {
            "name": "foggy",
            "label": "Patchy fog",
            "anomaly": 3,
            "pop": (5, 25),
            "wind": ("calm", 0, 5),
            "sky": "partly",
            "hazard": "Patchy fog late tonight, with locally dense fog south of Interstate 80.",
            "keys": [
                "Some fog is possible tonight, especially south of Interstate 80.",
                "There is a threat for locally dense fog with visibility under a quarter mile.",
            ],
        },
        {
            "name": "colder",
            "label": "Turning colder",
            "anomaly": -9,
            "pop": (20, 45),
            "wind": ("northwest", 15, 25),
            "sky": "mostly_cloudy",
            "hazard": "A cold front will bring gusty winds and the first flakes of the season.",
            "keys": [
                "A strong cold front will bring much colder air for the weekend.",
                "Rain may mix with or change to light snow Saturday night, mainly north of Interstate 80.",
            ],
        },
        {
            "name": "warm",
            "label": "Well above normal",
            "anomaly": 12,
            "pop": (5, 25),
            "wind": ("south", 10, 20),
            "sky": "partly",
            "hazard": None,
            "keys": [
                "Above to much above average temperatures are expected to continue through the weekend.",
                "Highs will run 10 to 15 degrees above climatology with a gusty south wind.",
            ],
        },
    ],
}


def season_of(month: int) -> str:
    if month in (12, 1, 2):
        return "winter"
    if month in (3, 4, 5):
        return "spring"
    if month in (6, 7, 8):
        return "summer"
    return "fall"


@dataclass
class DayWeather:
    day: date
    high: int
    low: int
    sky: str
    pop: int
    wind_dir: str
    wind_min: int
    wind_max: int
    pattern: dict
    hazard: str | None
    snow: float = 0.0
    precip: float = 0.0
    fog: bool = False

    @property
    def season(self) -> str:
        return season_of(self.day.month)


@dataclass
class Observation:
    ident: str
    name: str
    state: str
    temp: int
    dewpoint: int
    wind_dir: str
    wind_speed: int
    sky: str
    visibility: float
    precip: float = 0.0
    snow: str = "Missing"

    @property
    def label(self) -> str:
        return f"{self.name} {self.state}"


@dataclass
class Period:
    label: str
    is_night: bool
    sky: str
    temp: int
    pop: int
    wind: list[str]
    text: str
    sentences: list[str] = field(default_factory=list)


SITE_BY_CITY = {
    "Valparaiso": "VPZ",
    "Gary": "GYY",
    "Chicago": "ORD",
    "Chicago O'Hare": "ORD",
    "Chicago Midway": "MDW",
    "Aurora": "AUZ",
    "Joliet": "JOT",
    "Waukegan": "UGN",
    "Rockford": "RFD",
    "Kankakee": "IKK",
    "Rensselaer": "RNZ",
    "Wheaton": "DPA",
}

EXTRA_STATIONS = [
    ("Rockford", "IL", 52, 12),
    ("Madison", "WI", 50, 10),
    ("Milwaukee", "WI", 51, 14),
    ("Springfield", "IL", 56, 13),
    ("Lincoln", "IL", 55, 11),
    ("Indianapolis", "IN", 57, 9),
    ("South Bend", "IN", 53, 12),
]

WEEKDAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

DISPLAY_NAMES = {
    "ORD": "Chicago O'Hare",
    "MDW": "Chicago Midway",
    "PWK": "Chicago Executive Airport",
    "DPA": "DuPage Airport",
    "AUZ": "Aurora Municipal Airport",
    "UGN": "Waukegan",
    "RFD": "Rockford",
    "JOT": "Joliet",
    "IKK": "Kankakee",
    "VPZ": "Valparaiso",
    "GYY": "Gary",
    "RNZ": "Rensselaer",
    "MMO": "Morrison",
    "OTW": "Ottawa",
    "PNT": "Pontiac",
    "RZL": "Rensselaer",
}


def display_name(ident_or_name: str) -> str:
    key = ident_or_name.upper()
    if key in DISPLAY_NAMES:
        return DISPLAY_NAMES[key]
    for k, v in DISPLAY_NAMES.items():
        if v.upper() == key:
            return v
    return ident_or_name.title()


def _ordinal_anomaly(day: date) -> float:
    n = day.toordinal()
    return 5.0 * math.sin(n * 0.37) + 3.0 * math.sin(n * 0.11 + 1.7)


class WeatherModel:
    """Deterministic daily weather for a window of dates."""

    def __init__(self, start: date | None = None, seed_offset: int = 0):
        self.start = start or tz.central_now()[0].date()
        self._rng = random.Random(self.start.toordinal() + seed_offset)
        self.season = season_of(self.start.month)
        self.pattern = self._pick_pattern()
        self.days: list[DayWeather] = self._build_days(10)

    # -- construction ----------------------------------------------------
    def _pick_pattern(self) -> dict:
        patterns = SEASON_PATTERNS[self.season]
        weights = [3, 2, 2, 2, 1][: len(patterns)]
        return self._rng.choices(patterns, weights=weights, k=1)[0]

    def _build_days(self, count: int) -> list[DayWeather]:
        out: list[DayWeather] = []
        pattern = self.pattern
        wet_start = self._rng.randint(0, 3)
        wet_len = self._rng.randint(1, 3)
        for i in range(count):
            day = self.start + timedelta(days=i)
            sit = SITES["ORD"]
            nh, nl, _, _ = climate.normals_for(sit, day)
            anomaly = _ordinal_anomaly(day) + pattern["anomaly"] * 0.75
            high = nh + anomaly + (3 if pattern["sky"] in ("sunny", "mostly_sunny") else -2)
            low = nl + anomaly * 0.8 + (2 if pattern["sky"] in ("cloudy", "showers") else 0)

            in_wet = wet_start <= i < wet_start + wet_len
            base_pop = self._rng.randint(*pattern["pop"])
            pop = max(0, min(95, base_pop + (20 if in_wet else -10)))
            if pop >= 60:
                sky = "storms" if pattern["sky"] in ("storms", "showers") else "showers"
            elif pop >= 40:
                sky = "showers" if pattern["sky"] in ("showers", "storms") else "mostly_cloudy"
            elif pop >= 20:
                sky = "partly"
            else:
                sky = pattern["sky"] if pattern["sky"] in ("sunny", "mostly_sunny", "partly") else "partly"

            wdir, wmin, wmax = pattern["wind"]
            jitter = self._rng.randint(-3, 5)
            wmin = max(0, wmin + jitter)
            wmax = max(wmin, wmax + jitter)
            if wdir != "calm" and wmin < 5:
                wmin = 5
                wmax = max(wmin + 5, wmax)
            if wdir == "calm":
                wmin, wmax = 0, 5
            pop = int(round(pop / 5.0) * 5)

            hazard = pattern["hazard"]
            fog = pattern["name"] == "foggy" or (pop < 25 and self._rng.random() < 0.12)

            snow = 0.0
            if sky in ("snow", "flurries"):
                snow = round(self._rng.uniform(0.5, 3.5 if pattern["name"] == "clipper" else 1.5), 1)
            precip = round(pop / 100.0 * self._rng.uniform(0.05, 0.55), 2) if pop >= 30 else 0.0
            out.append(
                DayWeather(
                    day=day,
                    high=int(round(high)),
                    low=int(round(low)),
                    sky=sky,
                    pop=pop,
                    wind_dir=wdir,
                    wind_min=wmin,
                    wind_max=wmax,
                    pattern=pattern,
                    hazard=hazard,
                    snow=snow,
                    precip=precip,
                    fog=fog,
                )
            )
        return out

    # -- lookups ---------------------------------------------------------
    def day(self, offset: int = 0) -> DayWeather:
        if offset < len(self.days):
            return self.days[offset]
        extra = self._build_days(offset + 5)
        self.days = extra
        return self.days[offset]

    def site_day(self, offset: int = 0, site: str = "ORD") -> DayWeather:
        """Adjust the base (O'Hare) day for another site's climatology."""
        base = self.day(offset)
        sit = climate.site(site) or SITES["ORD"]
        nh, nl, _, _ = climate.normals_for(sit, base.day)
        bh, bl, _, _ = climate.normals_for(SITES["ORD"], base.day)
        d_high = base.high + (nh - bh)
        d_low = base.low + (nl - bl)
        return DayWeather(
            base.day, int(round(d_high)), int(round(d_low)), base.sky, base.pop,
            base.wind_dir, base.wind_min, base.wind_max, base.pattern,
            base.hazard, base.snow, base.precip, base.fog,
        )

    # -- period text -----------------------------------------------------
    def periods(self, city: str, count: int = 7) -> list[Period]:
        """Forecast periods starting with the current part of today."""
        site = SITE_BY_CITY.get(city, "ORD")
        periods: list[Period] = []
        now, _ = tz.central_now()
        today = self.site_day(0, site)
        if 5 <= now.hour < 16:
            periods.append(self._period_text(today, "This afternoon", night=False))
            periods.append(self._period_text(today, "Tonight", night=True))
        elif 16 <= now.hour < 21:
            periods.append(self._period_text(today, "Tonight", night=True))
        else:
            periods.append(self._period_text(today, "Overnight", night=True))
        for i in range(1, count + 1):
            d = self.site_day(i, site)
            name = WEEKDAY_NAMES[d.day.weekday()]
            periods.append(self._period_text(d, name, night=False))
            periods.append(self._period_text(d, f"{name} night", night=True))
        return periods

    def _wind_sentence(self, d: DayWeather, night: bool) -> str:
        if d.wind_max <= 5:
            return "Light and variable winds."
        if d.wind_min == d.wind_max:
            return f"{d.wind_dir.capitalize()} winds around {d.wind_max} miles per hour."
        if d.wind_max - d.wind_min <= 5:
            return f"{d.wind_dir.capitalize()} winds around {d.wind_max} miles per hour."
        return f"{d.wind_dir.capitalize()} winds {d.wind_min} to {d.wind_max} miles per hour."

    def _period_text(self, d: DayWeather, label: str, night: bool, tonight: bool = False) -> Period:
        rng = random.Random(hash((d.day.toordinal(), label, night)) & 0xFFFFFFFF)
        sentences: list[str] = []
        sky = NIGHT_SKY.get(d.sky, d.sky) if night else d.sky

        if d.sky in ("showers", "storms", "snow", "flurries"):
            opening = {
                "showers": ["Cloudy with periods of showers.", "Showers likely.", "Occasional showers."],
                "storms": [
                    "Showers and thunderstorms likely.",
                    "Mostly cloudy with scattered thunderstorms.",
                ],
                "snow": ["Snow likely.", "Periods of snow."],
                "flurries": ["A chance of flurries.", "Cloudy with a chance of light snow."],
            }[d.sky]
            sentences.append(rng.choice(opening))
        elif night:
            if rng.random() < 0.45:
                alt = "mostly_cloudy" if sky in ("clear", "mostly_clear") else "clear"
                sentences.append(evening_transition(rng, sky, alt))
            else:
                sentences.append(f"{sky_phrase(sky)}.")
        else:
            start = sky
            if rng.random() < 0.5:
                start = "partly" if sky in ("mostly_sunny", "sunny") else "mostly_cloudy"
            sentences.append(morning_transition(rng, start, sky, afternoon=label == "This afternoon"))

        if night and d.fog:
            sentences.append(
                rng.choice([
                    "Patchy fog developing late.",
                    "Areas of fog after midnight.",
                    "Patchy fog late with visibility under a mile at times.",
                ])
            )

        if night:
            sentences.append(f"Lows {temp_in(d.low)}.")
        else:
            sentences.append(f"Highs {temp_in(d.high)}.")

        sentences.append(self._wind_sentence(d, night))

        if d.pop >= 30:
            shower_word = "snow" if d.sky in ("snow", "flurries") else "precipitation"
            if rng.random() < 0.35:
                sentences.append(f"Chance of {shower_word} {d.pop} percent.")
            else:
                sentences.append(f"Chance of precipitation {d.pop} percent.")

        text = " ".join(sentences)
        return Period(label, night, sky, d.low if night else d.high, d.pop, [d.wind_dir], text, sentences)

    # -- spoken pieces ---------------------------------------------------
    def radio_forecast(self, city: str, station: dict, days: int = 7) -> str:
        periods = self.periods(city, days)
        parts = [
            f"Here is the forecast for {city} and surrounding communities."
        ]
        for idx, p in enumerate(periods):
            prefix = "For " if idx == 0 else ""
            label = p.label
            body = p.text
            if prefix:
                label = label[:1].lower() + label[1:]
                body = body[:1].lower() + body[1:]
            parts.append(f"{prefix}{label}, {body}")
        return "\n\n".join(parts)

    def zone_forecast_text(self, ugc_list: list[str], city_map: dict | None = None) -> str:
        """AWIPS style ZFP body, one block per zone."""
        blocks: list[str] = []
        for ugc in ugc_list:
            z = zones.zone(ugc)
            if not z or z.marine:
                continue
            city = (city_map or {}).get(ugc) or zones.seat(ugc, z.name)
            periods = self.periods(city, 7)
            lines = [f"{ugc}-", f"{z.name}-", f"Including the city of {city}"]
            for p in periods[:11]:
                tag = p.label.upper()
                body = p.text[:1].upper() + p.text[1:]
                lines.append(textwrap.fill(f".{tag}...{body}", 69, subsequent_indent=""))
            blocks.append("\n".join(lines))
        return "\n\n".join(blocks)

    def key_messages(self) -> str:
        keys = self.pattern["keys"]
        lead = "Here are the Key Forecast Messages for portions of northern and central Illinois, and northwest Indiana."
        return lead + " " + " ".join(keys)

    def current_conditions(self, city: str) -> str:
        site = SITE_BY_CITY.get(city, "ORD")
        obs = self.observation(site)
        sky = {
            "sunny": "Sunny",
            "mostly_sunny": "Mostly sunny",
            "partly": "Partly cloudy",
            "mostly_cloudy": "Mostly cloudy",
            "cloudy": "Cloudy",
            "showers": "Light rain",
            "storms": "Thunderstorms",
            "snow": "Light snow",
            "flurries": "Light snow",
            "fog": "Fog",
        }.get(obs.sky, "Partly cloudy")
        return (
            f"At {display_name(obs.ident)}, the weather conditions are {sky.lower()}. "
            f"The temperature is {obs.temp} degrees, the dew point is {obs.dewpoint}, "
            f"and the wind is {obs.wind_dir} at {obs.wind_speed} miles per hour. "
            f"Visibility is {int(obs.visibility)} miles."
        )

    def observation(self, ident: str = "ORD") -> Observation:
        sit = climate.site(ident)
        if not sit:
            sit = SITES["ORD"]
        d = self.site_day(0, sit.ident)
        now, _ = tz.central_now()
        hour = now.hour + now.minute / 60.0
        # cosine diurnal curve, minimum near 5am, maximum near 3pm
        frac = math.cos((hour - 15) / 24.0 * 2 * math.pi)
        temp = (d.high + d.low) / 2 + (d.high - d.low) / 2 * frac
        if d.sky in ("showers", "storms", "cloudy", "snow"):
            temp -= 3
        dew_spread = 8 if d.pop < 30 else 4
        return Observation(
            ident=sit.ident,
            name=sit.name,
            state=sit.state,
            temp=int(round(temp)),
            dewpoint=int(round(temp - dew_spread)),
            wind_dir=d.wind_dir,
            wind_speed=max(0, d.wind_max - 3),
            sky=d.sky,
            visibility=2.0 if d.fog else 10.0,
            precip=d.precip,
            snow=f"{d.snow:.1f}" if d.snow else "Missing",
        )

    def observations(self) -> list[Observation]:
        order = ["VPZ", "GYY", "ORD", "MDW", "PWK", "JOT", "IKK", "UGN", "AUZ", "DPA", "RFD"]
        return [self.observation(k) for k in order]

    def roundup(self) -> str:
        obs = self.observations()
        lead = obs[0]
        pieces = [
            f"Elsewhere around the area, in {display_name(lead.ident)}, the temperature is {lead.temp} degrees."
        ]
        for o in obs[1:]:
            pieces.append(
                f"In {display_name(o.ident)}, {o.temp} degrees with a {o.wind_dir} wind "
                f"at {o.wind_speed} miles per hour."
            )
        regional = ["Now here are the observations for around the midwest."]
        for name, state, base_temp, wind in EXTRA_STATIONS:
            t = base_temp + int(_ordinal_anomaly(self.start) * 0.6)
            regional.append(f"In {name}, {t} degrees.")
        return "\n\n".join([
            "Here are the current conditions around the area.",
            " ".join(pieces[:3]),
            " ".join(pieces[3:]),
            " ".join(regional),
        ])

    def climate_report_lines(self) -> list[str]:
        lines: list[str] = []
        for ident in climate.SITE_ORDER:
            sit = climate.site(ident)
            if not sit:
                continue
            d = self.site_day(0, sit.ident)
            obs = self.observation(ident)
            lines.append(
                f"{sit.name} {self.start:%b} {self.start.day} Climate Report: "
                f"High: {d.high}  Low: {d.low}  Precip: {obs.precip:.2f}\"  Snow: {obs.snow}"
            )
        return lines

    def climate_summary_script(self) -> str:
        sit = SITES["VPZ"]
        day = self.start
        nh, nl, np_, _ = climate.normals_for(sit, day)
        rh, ry, rl, rly = climate.records_for(sit, day)
        hi = int(round(nh + _ordinal_anomaly(day) * 0.8 + 6))
        lo = int(round(nl + _ordinal_anomaly(day) * 0.6 + 3))
        return (
            f"Here is the climate summary for {day:%B} {day.day}. "
            f"At Valparaiso, the high was {hi} degrees and the low was {lo}. "
            f"The normal high for today is {round(nh)} and the normal low is {round(nl)}. "
            f"The record high for this date is {rh} degrees set in {ry}, "
            f"and the record low is {rl} degrees set in {rly}."
        )

    def climate_normals_block(self) -> str:
        rows = []
        for ident in climate.SITE_ORDER[:8]:
            sit = climate.site(ident)
            if not sit:
                continue
            nh, nl, np_, ns = climate.normals_for(sit, self.start)
            rh, ry, rl, rly = climate.records_for(sit, self.start)
            rows.append(
                f"{sit.name:<26} Normal {round(nh):>3}/{round(nl):<3}  "
                f"Record {rh:>3} ({ry}) / {rl:>4} ({rly})"
            )
        return "\n".join(rows)

    def hazardous_outlook(self) -> str:
        today = self.day(0)
        d2 = self.day(1)
        patch = self.pattern
        if today.hazard:
            near = today.hazard
        elif self.pattern["name"] in ("quiet_dry", "quiet_cold", "quiet_summer"):
            near = "No hazardous weather is expected at this time."
        else:
            near = f"Hazardous weather is not expected, though {patch['label'].lower()} conditions will continue."
        extended_days = (
            f"{WEEKDAY_NAMES[self.day(2).day.weekday()]} through "
            f"{WEEKDAY_NAMES[self.day(5).day.weekday()]}"
        )
        near_text = near[:1].lower() + near[1:] if near[:1].isupper() else near
        ext_text = d2.hazard or "no hazardous weather is expected at this time"
        ext_text = ext_text[:1].lower() + ext_text[1:] if ext_text[:1].isupper() else ext_text
        return (
            "Now here is the Hazardous Weather Outlook for portions of central Illinois, "
            "east central Illinois, northeast Illinois, and northwest Indiana. "
            f"For today and tonight, {near_text} "
            f"And now the extended outlook for the period from {extended_days}, "
            f"{ext_text}. "
            "Spotter information statement, spotter activation will not be needed."
        )

    def marine_forecast(self) -> str:
        lines = []
        for z in zones.MARINE_ZONES:
            wind_max = self.day(0).wind_max + 8
            waves = max(1, round(wind_max / 5))
            small_craft = wind_max >= 18
            lines.append(
                f"{z.ugc}...{zones.MARINE_NAMES[z.ugc]}...\n"
                f"Tonight...{self.day(0).wind_dir.capitalize()} winds {wind_max - 5} to {wind_max + 5} knots. "
                f"Waves {waves} to {waves + 3} feet. "
                f"{'Small Craft Advisory in effect.' if small_craft else 'Winds and waves will remain below advisory criteria.'}\n"
                f"Wednesday...{self.day(1).wind_dir.capitalize()} winds {max(5, wind_max - 7)} to {max(10, wind_max + 3)} knots. "
                f"Waves {max(1, waves - 1)} to {waves + 2} feet."
            )
        return "\n\n".join(lines)

    def discussion(self) -> str:
        """Area Forecast Discussion body used by AFDLOT."""
        today = self.day(0)
        tomorrow = self.day(1)
        mid = self.day(3)
        late = self.day(6)
        lines = [
            f".DISCUSSION...{self.pattern['label']} will dominate the pattern through the "
            f"period. {self.pattern['keys'][0]} {self.pattern['keys'][1]}",
            "",
            f".SHORT TERM...Today through Wednesday...\n"
            f"High pressure will keep conditions {today.sky.replace('_', ' ')} today with "
            f"highs {temp_in(today.high)} and {today.wind_dir} winds "
            f"{today.wind_min} to {today.wind_max} miles per hour. "
            f"Overnight lows will fall {temp_in(today.low)}. "
            f"{_pop_phrase(today.pop)} {tomorrow.pattern['label']} arrives Tuesday with "
            f"highs {temp_in(tomorrow.high)}.",
            "",
            f".LONG TERM...Thursday through Sunday...\n"
            f"Temperatures moderate toward {temp_phrase(mid.high)} by Thursday, then trend "
            f"toward {temp_phrase(late.high)} by the weekend. "
            f"{_pop_phrase(max(d.pop for d in self.days[3:8]))}",
            "",
            f".AVIATION...VFR conditions expected through the period with brief MVFR "
            f"visibility restrictions in any shower activity. Surface winds "
            f"{today.wind_dir} at {today.wind_min} to {today.wind_max} knots.",
            "",
            ".LOT WATCHES/WARNINGS/ADVISORIES...None.",
        ]
        return "\n".join(lines)

    def discussion_script(self) -> str:
        today = self.day(0)
        return (
            "Here is the Area Forecast Discussion from the National Weather Service in "
            f"Chicago. {self.pattern['label']} will dominate the pattern through the period. "
            f"{self.pattern['keys'][0]} {self.pattern['keys'][1]} "
            f"Today, look for {sky_phrase(today.sky).lower()} conditions with highs "
            f"{temp_in(today.high)} and {today.wind_dir} winds {today.wind_min} to "
            f"{today.wind_max} miles per hour. Overnight, lows will fall "
            f"{temp_in(today.low)}. Temperatures moderate through the rest of the week."
        )

    def marine_script(self) -> str:
        wind_max = self.day(0).wind_max + 8
        waves = max(1, round(wind_max / 5))
        advisory = wind_max >= 18
        prefix = (
            "Urgent, marine weather message. The National Weather Service in Chicago has issued a "
            f"Small Craft Advisory for the nearshore waters of Lake Michigan. "
            if advisory
            else "Here is the nearshore marine forecast for Lake Michigan. "
        )
        return (
            prefix
            + f"Tonight, {self.day(0).wind_dir} winds {wind_max - 5} to {wind_max + 5} knots, "
            f"with waves {waves} to {waves + 3} feet. "
            f"{'Conditions will be hazardous to small craft. Inexperienced mariners, especially those operating smaller vessels, should avoid navigating in hazardous conditions.' if advisory else 'Conditions will remain favorable for small craft.'} "
            f"Wednesday, winds {max(5, wind_max - 7)} to {max(10, wind_max + 3)} knots, waves {max(1, waves - 1)} to {waves + 2} feet."
        )

    # -- static messages -------------------------------------------------
    def static_message(self, key: str, station: dict) -> str:
        key = key.upper()
        callsign = station.get("id", "WXJ75")
        spoken = spell_callsign(callsign)
        freq = station.get("frequency", "162.400")
        township = station.get("township", "Porter Township")
        city = station.get("city", "Valparaiso")
        state = station.get("state", "IN")
        cities = station.get("cities", [])
        if len(cities) > 2:
            cities_phrase = ", ".join(cities[:-1]) + f", and {cities[-1]}"
        elif len(cities) == 2:
            cities_phrase = f"{cities[0]} and {cities[1]}"
        else:
            cities_phrase = cities[0] if cities else city
        counties = station.get("counties", ["Lake", "Porter"])
        counties_phrase = " and ".join(counties)
        now, label = tz.central_now()

        if key == "CURRENT_TIME":
            hour = now.hour % 12 or 12
            return f"The current time is, {hour}:{now:%M} {now:%p} {same_label(label)}."
        if key == "STATION_ID":
            return (
                f"This is NOAA Weather Radio station, {spoken}, broadcasting weather information for "
                f"{cities_phrase}, operating 24 hours a day, 7 days a week, broadcasting on a frequency "
                f"of {freq} megahertz, from a transmitter in {township}. This station will broadcast "
                f"severe weather events for residents in the following areas, {counties_phrase} counties "
                f"in northwest Indiana. This broadcast originates from the National Weather Service "
                f"Forecast Office in Romeoville, Illinois. Visit us on the web at weather dot gov slash chicago."
            )
        if key == "LONG_ID":
            return (
                self.static_message("STATION_ID", station)
                + " NOAA Weather Radio is the voice of the National Weather Service, and broadcasts "
                "continuous weather information twenty four hours a day. During severe weather, this "
                "station will interrupt normal programming with the latest warnings, watches, and "
                "statements for your area. Your NOAA Weather Radio should be equipped with a tone alarm "
                "so that it can automatically alert you to hazardous weather."
            )
        if key == "SHORT_ID":
            return f"This is NOAA Weather Radio, {spoken}, {city}, {state_name(state)}."
        if key == "EMR_STATION_ID":
            return (
                f"This is NOAA Weather Radio, {spoken}, {city}, {state_name(state)}, operating on "
                f"{freq} megahertz, serving {counties_phrase} counties in northwest Indiana."
            )
        if key == "SLGT_STATION_ID":
            return f"NOAA Weather Radio, {spoken}, {city}, {freq} megahertz."
        if key == "ADVANCE":
            return (
                f"You are listening to NOAA Weather Radio, {spoken}, serving {station.get('coverage', cities_phrase)}."
            )
        if key == "OFF_AIR":
            return (
                "This NOAA Weather Radio station is temporarily off the air. Please tune to an "
                "alternate weather radio broadcast, or visit weather dot gov for the latest weather information."
            )
        if key == "SEVERE_MESSAGE":
            return (
                f"This is NOAA Weather Radio, {spoken} in {township}. Severe weather is occurring or "
                "forecast to occur in the listening area. Standard broadcasts will be curtailed to bring "
                "you the latest severe weather information. Normal broadcasts will resume when the threat "
                "of severe weather has ended."
            )
        if key == "PREPAREDNESS_ACTIONS":
            return (
                "The preceding was a test of the National Weather Service warning alarm tone. During "
                "potentially dangerous weather situations, specially equipped receivers are automatically "
                "activated to warn of the impending hazard. Tests of these receivers are normally conducted "
                "by the National Weather Service every Wednesday between 11 AM and noon. When there is the "
                "threat of, or existing severe weather in the area on Wednesday, the test is postponed until "
                "the next available good weather day. This concludes the tone alarm test. We will now return "
                "to our regular program."
            )
        if key == "NWSLOT":
            return (
                "This is NOAA Weather Radio, from the National Weather Service forecast office in "
                "Romeoville, Illinois, serving northeast Illinois and northwest Indiana. NOAA Weather "
                "Radio is the fastest way to receive life saving weather warnings directly from the "
                "National Weather Service."
            )
        if key == "SUMMARY":
            return self.summary_script([])
        return self.static_message("SHORT_ID", station)

    def summary_script(self, alerts: list) -> str:
        if not alerts:
            return (
                "There are no active watches, warnings, or advisories in effect for the listening area "
                "at this time. Your NOAA Weather Radio will alert you when new hazardous weather "
                "information is issued."
            )
        pieces = ["Here is the summary of active alerts for the listening area."]
        for alert in alerts[:6]:
            pieces.append(
                f"{alert.event} for {zones.describe_area(alert.ugc)} until {alert.expires:%I:%M %p}."
            )
        pieces.append("Stay tuned to NOAA Weather Radio for the latest information.")
        return " ".join(pieces)

    def severe_dynamic(self, alerts: list) -> str:
        if not alerts:
            return (
                "Severe weather is not occurring or forecast to occur in the listening area at this time. "
                "NOAA Weather Radio will interrupt normal programming the moment a warning is issued for "
                "Lake or Porter county."
            )
        worst = alerts[0]
        return (
            f"Severe weather is occurring in the listening area. A {worst.event} is in effect for "
            f"{zones.describe_area(worst.ugc)} until {worst.expires:%I:%M %p}. "
            f"{worst.headline} Take cover now. Stay tuned to NOAA Weather Radio for the latest "
            "updates from the National Weather Service."
        )


def same_label(label: str) -> str:
    return tz.CENTRAL_LABEL.get(label, "Central Standard Time")


def state_name(code: str) -> str:
    return zones.STATE_NAMES.get(code, code)


def spell_callsign(callsign: str) -> str:
    """``WXJ75`` -> ``W X J 75`` (how NWR reads a callsign)."""
    letters = [ch for ch in callsign.upper() if ch.isalpha()]
    digits = "".join(ch for ch in callsign.upper() if ch.isdigit())
    out = " ".join(letters)
    if digits:
        out = f"{out} {digits}" if out else digits
    return out


def spell_frequency(freq: str) -> str:
    return freq.replace(".", " point ") + " megahertz"


def spell_header(header: str) -> str:
    """Read a SAME header out loud, character by character groups."""
    body = header.replace("ZCZC", "Z C Z C").replace("NNNN", "N N N N")
    groups = body.split("-")
    return " dash ".join(
        " ".join(g) if not g.isdigit() else " ".join(list(g)) for g in groups if g
    )
