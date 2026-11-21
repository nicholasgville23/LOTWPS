"""Adapter for standalone VoiceText Paul command-line renderer.

Protocol documented by WeatherRadioSuite: write UTF-8 text to input1.txt beside
voicetext_paul.exe, run the executable without arguments, then consume output.wav.
The adapter serializes access to those fixed files and normalizes WAV output.
"""
from __future__ import annotations

import os
import subprocess
import threading
from contextlib import contextmanager
from pathlib import Path

from . import audio


class VoiceTextPaulCLI:
    """VoiceText Paul renderer using the standalone voicetext_paul.exe binary."""

    _thread_lock = threading.RLock()

    def __init__(self, executable: str | Path, timeout: int = 120) -> None:
        self.executable = Path(executable).expanduser()
        self.timeout = int(timeout)

    @property
    def available(self) -> bool:
        return self.executable.is_file()

    @contextmanager
    def _exclusive_lock(self, workdir: Path):
        with self._thread_lock:
            lock_path = workdir / ".voicetext_paul.lock"
            handle = lock_path.open("a+b")
            locked = False
            lock_module = None
            try:
                try:
                    import msvcrt as lock_module
                except ImportError:
                    lock_module = None
                if lock_module is not None:
                    handle.seek(0, os.SEEK_END)
                    if handle.tell() == 0:
                        handle.write(b"\\0")
                        handle.flush()
                    handle.seek(0)
                    lock_module.locking(handle.fileno(), lock_module.LK_LOCK, 1)
                    locked = True
                yield
            finally:
                if locked and lock_module is not None:
                    handle.seek(0)
                    lock_module.locking(handle.fileno(), lock_module.LK_UNLCK, 1)
                handle.close()

    def render(self, text: str, destination: str | Path) -> Path:
        """Synthesize text and write a 16 kHz mono, 16-bit WAV."""
        text = str(text).strip()
        if not text:
            raise ValueError("VoiceText Paul cannot render empty text")
        if not self.available:
            raise FileNotFoundError(f"VoiceText executable not found: {self.executable}")

        executable = self.executable.resolve()
        workdir = executable.parent
        input_path = workdir / "input1.txt"
        output_path = workdir / "output.wav"
        destination = Path(destination)
        destination.parent.mkdir(parents=True, exist_ok=True)

        with self._exclusive_lock(workdir):
            output_path.unlink(missing_ok=True)
            input_path.write_text(text, encoding="utf-8")
            try:
                result = subprocess.run(
                    [str(executable)],
                    cwd=str(workdir),
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                    check=False,
                )
            except subprocess.TimeoutExpired as exc:
                raise TimeoutError(
                    f"VoiceText Paul exceeded the {self.timeout}-second timeout"
                ) from exc

            detail = (result.stderr or result.stdout or "").strip()
            if result.returncode != 0:
                raise RuntimeError(
                    f"VoiceText Paul exited with code {result.returncode}: {detail}"
                )
            if not output_path.is_file() or output_path.stat().st_size < 64:
                raise RuntimeError(
                    "VoiceText Paul did not create output.wav. "
                    f"Check the executable and companion files. {detail}"
                )

            pcm, source_rate = audio.read_wav(output_path)
            if source_rate <= 0:
                raise RuntimeError("VoiceText Paul produced an invalid WAV sample rate")
            pcm = audio.resample(pcm, source_rate, audio.RATE)
            audio.write_wav(destination, pcm, audio.RATE)

        if not destination.is_file() or destination.stat().st_size < 64:
            raise RuntimeError("VoiceText Paul output normalization failed")
        return destination
