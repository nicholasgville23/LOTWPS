"""Local-only broadcast queue engine; playback is supplied by an adapter."""
from __future__ import annotations
from collections.abc import Callable
from threading import Event, RLock, Thread
from time import sleep
from .models import WeatherProduct

class BroadcastQueue:
    """Priority queue with explicit manual start/stop and no network transmitter."""
    def __init__(self, playback: Callable[[WeatherProduct], None] | None = None) -> None:
        self._items: list[tuple[int, int, WeatherProduct]] = []
        self._sequence = 0
        self._lock = RLock()
        self._stop = Event()
        self._thread: Thread | None = None
        self._playback = playback or (lambda product: None)
        self.current: WeatherProduct | None = None

    def enqueue(self, product: WeatherProduct) -> None:
        if not product.test_only:
            raise ValueError("only local test products may enter this queue")
        with self._lock:
            self._sequence += 1
            self._items.append((int(product.priority), self._sequence, product))
            self._items.sort(key=lambda item: (item[0], item[1]))

    def snapshot(self) -> list[WeatherProduct]:
        with self._lock:
            return [item[2] for item in self._items]

    def start(self) -> bool:
        with self._lock:
            if self._thread and self._thread.is_alive():
                return False
            self._stop.clear()
            self._thread = Thread(target=self._run, name="bmh-local-queue", daemon=True)
            self._thread.start()
            return True

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread and thread.is_alive():
            thread.join(timeout=timeout)
        self.current = None

    def _run(self) -> None:
        while not self._stop.is_set():
            with self._lock:
                product = self._items.pop(0)[2] if self._items else None
            if product is None:
                sleep(0.1)
                continue
            self.current = product
            try:
                self._playback(product)
            finally:
                self.current = None
