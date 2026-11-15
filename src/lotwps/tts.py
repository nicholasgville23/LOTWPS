from __future__ import annotations

import re
import subprocess
from pathlib import Path
from typing import Any


class TTSError(RuntimeError):
    pass


class VoiceEngine:
    """Optional pyttsx3/SAPI adapter. Proprietary voice packs are not included."""

    def __init__(self, voice_config: dict[str, Any]):
        self.config = voice_config

    def list_voices(self) -> list[dict[str, str]]:
        try:
            import pyttsx3
        except ImportError as exc:
            raise TTSError("Install optional TTS dependencies with: pip install -e .[windows]") from exc
        engine = pyttsx3.init()
        return [{"id": v.id, "name": v.name} for v in engine.getProperty("voices")]

    def _find_voice(self, profile: str, engine: Any) -> str | None:
        selected = self.config.get("profiles", {}).get(profile.lower(), {})
        patterns = [str(x).lower() for x in selected.get("match", [profile])]
        for voice in engine.getProperty("voices"):
            name = f"{voice.name} {voice.id}".lower()
            if any(re.search(re.escape(p), name) for p in patterns):
                return voice.id
        return None

    def synthesize(self, text: str, output_path: str | Path, profile: str = "paul") -> Path:
        if not text.strip():
            raise TTSError("Cannot synthesize an empty message")
        try:
            import pyttsx3
        except ImportError as exc:
            raise TTSError("Install optional TTS dependencies with: pip install -e .[windows]") from exc
        engine = pyttsx3.init()
        voice_id = self._find_voice(profile, engine)
        if not voice_id:
            raise TTSError(f"No installed voice matched {profile!r}. Available: {self.list_voices()}")
        engine.setProperty("voice", voice_id)
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        engine.save_to_file(text, str(path))
        engine.runAndWait()
        if not path.exists() or not path.stat().st_size:
            raise TTSError("Speech engine did not create an audio file")
        return path


def synthesize_with_external_command(voice_config: dict[str, Any], text: str,
                                     output_path: str | Path, voice_name: str = "Paul") -> Path:
    template = voice_config.get("voicetext_command") or []
    if not template:
        raise TTSError("No VoiceText CLI/SDK wrapper configured. VTEditor_ENG.exe may be GUI-only.")
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    args = [str(x).format(text=text, output=str(path), voice=voice_name) for x in template]
    try:
        subprocess.run(args, check=True, timeout=120)
    except (OSError, subprocess.SubprocessError) as exc:
        raise TTSError(f"VoiceText wrapper failed: {exc}") from exc
    if not path.exists() or not path.stat().st_size:
        raise TTSError("VoiceText command did not create output")
    return path
