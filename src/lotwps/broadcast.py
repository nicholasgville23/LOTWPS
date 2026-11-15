from __future__ import annotations

import json
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Callable


@dataclass(slots=True)
class QueueItem:
    item_id: str
    product_id: str
    title: str
    text: str
    audio_path: str | None = None
    station_id: str = "KLOT"
    status: str = "QUEUED"
    created_at: str = ""

    @classmethod
    def create(cls, product_id: str, title: str, text: str, audio_path: str | None = None, station_id: str = "KLOT"):
        return cls(str(uuid.uuid4()), product_id, title, text, audio_path, station_id, "QUEUED", datetime.now().astimezone().isoformat())


class LocalQueue:
    def __init__(self):
        self._items: list[QueueItem] = []
        self._lock = threading.Lock()

    def add(self, item: QueueItem) -> None:
        with self._lock:
            self._items.append(item)

    def items(self) -> list[QueueItem]:
        with self._lock:
            return list(self._items)

    def next_item(self) -> QueueItem | None:
        with self._lock:
            return next((item for item in self._items if item.status == "QUEUED"), None)

    def set_status(self, item_id: str, status: str) -> None:
        with self._lock:
            for item in self._items:
                if item.item_id == item_id:
                    item.status = status
                    break


class BroadcastLoop:
    """Manual local playout loop. No RF transmitter or EAS modem is used."""

    def __init__(self, queue: LocalQueue, play: Callable[[QueueItem], None], idle_seconds: float = 1.0):
        self.queue, self.play, self.idle_seconds = queue, play, idle_seconds
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.running = False

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="LOTWPS-local-playout")
        self.running = True
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=3)
        self.running = False

    def _run(self) -> None:
        while not self._stop.is_set():
            item = self.queue.next_item()
            if item is None:
                self._stop.wait(self.idle_seconds)
                continue
            self.queue.set_status(item.item_id, "PLAYING")
            try:
                self.play(item)
                self.queue.set_status(item.item_id, "PLAYED")
            except Exception:
                self.queue.set_status(item.item_id, "ERROR")
                self._stop.wait(self.idle_seconds)
        self.running = False


def export_queue(path: str | Path, queue: LocalQueue) -> Path:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps([asdict(item) for item in queue.items()], indent=2), encoding="utf-8")
    return output
