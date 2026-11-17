"""VTML-style broadcast scripts: text normalisation plus audio assembly.

A :class:`Script` is a list of parts - speech, pauses, SAME bursts, the 1050 Hz
tone, EOM, pre-rendered Paul assets. Rendering flattens everything into one
16 kHz WAV so a product plays seamlessly on the transmitter.
"""

from __future__ import annotations

import hashlib
import re
from array import array
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from . import audio, paths, same, tz
from .voices import VoiceEngine, clean_text

PAUSE = 1000  # ms used by the VTML scripts

_CALLSIGNS = {
    "WXJ75": "W X J 75",
    "KBB58": "K B B 58",
    "WNG689": "W N G 6 89",
    "KLOT": "K L O T",
    "KILN": "K I L N",
    "LOT": "L O T",
}

_ACRONYMS = {
    "NWS": "National Weather Service",
    "NWR": "NOAA Weather Radio",
    "HWO": "Hazardous Weather Outlook",
    "AFD": "Area Forecast Discussion",
    "ZFP": "Zone Forecast Product",
    "SAME": "S A M E",
    "EAS": "E A S",
    "UGC": "U G C",
    "SVR": "severe thunderstorm warning",
    "TOR": "tornado warning",
    "FFW": "flash flood warning",
    "EWW": "extreme wind warning",
    "RWT": "required weekly test",
    "RMT": "required monthly test",
    "BMH": "B M H",
    "LOTIEM": "L O T I E M",
    "LOTWPS": "L O T W P S",
}

_UNITS = [
    (r"\bmph\b", "miles per hour"),
    (r"\bMPH\b", "miles per hour"),
    (r"\bkt\b", "knots"),
    (r"\bkts\b", "knots"),
    (r"\bMHz\b", "megahertz"),
    (r"\bHz\b", "hertz"),
    (r"\bmi\b", "miles"),
    (r"\bin\.", "inches"),
    (r"\bft\b", "feet"),
    (r"%", " percent"),
    (r'"', " inches "),
    (r"&", " and "),
    (r"\+", " plus "),
    (r"@", " at "),
]


def spell_callsign(callsign: str) -> str:
    letters = [ch for ch in callsign.upper() if ch.isalpha()]
    digits = "".join(ch for ch in callsign.upper() if ch.isdigit())
    out = " ".join(letters)
    if digits:
        out = f"{out} {digits}" if out else digits
    return out


def _headline_tail(alert) -> str:
    """Avoid repeating the event name twice in the spoken alert."""
    headline = (alert.headline or "").strip().rstrip(".")
    if not headline:
        return ""
    if headline.lower().startswith(alert.event.lower()):
        return ""
    return headline + "."


def normalize(text: str) -> str:
    """Make product text sound right through SAPI / VoiceText."""
    text = clean_text(text)
    text = text.replace("\r\n", "\n")

    for name, spoken in _CALLSIGNS.items():
        text = re.sub(rf"\b{name}\b", spoken, text)
    for acronym, expansion in _ACRONYMS.items():
        text = re.sub(rf"\b{acronym}\b", expansion, text)

    for pattern, replacement in _UNITS:
        text = re.sub(pattern, replacement, text)

    # decimals: 162.400 -> 162.4, 0.00 -> 0
    text = re.sub(r"(\d+)\.(\d*?[1-9])0+\b", r"\1.\2", text)
    text = re.sub(r"(\d+)\.0+\b", r"\1", text)

    # leading zero on times: 03:52 -> 3:52
    text = re.sub(r"\b0(\d):(\d{2})\b", r"\1:\2", text)

    # AM / PM so voices do not say "am"
    text = re.sub(r"\b([Aa])\.?[Mm]\b", "A M", text)
    text = re.sub(r"\b([Pp])\.?[Mm]\b", "P M", text)

    # slash-separated pairs read better as "and"
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"\s*/\s*", " and ", text)
    text = re.sub(r"\s+([,.;:])", r"\1", text)
    return text.strip()


# ---------------------------------------------------------------------------
# scripts
# ---------------------------------------------------------------------------

