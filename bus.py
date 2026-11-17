"""LOTWPS -> LOTIEM message bus.

A JSON file bus (``var/bus``) gives every process on the box a shared inbox with
no port conflicts; the optional TCP transport speaks the same JSON to
``IP:port`` (192.168.10.144:6000) when LOTIEM is running as a daemon.
"""

from __future__ import annotations

import json
import os
import socket
import threading
import time
import uuid
from pathlib import Path

from . import paths, tz
from .config import Settings, settings as global_settings

BUS_KEEP = 600


def _seq() -> int:
    return int(time.time() * 1_000_000)


class Bus:
    def __init__(self, role: str = "LOTWPS", app_settings: Settings | None = None):
        self.role = role
        self.settings = app_settings or global_settings()
        self.root = paths.BUS
        self.root.mkdir(parents=True, exist_ok=True)
        self.transport = self.settings.get("lotiem.transport", "file")
        self.host = self.settings.get("lotiem.host", "127.0.0.1")
        self.port = int(self.settings.get("lotiem.port", 6000))
        self._lock = threading.RLock()
        self._cursor_file = paths.STATE / f"bus-{role}.cursor"

    # -- publishing ------------------------------------------------------
    def publish(
        self,
        topic: str,
        payload: dict,
        target: str = "LOTIEM",
        source: str | None = None,
    ) -> dict:
        message = {
            "seq": _seq(),
            "ts": tz.iso(tz.utc_now()),
            "topic": topic,
            "from": source or self.role,
            "to": target,
            "payload": payload,
        }
        if not self._send_tcp(message):
            self._write_file(message)
        return message

    def _write_file(self, message: dict) -> Path:
        token = uuid.uuid4().hex[:8]
        path = self.root / f"{message['seq']:012d}-{token}.json"
        tmp = path.with_suffix(".tmp")
        with self._lock:
            tmp.write_text(json.dumps(message, indent=2), encoding="utf-8")
            tmp.replace(path)
        self._prune()
        return path

    def _send_tcp(self, message: dict) -> bool:
        if self.transport != "tcp":
            return False
        try:
            with socket.create_connection((self.host, self.port), timeout=1.0) as sock:
                sock.sendall(json.dumps(message).encode("utf-8") + b"\n")
                sock.settimeout(1.0)
                data = sock.recv(4096)
                return bool(data)
        except OSError:
            return False

    def _prune(self) -> None:
        files = sorted(self.root.glob("*.json"))
        for stale in files[:-BUS_KEEP]:
            try:
                stale.unlink()
            except OSError:
                pass

    # -- consuming -------------------------------------------------------
    def poll(self, advance: bool = True, topics: list[str] | None = None) -> list[dict]:
        cursor = self.cursor()
        out: list[dict] = []
        for path in sorted(self.root.glob("*.json")):
            try:
                seq = int(path.name.split("-", 1)[0])
            except (ValueError, IndexError):
                continue
            if seq <= cursor:
                continue
            try:
                message = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            if topics and message.get("topic") not in topics:
                continue
            out.append(message)
        if out and advance:
            self.set_cursor(max(m["seq"] for m in out))
        return out

    def cursor(self) -> int:
        try:
            return int(self._cursor_file.read_text().strip())
        except (OSError, ValueError):
            return 0

    def set_cursor(self, value: int) -> None:
        try:
            self._cursor_file.write_text(str(value))
        except OSError:
            pass

    def pending(self) -> int:
        cursor = self.cursor()
        count = 0
        for path in self.root.glob("*.json"):
            try:
                if int(path.name.split("-", 1)[0]) > cursor:
                    count += 1
            except (ValueError, IndexError):
                continue
        return count

    # -- convenience -----------------------------------------------------
    def publish_product(
        self,
        text: str,
        product: dict,
        ugc: list[str],
        options: dict | None = None,
    ) -> dict:
        payload = {
            "product": product,
            "ugc": ugc,
            "text": text,
            "options": options or {},
            "author": "LOT",
        }
        return self.publish("product", payload)

    def publish_alert(self, alert_dict: dict) -> dict:
        return self.publish("alert", alert_dict)

    def publish_status(self, payload: dict, source: str) -> dict:
        return self.publish("status", payload, target="ALL", source=source)

    def drain(self, topics: list[str] | None = None) -> list[dict]:
        return self.poll(advance=True, topics=topics)


def save_product_file(text: str, awips_id: str, stamp: str | None = None) -> Path:
    stamp = stamp or tz.central_now()[0].strftime("%Y%m%d-%H%M%S")
    path = paths.PRODUCTS_OUT / f"{awips_id}-{stamp}.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def prune_exports(keep: int = 200) -> int:
    removed = 0
    for folder in (paths.PRODUCTS_OUT, paths.EXPORTS):
        files = sorted(folder.glob("*"), key=lambda p: p.stat().st_mtime, reverse=True)
        for stale in files[keep:]:
            try:
                if stale.is_file():
                    stale.unlink()
                    removed += 1
            except OSError:
                pass
    return removed


def tail_bus(limit: int = 20) -> list[dict]:
    files = sorted(paths.BUS.glob("*.json"))[-limit:]
    messages = []
    for path in files:
        try:
            messages.append(json.loads(path.read_text(encoding="utf-8")))
        except (OSError, json.JSONDecodeError):
            continue
    return messages
