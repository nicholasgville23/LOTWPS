"""Voice engines: VoiceText Paul (assets + editor hand-off) and SAPI David/Zira.

The VoiceText editor (``VTEditor_ENG.exe``) is a GUI application with no batch
export switch, so this module does three things:

1. Plays the *real* Paul WAV assets already rendered in the asset folder
   (``WXJ75_ID.wav``, ``Forecast.wav``, ``Observations.wav`` ...).
2. Falls back to a SAPI David proxy shaped to sit close to Paul's cadence for
   any text that has no pre-rendered asset.
3. Exports the exact VTML script and opens it in ``VTEditor_ENG.exe`` so the
   user can render genuine Paul audio when they want it.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import threading
from pathlib import Path

from . import audio, paths
from .config import Settings, settings as global_settings
from .voicetext import VoiceTextPaulCLI

try:
    import pythoncom
    import win32com.client

    SAPI_AVAILABLE = True
except Exception:  # pragma: no cover - non Windows
    pythoncom = None  # type: ignore[assignment]
    win32com = None  # type: ignore[assignment]
    SAPI_AVAILABLE = False

TTS_CACHE = paths.AUDIO_CACHE / "tts"
TTS_CACHE.mkdir(parents=True, exist_ok=True)

_COMPAT = str.maketrans({
    "\u2018": "'", "\u2019": "'", "\u201c": '"', "\u201d": '"',
    "\u2013": "-", "\u2014": "-", "\u2026": "...", "\u00b0": " degrees ",
    "\u00bd": " and one half ", "\u00bc": " and one quarter ",
})


def clean_text(text: str) -> str:
    return text.translate(_COMPAT)


def _with_com(func):
    """Run ``func`` inside a COM apartment (safe from worker threads)."""
    if not SAPI_AVAILABLE:
        return None
    pythoncom.CoInitialize()
    try:
        return func()
    finally:
        try:
            pythoncom.CoUninitialize()
        except Exception:
            pass


_voices_lock = threading.RLock()
_voice_cache: list[tuple[str, str]] | None = None


def sapi_voice_list(refresh: bool = False) -> list[tuple[str, str]]:
    """Return ``[(token_id, description), ...]`` for installed SAPI voices."""
    global _voice_cache
    with _voices_lock:
        if _voice_cache is not None and not refresh:
            return list(_voice_cache)

        def _list():
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            out = []
            for token in voice.GetVoices():
                try:
                    out.append((token.Id, token.GetDescription()))
                except Exception:
                    continue
            return out

        try:
            result = _with_com(_list) or []
        except Exception:
            result = []
        _voice_cache = result
        return list(result)


def resolve_voice_name(preferred: str) -> str | None:
    voices = sapi_voice_list()
    wanted = preferred.lower()
    for _id, desc in voices:
        if wanted in desc.lower():
            return desc
    stem = wanted.replace("microsoft", "").replace("desktop", "").strip()
    for _id, desc in voices:
        if stem and stem in desc.lower():
            return desc
    return None


def sapi_render(
    text: str,
    path: Path,
    voice_name: str | None = None,
    rate: int = 0,
    volume: int = 100,
    pitch: str | None = None,
) -> Path:
    """Render text to a 16 kHz mono WAV with SAPI."""
    if not SAPI_AVAILABLE:
        raise RuntimeError("SAPI is unavailable on this host")
    text = clean_text(text).strip()
    if not text:
        raise ValueError("nothing to speak")
    path.parent.mkdir(parents=True, exist_ok=True)

    def _do():
        voice = win32com.client.Dispatch("SAPI.SpVoice")
        stream = win32com.client.Dispatch("SAPI.SpFileStream")
        fmt = win32com.client.Dispatch("SAPI.SpAudioFormat")
        ok = False
        for fmt_type in (14, 22, 0):  # 16k mono, 22k mono, default
            try:
                fmt.Type = fmt_type
                stream.Format = fmt
                ok = True
                break
            except Exception:
                continue
        stream.Open(str(path), 3, False)  # SSFMCreateForWrite
        try:
            if voice_name:
                for token in voice.GetVoices():
                    try:
                        if token.GetDescription() == voice_name:
                            voice.Voice = token
                            break
                    except Exception:
                        continue
            try:
                voice.Rate = max(-10, min(10, int(rate)))
                voice.Volume = max(0, min(100, int(volume)))
            except Exception:
                pass
            voice.AudioOutputStream = stream
            if pitch:
                escaped = (
                    text.replace("&", "&amp;")
                    .replace("<", "&lt;")
                    .replace(">", "&gt;")
                )
                ssml = f'<prosody pitch="{pitch}">{escaped}</prosody>'
                try:
                    voice.Speak(ssml, 8 | 1)  # SVSFIsXML | SVSFlagsAsync off
                except Exception:
                    voice.Speak(text, 0)
            else:
                voice.Speak(text, 0)
        finally:
            try:
                stream.Close()
            except Exception:
                pass
        return ok

    _with_com(_do)
    if not path.exists() or path.stat().st_size < 64:
        raise RuntimeError("SAPI produced no audio")
    return path


class Voice:
    key = "voice"
    label = "Voice"

    def render(self, text: str, dest: Path) -> Path:
        raise NotImplementedError


class SapiVoice(Voice):
    def __init__(self, key: str, label: str, sapi_name: str, rate: int = 0, volume: int = 100):
        self.key = key
        self.label = label
        self.sapi_name = sapi_name
        self.rate = rate
        self.volume = volume

    @property
    def available(self) -> bool:
        return SAPI_AVAILABLE and resolve_voice_name(self.sapi_name) is not None

    def resolved_name(self) -> str | None:
        return resolve_voice_name(self.sapi_name)

    def render(self, text: str, dest: Path) -> Path:
        name = self.resolved_name()
        return sapi_render(text, dest, name, self.rate, self.volume)


class PaulVoice(Voice):
    """VoiceText Paul with asset playback and a SAPI proxy fallback."""

    key = "paul"

    def __init__(self, cfg: dict, app_settings: Settings):
        self.cfg = cfg
        self.settings = app_settings
        self.label = cfg.get("label", "VoiceText Paul")
        self.exe = Path(cfg.get("exe", ""))
        self.cli_exe = Path(cfg.get("cli_exe", ""))
        self.cli = VoiceTextPaulCLI(self.cli_exe)
        self.assets_dir = Path(cfg.get("assets_dir", ""))
        self.rate = int(cfg.get("rate", -1))
        self.pitch = str(cfg.get("pitch", "-3%"))
        self.mode = str(cfg.get("render_mode", "assets"))
        self.fallback_name = cfg.get("fallback_sapi", "Microsoft David Desktop")

    # -- assets ----------------------------------------------------------
    def asset_path(self, key: str) -> Path | None:
        """Look up a pre-rendered Paul WAV by product key (``FORECAST``...)."""
        station = self.settings.station("WXJ75") if self.settings.stations() else {}
        mapping = (station or {}).get("paul_assets", {})
        name = mapping.get(key.upper())
        if not name:
            return None
        for base in (self.assets_dir, Path(self.cfg.get("assets_dir", ""))):
            candidate = base / name
            if candidate.exists():
                return candidate
        return None

    def has_assets(self) -> bool:
        return self.assets_dir.exists()

    @property
    def editor_available(self) -> bool:
        return self.exe.exists()

    # -- rendering -------------------------------------------------------
    def render(self, text: str, dest: Path) -> Path:
        """Render with the standalone Paul CLI, registered SAPI Paul, or a David proxy."""
        if self.cli.available:
            return self.cli.render(clean_text(text), dest)

        paul_name = resolve_voice_name("VoiceText Paul") or resolve_voice_name("Paul")
        if paul_name:
            return sapi_render(text, dest, paul_name, self.rate, 100)

        name = resolve_voice_name(self.fallback_name) or resolve_voice_name("Microsoft David")
        return sapi_render(text, dest, name, self.rate, 100, pitch=self.pitch)

    @property
    def available(self) -> bool:
        paul_name = resolve_voice_name("VoiceText Paul") or resolve_voice_name("Paul")
        fallback = resolve_voice_name(self.fallback_name) or resolve_voice_name("Microsoft David")
        return self.cli.available or (SAPI_AVAILABLE and bool(paul_name or fallback))

    def describe(self) -> str:
        bits = ["VoiceText Paul"]
        if self.cli.available:
            bits.append("CLI renderer")
        if self.has_assets():
            bits.append("pre-rendered WAV assets")
        if resolve_voice_name("VoiceText Paul") or resolve_voice_name("Paul"):
            bits.append("registered SAPI voice")
        elif self.available:
            bits.append("David SAPI fallback")
        if self.editor_available:
            bits.append("VTML editor")
        return " + ".join(bits)

    # -- VTML hand-off ---------------------------------------------------
    def export_vtml(self, text: str, dest: Path) -> Path:
        """Write a VTML script the editor can load (pause tags included)."""
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        pause = '<vtml_pause time="1000"/><vtml_pause time="1000"/>'
        body = f"\n\n{pause}\n\n".join(paragraphs) + f"\n\n{pause}\n"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(body, encoding="utf-8-sig")
        return dest

    def launch_editor(self, text_file: Path) -> bool:
        if not self.editor_available:
            return False
        try:
            subprocess.Popen([str(self.exe), str(text_file)])
            return True
        except OSError:
            return False


class VoiceEngine:
    """Resolves a voice key to a renderer and caches WAVs on disk."""

    def __init__(self, app_settings: Settings | None = None):
        self.settings = app_settings or global_settings()
        self._lock = threading.RLock()
        self._voices: dict[str, Voice] = {}
        self._build()

    def _build(self) -> None:
        cfg_all = self.settings.to_dict().get("voices", {})
        for key in self.settings.voice_keys():
            cfg = cfg_all.get(key, {})
            if cfg.get("engine") == "voicetext":
                self._voices[key] = PaulVoice(cfg, self.settings)
            else:
                self._voices[key] = SapiVoice(
                    key,
                    cfg.get("label", key.title()),
                    cfg.get("sapi_name", ""),
                    int(cfg.get("rate", 0)),
                    int(cfg.get("volume", 100)),
                )

    def keys(self) -> list[str]:
        return list(self._voices.keys())

    def get(self, key: str) -> Voice:
        if key in self._voices:
            return self._voices[key]
        return next(iter(self._voices.values()))

    def labels(self) -> dict[str, str]:
        return {k: v.label for k, v in self._voices.items()}

    def describe(self) -> dict[str, str]:
        out = {}
        for key, voice in self._voices.items():
            if isinstance(voice, PaulVoice):
                out[key] = voice.describe()
            else:
                out[key] = f"{voice.label} ({'ready' if voice.available else 'missing'})"
        return out

    def cache_key(self, text: str, voice_key: str) -> str:
        raw = f"{voice_key}|{text}".encode("utf-8", "replace")
        return hashlib.sha1(raw).hexdigest()[:16]

    def cached_path(self, text: str, voice_key: str) -> Path:
        return TTS_CACHE / f"{self.cache_key(text, voice_key)}.wav"

    def render(self, text: str, voice_key: str | None = None) -> tuple[Path, bool]:
        """Render (or reuse) a WAV. Returns ``(path, from_cache)``."""
        voice_key = voice_key or self.settings.get("voices.default", "paul")
        text = clean_text(text).strip()
        if not text:
            raise ValueError("empty text")
        with self._lock:
            dest = self.cached_path(text, voice_key)
            if dest.exists() and dest.stat().st_size > 128:
                return dest, True
            voice = self.get(voice_key)
            try:
                voice.render(text, dest)
            except Exception:
                fallback = self.get("david") if voice_key != "david" else self.get("zira")
                fallback.render(text, dest)
            return dest, False

    def prune_cache(self, keep: int = 64) -> int:
        files = sorted(TTS_CACHE.glob("*.wav"), key=lambda p: p.stat().st_mtime, reverse=True)
        removed = 0
        for stale in files[keep:]:
            try:
                stale.unlink()
                removed += 1
            except OSError:
                pass
        return removed

    def test_voice(self, voice_key: str, text: str = "") -> Path:
        phrase = text or (
            "This is NOAA Weather Radio, testing the voice engine for the "
            "Broadcast Message Handler."
        )
        path, _ = self.render(phrase, voice_key)
        return path

    def export_and_open(self, text: str, name: str = "lotiem_vtml") -> Path | None:
        """Write the VTML script and hand it to VTEditor_ENG.exe."""
        paul = self.get("paul")
        if not isinstance(paul, PaulVoice):
            return None
        target = paths.EXPORTS / f"{name}.txt"
        paul.export_vtml(text, target)
        paul.launch_editor(target)
        return target


def available_voices_report() -> str:
    lines = ["SAPI voices installed:"]
    for token_id, desc in sapi_voice_list():
        lines.append(f"  - {desc}  [{token_id[:38]}]")
    if len(lines) == 1:
        lines.append("  (none found - install SAPI desktop voices)")
    return "\n".join(lines)
