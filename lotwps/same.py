"""SAME / EAS encoder: headers, preamble, AFSK burst and EOM.

Implements the over-the-air format used by NOAA Weather Radio:

    ZCZC-ORG-EEE-PSSCCC-PSSCCC+TTTT-JJJHHMM-LLLLLLLL-

* 16 bytes of ``0xAB`` preamble before every header and before the EOM
* 520.83 bps AFSK, mark 2083.3 Hz / space 1562.5 Hz
* each character framed with start/stop bits and sent twice
* header repeated three times, then the 1050 Hz warning tone

Everything produced here is simulated audio for the BMH simulator.
"""

from __future__ import annotations

import math
import re
from array import array
from datetime import datetime, timedelta

from . import tz

PREAMBLE_BYTE = 0xAB
PREAMBLE_BYTES = 16

EVENT_CODES: dict[str, str] = {
    "Tornado Warning": "TOR",
    "Tornado Emergency": "TOR",
    "Severe Thunderstorm Warning": "SVR",
    "Flash Flood Warning": "FFW",
    "Flash Flood Watch": "FFA",
    "Flood Warning": "FLW",
    "Flood Watch": "FLA",
    "Special Weather Statement": "SPS",
    "Extreme Wind Warning": "EWW",
    "Severe Weather Statement": "SVS",
    "Tornado Watch": "TOA",
    "Severe Thunderstorm Watch": "SVA",
    "Winter Storm Warning": "WSW",
    "Winter Weather Advisory": "WWY",
    "Blizzard Warning": "BZW",
    "Ice Storm Warning": "ISW",
    "High Wind Warning": "HWW",
    "Wind Advisory": "WND",
    "Dense Fog Advisory": "FOG",
    "Small Craft Advisory": "SCY",
    "Gale Warning": "GLW",
    "Excessive Heat Warning": "EHW",
    "Heat Advisory": "HTY",
    "Required Weekly Test": "RWT",
    "Required Monthly Test": "RMT",
    "Emergency Action Notification": "EAN",
    "Civil Emergency Message": "CEM",
    "Law Enforcement Warning": "LEW",
    "Local Area Emergency": "LAE",
    "Nuclear Power Plant Warning": "NUW",
}

# same set, but handy for the GUI dropdowns in the requested order
BMH_HAZARDS = [
    "Severe Thunderstorm Warning",
    "Tornado Warning",
    "Flash Flood Warning",
    "Special Weather Statement",
    "Extreme Wind Warning",
]

ORG_WXR = "WXR"
ORG_EAS = "EAS"


class SameHeaderError(ValueError):
    pass


def event_code(event: str) -> str:
    if event in EVENT_CODES:
        return EVENT_CODES[event]
    token = event.strip().upper()
    if re.fullmatch(r"[A-Z]{3}", token):
        return token
    raise SameHeaderError(f"unknown SAME event: {event!r}")


def same_header(
    event: str,
    same_codes: list[str],
    issued_utc: datetime | None = None,
    purge_minutes: int = 30,
    callsign: str = "WXJ75/NWS",
    org: str = ORG_WXR,
) -> str:
    """Build the ``ZCZC`` header line (without preamble)."""
    if not same_codes:
        raise SameHeaderError("at least one PSSCCC code is required")
    issued_utc = issued_utc or tz.utc_now()
    purge = f"{purge_minutes // 60:02d}{purge_minutes % 60:02d}"
    body = "-".join(same_codes)
    return (
        f"ZCZC-{org}-{event_code(event)}-{body}+{purge}-"
        f"{tz.same_timestamp(issued_utc)}-{callsign.upper()}-"
    )


def eom_text() -> str:
    return "NNNN"


def purge_label(minutes: int) -> str:
    return f"{minutes // 60:02d}{minutes % 60:02d}"


def expiration(issued: datetime, minutes: int) -> datetime:
    return issued + timedelta(minutes=minutes)


# ---------------------------------------------------------------------------
# bit / AFSK encoding
# ---------------------------------------------------------------------------

def _byte_bits(value: int) -> list[int]:
    """SAME framing: start 0, 8 data bits LSB first, stop 1."""
    bits = [0]
    bits.extend((value >> i) & 1 for i in range(8))
    bits.append(1)
    return bits


