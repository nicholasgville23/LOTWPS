from __future__ import annotations

import math
import struct
import wave
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable


EVENT_CODES = {
    "Tornado Warning": "TOR", "Tornado Emergency": "TOR",
    "Severe Thunderstorm Warning": "SVR", "Flash Flood Warning": "FFW",
    "Special Weather Statement": "SVS", "Extreme Wind Warning": "EWW",
    "Required Weekly Test": "RWT", "Required Monthly Test": "RMT",
    "Winter Storm Warning": "WSW", "Flood Warning": "FLW",
}


def normalize_same_area_code(value: str) -> str:
    code = value.strip().upper()
    if len(code) == 6 and code.isdigit():
        return code
    # County UGC -> SAME PSSCCC. P=0 denotes the whole county.
    if len(code) == 6 and code[2] == "C" and code[:2].isalpha() and code[3:].isdigit():
        state = {"IL": "17", "IN": "18"}.get(code[:2])
        if state:
            return "0" + state + code[3:]
    raise ValueError(f"{value!r} is not a six-digit SAME FIPS code or supported county UGC")


def build_same_header(event: str, areas: Iterable[str], duration_minutes: int = 15,
                      issued_at: datetime | None = None, station_id: str = "KLOT",
                      originator: str = "WXR") -> str:
    event_code = EVENT_CODES.get(event, event if len(event) == 3 else None)
    if not event_code or len(event_code) != 3 or not event_code.isalnum():
        raise ValueError(f"No valid SAME event code configured for {event!r}")
    area_codes = [normalize_same_area_code(code) for code in areas]
    if not area_codes:
        raise ValueError("At least one configured SAME FIPS area code is required")
    if len(area_codes) > 32:
        raise ValueError("SAME headers support no more than 32 area codes")
    if not 1 <= int(duration_minutes) <= 9999:
        raise ValueError("duration_minutes must be between 1 and 9999")
    moment = (issued_at or datetime.now(timezone.utc)).astimezone(timezone.utc)
    valid_time = f"{moment.timetuple().tm_yday:03d}{moment:%H%M}"
    origin = originator.upper()
    if origin not in {"WXR", "CIV", "EAS"}:
        raise ValueError("originator must be WXR, CIV, or EAS")
    ident = (station_id.upper() + "        ")[:8]
    return f"ZCZC-{origin}-{event_code}-{'-'.join(area_codes)}+{int(duration_minutes):04d}-{valid_time}-{ident}-"


def _append_fsk(samples: list[int], text: str, sample_rate: int, baud: float = 520.8333333333) -> None:
    # SAME FSK: 2083.3-Hz mark / 1562.5-Hz space, 520.833 bit/s.
    phase = 0.0
    bit_samples = sample_rate / baud
    bit_index = 0
    for byte in bytes([0xAB] * 16) + text.encode("ascii"):
        for bit in range(8):  # least-significant bit first
            frequency = 2083.3 if ((byte >> bit) & 1) else 1562.5
            start, end = round(bit_index * bit_samples), round((bit_index + 1) * bit_samples)
            for _sample in range(start, end):
                samples.append(int(0.68 * 32767 * math.sin(phase)))
                phase = (phase + 2.0 * math.pi * frequency / sample_rate) % (2.0 * math.pi)
            bit_index += 1


def _append_silence(samples: list[int], seconds: float, sample_rate: int) -> None:
    samples.extend([0] * round(seconds * sample_rate))


def _append_tone(samples: list[int], frequency: float, seconds: float, sample_rate: int) -> None:
    count = round(seconds * sample_rate)
    fade = min(round(0.02 * sample_rate), count // 2)
    for index in range(count):
        env = index / fade if fade and index < fade else (count - index - 1) / fade if fade and index >= count - fade else 1.0
        samples.append(int(0.55 * 32767 * env * math.sin(2 * math.pi * frequency * index / sample_rate)))


def _append_spoken_wav(samples: list[int], wav_path: str | Path, target_rate: int) -> None:
    with wave.open(str(wav_path), "rb") as source:
        channels, width, rate = source.getnchannels(), source.getsampwidth(), source.getframerate()
        if source.getcomptype() != "NONE" or width != 2 or channels not in (1, 2):
            raise ValueError("Spoken audio must be uncompressed 16-bit mono or stereo PCM WAV")
        raw = source.readframes(source.getnframes())
    values = list(struct.unpack("<" + "h" * (len(raw) // 2), raw))
    if channels == 2:
        values = [(values[i] + values[i + 1]) // 2 for i in range(0, len(values), 2)]
    if rate == target_rate:
        samples.extend(values)
        return
    if values:
        for index in range(round(len(values) * target_rate / rate)):
            pos = index * rate / target_rate
            left, right = min(int(pos), len(values) - 1), min(int(pos) + 1, len(values) - 1)
            fraction = pos - int(pos)
            samples.append(round(values[left] * (1 - fraction) + values[right] * fraction))


def write_test_alert_wav(output_path: str | Path, header: str, spoken_wav: str | Path | None = None,
                         sample_rate: int = 48000, header_repeats: int = 3,
                         eom_repeats: int = 3, attention_tone_seconds: float = 8.0) -> Path:
    """Create an EAS/SAME test file for local playback and lab validation only."""
    if header_repeats < 1 or eom_repeats < 1:
        raise ValueError("header_repeats and eom_repeats must be >= 1")
    samples: list[int] = []
    for _ in range(header_repeats):
        _append_fsk(samples, header, sample_rate)
        _append_silence(samples, 1.0, sample_rate)
    _append_tone(samples, 1050.0, attention_tone_seconds, sample_rate)
    if spoken_wav is not None:
        _append_silence(samples, 0.5, sample_rate)
        _append_spoken_wav(samples, spoken_wav, sample_rate)
        _append_silence(samples, 0.5, sample_rate)
    for _ in range(eom_repeats):
        _append_fsk(samples, "NNNN", sample_rate)
        _append_silence(samples, 1.0, sample_rate)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(output), "wb") as wav:
        wav.setnchannels(1); wav.setsampwidth(2); wav.setframerate(sample_rate)
        wav.writeframes(struct.pack("<" + "h" * len(samples), *samples))
    return output
