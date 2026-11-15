"""Manually controlled local audio briefing loop."""

from __future__ import annotations

import threading
from collections.abc import Callable
from typing import Any

from .models import Station
from .nws import NWSClient
from .speech import SpeechEngine


class BroadcastLoop:
    def __init__(
        self,
        client: NWSClient,
        speech: SpeechEngine,
        on_status: Callable[[str], None],
        interval_seconds: int = 900,
    ) -> None:
        self.client = client
        self.speech = speech
        self.on_status = on_status
        self.interval_seconds = max(60, int(interval_seconds))
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    @property
    def running(self) -> bool:
        return self._thread is not None and self._thread.is_alive()

    def start(self, station: Station, voice: str) -> None:
        if self.running:
            raise RuntimeError("The broadcast loop is already running")
        self._stop.clear()
        self._thread = threading.Thread(
            target=self._run,
            args=(station, voice),
            name=f"LOTWPS-{station.station_id}-audio-loop",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2.0)
        self.on_status("Local audio briefing loop stopped.")

    def _run(self, station: Station, voice: str) -> None:
        from .workstation import build_broadcast_script

        cycle_number = 0
        while not self._stop.is_set():
            try:
                snapshot: dict[str, Any] = self.client.fetch_station(station)
                script = build_broadcast_script(
                    station,
                    snapshot.get("alerts", []),
                    snapshot.get("forecast_periods", []),
                    cycle_number,
                )
                status = self.speech.speak(script, voice)
                self.on_status(f"{station.station_id}: {status}")
            except Exception as exc:
                self.on_status(f"{station.station_id}: local audio loop error: {exc}")
            cycle_number += 1
            self._stop.wait(self.interval_seconds)