def text_bits(text: str, repeat: int = 2) -> list[int]:
    bits: list[int] = []
    for byte in text.encode("ascii", "replace"):
        framed = _byte_bits(byte)
        for _ in range(repeat):
            bits.extend(framed)
    return bits


def preamble_bits() -> list[int]:
    bits: list[int] = []
    for _ in range(PREAMBLE_BYTES):
        bits.extend(_byte_bits(PREAMBLE_BYTE))
    return bits


def afsk_pcm(
    text: str,
    rate: int = 16000,
    mark: float = 2083.3,
    space: float = 1562.5,
    baud: float = 520.83,
    amplitude: float = 0.72,
    preamble: bool = True,
    repeat: int = 2,
) -> array:
    """Render ``text`` (header or NNNN) as an AFSK tone burst."""
    bits = (preamble_bits() if preamble else []) + text_bits(text, repeat=repeat)
    samples_per_bit = rate / baud
    peak = int(32767 * amplitude)
    pcm = array("h")
    phase = 0.0
    step_mark = 2.0 * math.pi * mark / rate
    step_space = 2.0 * math.pi * space / rate
    for bit in bits:
        step = step_mark if bit else step_space
        count = int(round(samples_per_bit))
        for _ in range(count):
            pcm.append(int(peak * math.sin(phase)))
            phase += step
        phase %= 2.0 * math.pi
    return pcm


def header_pcm(header: str, **kwargs) -> array:
    return afsk_pcm(header, **kwargs)


def eom_pcm(**kwargs) -> array:
    kwargs.setdefault("repeat", 2)
    return afsk_pcm(eom_text(), **kwargs)


def same_burst(
    event: str,
    same_codes: list[str],
    issued_utc: datetime | None = None,
    purge_minutes: int = 30,
    callsign: str = "WXJ75/NWS",
    repeats: int = 3,
) -> list[array]:
    """Three header bursts followed by three EOM bursts (as transmitted)."""
    header = same_header(event, same_codes, issued_utc, purge_minutes, callsign)
    bursts = [header_pcm(header) for _ in range(max(1, repeats))]
    bursts.extend(eom_pcm() for _ in range(max(1, repeats)))
    return bursts


def validate_header(header: str) -> list[str]:
    """Return a list of human readable problems with a header string."""
    problems: list[str] = []
    if not header.startswith("ZCZC-"):
        problems.append("header must start with ZCZC-")
    if not header.endswith("-"):
        problems.append("header must end with a dash")
    body = header[len("ZCZC-"):].rsplit("-", 1)[0]
    parts = body.split("-")
    if len(parts) < 5:
        problems.append("header is missing SAME fields")
        return problems
    if parts[0] not in (ORG_WXR, ORG_EAS, "CIV", "PEP"):
        problems.append(f"unknown originator {parts[0]}")
    if not re.fullmatch(r"[A-Z]{3}", parts[1]):
        problems.append("event code must be three letters")
    if not re.fullmatch(r"\d{6}", parts[2]):
        problems.append("first location code must be PSSCCC")
    return problems


def describe(header: str, when: datetime | None = None) -> str:
    """Voice-friendly expansion of a SAME header for the EAS details channel."""
    try:
        body = header[len("ZCZC-"):].rstrip("-")
        parts = body.split("-")
        code = parts[1]
        raw_locations = [p.split("+", 1)[0] for p in parts[2:]]
        locations = [p for p in raw_locations if re.fullmatch(r"\d{6}", p)]
        name = next((k for k, v in EVENT_CODES.items() if v == code), code)
        from . import zones

        county_names = []
        for loc in locations:
            ugc = zones.ugc_for_same(loc)
            if ugc:
                zone_obj = zones.ZONES[ugc]
                state = zones.STATE_NAMES.get(zone_obj.state, zone_obj.state)
                county_names.append(f"{zone_obj.name} County in {state}")
            else:
                county_names.append(loc)
        if len(county_names) > 3:
            area = f"{county_names[0]} and portions of {county_names[1]} and {county_names[2]}"
        elif county_names:
            area = " and ".join(county_names[:2]) if len(county_names) == 2 else county_names[0]
        else:
            area = "the listening area"
        return (
            f"The National Weather Service has issued a {name} for {area}. "
            f"This is a simulated emergency alert system message for {code}."
        )
    except Exception:
        return "This is a simulated emergency alert system message."
