"""Speak with an installed Windows SAPI5 voice via pyttsx3.

VoiceText Paul is selectable here only when the Paul SAPI voice is registered.
A standalone voicetext_paul.exe is not a pyttsx3 voice; configure
voices.paul.cli_exe in config/settings.json to use that executable.
"""
from __future__ import annotations

import argparse
import sys


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--voice", default="paul", help="Substring of the SAPI voice name or ID")
    parser.add_argument(
        "--text",
        default="This is NOAA Weather Radio. This is a VoiceText Paul speech test.",
    )
    parser.add_argument("--list", action="store_true", help="List installed SAPI5 voices and exit")
    args = parser.parse_args()

    try:
        import pyttsx3
    except ImportError:
        print("Install pyttsx3 with: py -3.12 -m pip install pyttsx3", file=sys.stderr)
        return 2

    engine = pyttsx3.init(driverName="sapi5")
    voices = engine.getProperty("voices") or []
    for voice in voices:
        print(f"{voice.name} [{voice.id}]")

    if args.list:
        return 0

    wanted = args.voice.casefold()
    selected = next(
        (v for v in voices if wanted in f"{v.name or ''} {v.id or ''}".casefold()),
        None,
    )
    if selected is None:
        print(
            f"No SAPI5 voice matched {args.voice!r}. A standalone voicetext_paul.exe "
            "is not automatically a pyttsx3 voice. Configure voices.paul.cli_exe "
            "in config/settings.json to use the executable adapter.",
            file=sys.stderr,
        )
        return 3

    engine.setProperty("voice", selected.id)
    engine.say(args.text)
    engine.runAndWait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
