"""Audio plumbing: PCM helpers, WAV I/O, tones and playback.

The whole system standardises on 16 kHz / 16-bit / mono so that SAPI renders,
VoiceText Paul assets, the 1050 Hz tone and the SAME AFSK bursts can be joined
into a single continuous broadcast without resampling artifacts.
"""

from __future__ import annotations

import math
import threading
import time
import wave
from array import array
from pathlib import Path

try:
    import winsound

    PLAYBACK_AVAILABLE = True
except Exception:  # pragma: no cover - non Windows
    winsound = None  # type: ignore[assignment]
    PLAYBACK_AVAILABLE = False

RATE = 16000
SAMPLE_WIDTH = 2
CHANNELS = 1


# ---------------------------------------------------------------------------
# PCM
# ---------------------------------------------------------------------------

def silence_pcm(seconds: float, rate: int = RATE) -> array:
    return array("h", bytes(int(rate * max(0.0, seconds)) * 2))


def tone_pcm(
    freq: float,
    seconds: float,
    rate: int = RATE,
    amplitude: float = 0.62,
    fade: float = 0.012,
) -> array:
    """Sine tone (1050 Hz for the NWR warning alarm)."""
    total = int(rate * max(0.0, seconds))
    peak = int(32767 * amplitude)
    fade_n = max(1, int(rate * fade))
    pcm = array("h")
    step = 2.0 * math.pi * freq / rate
    phase = 0.0
    for i in range(total):
        gain = 1.0
        if i < fade_n:
            gain = i / fade_n
        elif i > total - fade_n:
            gain = max(0.0, (total - i) / fade_n)
        pcm.append(int(peak * gain * math.sin(phase)))
        phase += step
    return pcm


def concat(*chunks: array) -> array:
    out = array("h")
    for chunk in chunks:
        if chunk:
            out.extend(chunk)
    return out


def gain(pcm: array, factor: float) -> array:
    return array("h", (max(-32768, min(32767, int(s * factor))) for s in pcm))


def mix(a: array, b: array) -> array:
    n = max(len(a), len(b))
    out = array("h", [0]) * n
    for i in range(n):
        va = a[i] if i < len(a) else 0
        vb = b[i] if i < len(b) else 0
        out[i] = max(-32768, min(32767, va + vb))
    return out


def duration(pcm: array, rate: int = RATE) -> float:
    return len(pcm) / float(rate)


def resample(pcm: array, src: int, dst: int) -> array:
    if src == dst or not pcm:
        return pcm
    ratio = dst / float(src)
    out_len = int(len(pcm) * ratio)
    out = array("h", bytes(out_len * 2))
    last = len(pcm) - 1
    for i in range(out_len):
        pos = i / ratio
        left = int(pos)
        frac = pos - left
        right = left + 1 if left < last else last
        out[i] = int(pcm[left] * (1 - frac) + pcm[right] * frac)
    return out


# ---------------------------------------------------------------------------
# WAV I/O
# ---------------------------------------------------------------------------

def pcm_to_wav_bytes(pcm: array, rate: int = RATE) -> bytes:
    import io

    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return buf.getvalue()


def write_wav(path: Path | str, pcm: array, rate: int = RATE) -> Path:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with wave.open(str(path), "wb") as wf:
        wf.setnchannels(CHANNELS)
        wf.setsampwidth(SAMPLE_WIDTH)
        wf.setframerate(rate)
        wf.writeframes(pcm.tobytes())
    return path


def read_wav(path: Path | str) -> tuple[array, int]:
    with wave.open(str(path), "rb") as wf:
        rate = wf.getframerate()
        channels = wf.getnchannels()
        width = wf.getsampwidth()
        frames = wf.readframes(wf.getnframes())
    if width == 1:
        raw = array("B", frames)
        pcm = array("h", ((b - 128) << 8 for b in raw))
    elif width == 2:
        pcm = array("h", frames)
    elif width == 4:
        raw = array("i", frames)
        pcm = array("h", (s >> 16 for s in raw))
    else:
        raise ValueError(f"unsupported sample width: {width}")
    if channels > 1:
        mono = array("h", bytes((len(pcm) // channels) * 2))
        for i in range(len(mono)):
            total = 0
            for c in range(channels):
                total += pcm[i * channels + c]
            mono[i] = int(total / channels)
        pcm = mono
    return pcm, rate


def wav_duration(path: Path | str) -> float:
    with wave.open(str(path), "rb") as wf:
        return wf.getnframes() / float(wf.getframerate() or 1)


# ---------------------------------------------------------------------------
# Playback
# ---------------------------------------------------------------------------

class AudioPlayer:
    """Blocking WAV player with a cross-thread stop (used by the TX worker)."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._playing = False
        self._stop = threading.Event()
        self._current: str | None = None

    @property
    def playing(self) -> bool:
        return self._playing

    @property
    def current(self) -> str | None:
        return self._current

    def play(self, source: Path | str | array, rate: int = RATE) -> None:
        """Play a WAV file or PCM buffer; returns when finished or stopped."""
        if isinstance(source, array):
            tmp = Path(__file__).resolve().parent.parent / "var" / "audio" / "scratch.wav"
            write_wav(tmp, source, rate)
            path = tmp
        else:
            path = Path(source)
        with self._lock:
            self._playing = True
            self._stop.clear()
            self._current = str(path)
        try:
            if PLAYBACK_AVAILABLE:
                winsound.PlaySound(
                    str(path), winsound.SND_FILENAME | winsound.SND_NODEFAULT
                )
            else:  # pragma: no cover - headless fallback
                time.sleep(wav_duration(path))
        except Exception:
            pass
        finally:
            with self._lock:
                self._playing = False
                self._current = None

    def stop(self) -> None:
        self._stop.set()
        if PLAYBACK_AVAILABLE:
            try:
                winsound.PlaySound(None, winsound.SND_PURGE)
            except Exception:
                pass
        with self._lock:
            self._playing = False

    def beep(self, freq: float = 1050, seconds: float = 0.35) -> None:
        try:
            if PLAYBACK_AVAILABLE:
                winsound.Beep(int(freq), int(seconds * 1000))
        except Exception:
            pass


_player: AudioPlayer | None = None


def player() -> AudioPlayer:
    global _player
    if _player is None:
        _player = AudioPlayer()
    return _player