@dataclass
class Part:
    kind: str  # speak | pause | tone | same | eom | silence | asset
    value: object = None
    note: str = ""


@dataclass
class Script:
    title: str = ""
    product_id: str = ""
    voice: str = "paul"
    parts: list[Part] = field(default_factory=list)
    station_id: str = ""
    priority: int = 10
    asset_key: str = ""
    created: datetime = field(default_factory=tz.utc_now)

    # -- construction ----------------------------------------------------
    def say(self, text: str, note: str = "") -> "Script":
        if text and text.strip():
            self.parts.append(Part("speak", normalize(text), note))
        return self

    def say_raw(self, text: str, note: str = "") -> "Script":
        if text and text.strip():
            self.parts.append(Part("speak", clean_text(text), note))
        return self

    def pause(self, ms: int = PAUSE) -> "Script":
        self.parts.append(Part("pause", ms))
        return self

    def tone(self, seconds: float = 8.0) -> "Script":
        self.parts.append(Part("tone", seconds))
        return self

    def same_header(self, header: str) -> "Script":
        self.parts.append(Part("same", header))
        return self

    def eom(self) -> "Script":
        self.parts.append(Part("eom", None))
        return self

    def asset(self, path: Path, key: str = "") -> "Script":
        self.parts.append(Part("asset", str(path), key))
        return self

    # -- inspection ------------------------------------------------------
    @property
    def speak_parts(self) -> list[str]:
        return [str(p.value) for p in self.parts if p.kind in ("speak",)]

    def text(self) -> str:
        return "\n\n".join(self.speak_parts)

    def expected_seconds(self) -> float:
        total = 0.0
        for p in self.parts:
            if p.kind in ("speak",):
                total += max(1.0, len(str(p.value)) / 14.5)
            elif p.kind == "pause":
                total += float(p.value) / 1000.0
            elif p.kind == "silence":
                total += float(p.value)
            elif p.kind == "tone":
                total += float(p.value)
            elif p.kind in ("same", "eom"):
                total += 2.2
            elif p.kind == "asset":
                try:
                    total += audio.wav_duration(str(p.value))
                except Exception:
                    total += 5.0
        return round(total, 1)

    def cache_key(self) -> str:
        raw = "|".join(f"{p.kind}:{p.value}" for p in self.parts)
        return hashlib.sha1(f"{self.voice}|{raw}".encode("utf-8", "replace")).hexdigest()[:16]

    # -- rendering -------------------------------------------------------
    def render(self, engine: VoiceEngine, rate: int = audio.RATE) -> Path:
        """Flatten every part into one WAV, caching by content."""
        cache = paths.AUDIO_CACHE / "products"
        cache.mkdir(parents=True, exist_ok=True)
        target = cache / f"{self.cache_key()}.wav"
        if target.exists() and target.stat().st_size > 256:
            return target

        chunks: list[array] = []
        for part in self.parts:
            try:
                chunks.append(self._render_part(part, engine, rate))
            except Exception:
                continue
        pcm = audio.concat(*chunks)
        if not pcm:
            pcm = audio.silence_pcm(0.25, rate)
        audio.write_wav(target, pcm, rate)
        return target

    def _render_part(self, part: Part, engine: VoiceEngine, rate: int) -> array:
        if part.kind == "speak":
            wav, _ = engine.render(str(part.value), self.voice)
            pcm, src_rate = audio.read_wav(wav)
            return audio.resample(pcm, src_rate, rate)
        if part.kind == "pause":
            return audio.silence_pcm(float(part.value) / 1000.0, rate)
        if part.kind == "silence":
            return audio.silence_pcm(float(part.value), rate)
        if part.kind == "tone":
            return audio.tone_pcm(1050.0, float(part.value), rate)
        if part.kind == "same":
            return same.header_pcm(str(part.value), rate=rate)
        if part.kind == "eom":
            return same.eom_pcm(rate=rate)
        if part.kind == "asset":
            path = Path(str(part.value))
            if not path.exists():
                return array("h")
            pcm, src_rate = audio.read_wav(path)
            return audio.resample(pcm, src_rate, rate)
        return array("h")

    def export_wav(self, path: Path, engine: VoiceEngine) -> Path:
        rendered = self.render(engine)
        pcm, rate = audio.read_wav(rendered)
        return audio.write_wav(path, pcm, rate)

    def export_vtml(self, path: Path) -> Path:
        pause = '<vtml_pause time="1000"/><vtml_pause time="1000"/>'
        paragraphs = [p.strip() for p in self.text().split("\n\n") if p.strip()]
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            f"\n\n{pause}\n\n".join(paragraphs) + f"\n\n{pause}\n",
            encoding="utf-8-sig",
        )
        return path


