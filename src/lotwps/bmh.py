"""Local BMH queue and station reachability checks.

This first version deliberately has no RF transmitter, SAME encoder, or EAS tone
generator. The network check only opens a TCP connection and sends no payload.
"""

from __future__ import annotations

import socket
from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True, slots=True)
class QueuedMessage:
    station_id: str
    hazard: str
    text: str
    created_at: str


class LocalBMHQueue:
    def __init__(self) -> None:
        self._items: list[QueuedMessage] = []

    def add(self, station_id: str, hazard: str, text: str) -> QueuedMessage:
        item = QueuedMessage(
            station_id=station_id,
            hazard=hazard,
            text=text,
            created_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
        self._items.append(item)
        return item

    def items(self) -> tuple[QueuedMessage, ...]:
        return tuple(self._items)

    def clear(self) -> None:
        self._items.clear()


def check_tcp_reachability(host: str, port: int, timeout: float = 2.0) -> tuple[bool, str]:
    """Check whether a configured TCP endpoint accepts a connection; send nothing."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True, f"TCP connection accepted by {host}:{port}; no data was sent."
    except (OSError, TimeoutError) as exc:
        return False, f"Could not connect to {host}:{port}: {exc}"
