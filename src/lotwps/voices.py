"""Voice discovery and speech adapter boundary for Windows SAPI."""
from __future__ import annotations

class SapiVoiceAdapter:
    """Late-bound SAPI adapter. Requires Windows and optional pywin32."""
    def __init__(self) -> None:
        try:
            import win32com.client  # type: ignore[import-not-found]
        except ImportError as exc:
            raise RuntimeError("SAPI voice support requires Windows and 'pip install pywin32'") from exc
        self._client = win32com.client

    def available_voices(self) -> list[str]:
        speaker = self._client.Dispatch("SAPI.SpVoice")
        voices = speaker.GetVoices()
        return [voices.Item(i).GetDescription() for i in range(voices.Count)]

    def speak(self, text: str, voice_hint: str = "Paul") -> None:
        if not text.strip():
            return
        speaker = self._client.Dispatch("SAPI.SpVoice")
        voices = speaker.GetVoices()
        for index in range(voices.Count):
            token = voices.Item(index)
            if voice_hint.casefold() in token.GetDescription().casefold():
                speaker.Voice = token
                break
        speaker.Speak(text)