# ---------------------------------------------------------------------------
# canned scripts
# ---------------------------------------------------------------------------

def alert_script(
    alert,
    station: dict,
    voice: str = "paul",
    tone_seconds: float = 8.0,
    header_repeats: int = 3,
    eom_repeats: int = 3,
) -> Script:
    """The full EAS activation sequence: SAME x3, tone, voice, EOM x3."""
    header = alert.ensure_header()
    script = Script(
        title=f"EAS {alert.event}",
        product_id=alert.prod_id,
        voice=voice,
        station_id=station.get("id", ""),
        priority=alert.priority,
    )
    for i in range(header_repeats):
        script.same_header(header)
        script.pause(900)
    script.tone(tone_seconds)
    script.pause(1200)
    local, label = tz.central_from_utc(alert.issued)
    expires_local, expires_label = tz.central_from_utc(alert.expires)
    issued_hour = local.hour % 12 or 12
    expires_hour = expires_local.hour % 12 or 12
    script.say(
        f"The National Weather Service in Chicago has issued a {alert.event} "
        f"for {alert.area}, effective until {expires_hour}:{expires_local:%M} {expires_local:%p} "
        f"{expires_label}. {_headline_tail(alert)}"
    )
    if alert.description:
        script.say(alert.description)
    if alert.instruction:
        script.say(alert.instruction)
    script.pause(800)
    script.say(
        f"This alert was issued at {issued_hour}:{local:%M} {local:%p} {label} by the "
        f"National Weather Service forecast office in Romeoville, Illinois. Stay tuned to "
        f"NOAA Weather Radio for the latest information."
    )
    script.pause(1000)
    for _ in range(eom_repeats):
        script.eom()
        script.pause(700)
    return script


def test_script(
    station: dict,
    event: str = "Required Weekly Test",
    voice: str = "paul",
    tone_seconds: float = 8.0,
    ugc: list[str] | None = None,
) -> Script:
    """Required Weekly/Monthly Test with the full SAME + tone sequence."""
    from . import zones

    ugc = ugc or station.get("ugc", ["INZ001", "INZ002"])
    header = same.same_header(
        event,
        zones.same_list(ugc),
        purge_minutes=15,
        callsign=f"{station.get('id', 'WXJ75')}/NWS",
    )
    script = Script(
        title=event,
        product_id="RWT" if "Weekly" in event else "RMT",
        voice=voice,
        station_id=station.get("id", ""),
        priority=30,
    )
    script.say(
        f"This is NOAA Weather Radio, {spell_callsign(station.get('id', 'WXJ75'))}. "
        "The following is a test of the National Weather Service warning alarm system. "
        "This is only a test."
    )
    script.pause(1000)
    for _ in range(3):
        script.same_header(header)
        script.pause(900)
    script.tone(tone_seconds)
    script.pause(1000)
    script.say(
        "This was a test of the National Weather Service warning alarm system. "
        "During potentially dangerous weather situations, specially equipped receivers "
        "are automatically activated to warn of the impending hazard. Tests of these "
        "receivers are normally conducted every Wednesday between 11 A M and noon. "
        "When there is the threat of severe weather on Wednesday, the test is postponed "
        "until the next available good weather day. This concludes the tone alarm test. "
        "We will now return to our regular program."
    )
    script.pause(800)
    for _ in range(3):
        script.eom()
        script.pause(700)
    return script


def ticker_script(text: str, voice: str = "paul") -> Script:
    return Script(title="Ticker", product_id="TICKER", voice=voice).say(text)
