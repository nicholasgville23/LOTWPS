"""Windows SAPI speech adapter.

David and Zira are selected from voices installed in Windows. Paul is used when
a matching SAPI voice is installed; otherwise the configured VoiceText editor
can be opened for manual production. The editor executable is not assumed to
have an undocumented command-line TTS interface.
"""

from __future__ import annotations

import subprocess
from pathlib import Path


class SpeechError(RuntimeError):
    """Raised when speech synthesis cannot be completed."""


class SpeechEngine:
    def __init__(self, voicetext_exe: str = "") -> None:
        self.voicetext_exe = voicetext_exe

    @staticmethod
    def _sapi_tokens():
        try:
            import pythoncom
            import win32com.client
        except ImportError as exc:
            raise SpeechError(
                "Windows SAPI integration requires the optional pywin32 package. "
                "Install with: pip install -e .[windows-sapi]"
            ) from exc
        pythoncom.CoInitialize()
        try:
            voice = win32com.client.Dispatch("SAPI.SpVoice")
            tokens = voice.GetVoices()
            return pythoncom, voice, tokens
        except Exception:
            pythoncom.CoUninitialize()
            raise

    def available_sapi_voices(self) -> list[str]:
        pythoncom, _voice, tokens = self._sapi_tokens()
        try:
            return [str(tokens.Item(index).GetDescription()) for index in range(tokens.Count)]
        finally:
            pythoncom.CoUninitialize()

    def speak(self, text: str, voice_name: str = "David") -> str:
        if not text.strip():
            raise SpeechError("There is no text to read")
        pythoncom, voice, tokens = self._sapi_tokens()
        try:
            wanted = voice_name.casefold().replace("(sapi)", "").strip()
            match = None
            for index in range(tokens.Count):
                token = tokens.Item(index)
                description = str(token.GetDescription())
                if wanted in description.casefold():
                    match = token
                    break
            if match is None:
                if wanted == "paul":
                    return self._open_voicetext_or_explain()
                available = self.available_sapi_voices()
                raise SpeechError(
                    f"No installed SAPI voice matched '{voice_name}'. "
                    f"Available voices: {', '.join(available) or 'none'}"
                )
            voice.Voice = match
            voice.Speak(text, 0)
            return f"Read with {match.GetDescription()}"
        except SpeechError:
            raise
        except Exception as exc:
            raise SpeechError(f"Windows SAPI could not read the message: {exc}") from exc
        finally:
            pythoncom.CoUninitialize()

    def _open_voicetext_or_explain(self) -> str:
        executable = Path(self.voicetext_exe).expanduser() if self.voicetext_exe else None
        if executable and executable.is_file():
            subprocess.Popen([str(executable)], cwd=str(executable.parent))
            return "Opened VoiceText Editor. Export the speech there, then play the resulting WAV locally."
        raise SpeechError(
            "VoiceText Paul is not registered as a SAPI voice and no valid VoiceText editor path is configured. "
            "Set the executable path in Settings. LOTWPS does not guess undocumented VoiceText command-line arguments."
        )
