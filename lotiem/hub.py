"""LOTIEM - Chicago Illinois Iowa Environmental Mesonet distribution hub.

LOTIEM sits between the LOTWPS text workstation / BMH network and the outside
world. It accepts products on the JSON bus (file transport by default, TCP on
192.168.10.144:6000 when the daemon is running), fans them out to the configured
routes (BMH, WWA, local officials, public, IEMBOT, email, websites) and keeps a
replayable log under ``var/lotiem``.
"""

from __future__ import annotations

import json
import threading
import time
from datetime import datetime
from pathlib import Path

from lotwps import bus as bus_mod, paths, tz
from lotwps.config import Settings, settings as global_settings

ROOT = paths.VAR / "lotiem"
ROUTES_DIR = ROOT / "routes"
LOG_FILE = ROOT / "messages.jsonl"
STATE_FILE = ROOT / "state.json"

DEFAULT_ROUTES = ["BMH", "WWA", "LOCAL_OFFICIALS", "PUBLIC", "IEMBOT", "EMAIL", "WEBSITES"]


class Hub:
    def __init__(self, app_settings: Settings | None = None) -> None:
        self.settings = app_settings or global_settings()
        self.root = ROOT
        self.root.mkdir(parents=True, exist_ok=True)
        ROUTES_DIR.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._counts: dict[str, int] = {route: 0 for route in DEFAULT_ROUTES}
        self._total = 0
        self._started = tz.utc_now()
        self.bus = bus_mod.Bus("LOTIEM", self.settings)
        self._load_counts()

    # -- state -----------------------------------------------------------
    def _load_counts(self) -> None:
        if not STATE_FILE.exists():
            return
        try:
            data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        self._total = int(data.get("total", 0))
        for route, count in (data.get("counts") or {}).items():
            self._counts[route] = int(count)

    def _save_counts(self) -> None:
        payload = {
            "total": self._total,
            "counts": self._counts,
            "updated": tz.iso(tz.utc_now()),
            "started": tz.iso(self._started),
        }
        tmp = STATE_FILE.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        tmp.replace(STATE_FILE)

    # -- routing ---------------------------------------------------------
    def enabled_routes(self) -> list[str]:
        configured = self.settings.get("lotiem.routes", {}) or {}
        return [route for route in DEFAULT_ROUTES if configured.get(route, True)]

    def routes_for(self, message: dict) -> list[str]:
        payload = message.get("payload", {}) or {}
        options = payload.get("options", {}) or {}
        requested = options.get("routes") or payload.get("routes")
        enabled = self.enabled_routes()
        if requested:
            return [route for route in requested if route in DEFAULT_ROUTES]
        return enabled

    def dispatch(self, message: dict) -> list[str]:
        routes = self.routes_for(message)
        payload = message.get("payload", {}) or {}
        product = payload.get("product", {}) or {}
        text = payload.get("text", "")
        stamp = tz.central_now()[0].strftime("%Y%m%d-%H%M%S")
        core = product.get("pil") or product.get("code") or "SPS"
        with self._lock:
            self._total += 1
            seq = self._total
            for route in routes:
                folder = ROUTES_DIR / route
                folder.mkdir(parents=True, exist_ok=True)
                out = folder / f"{stamp}-{seq:05d}-{core}.json"
                out.write_text(
                    json.dumps(
                        {
                            "seq": message.get("seq"),
                            "route": route,
                            "subscriber": payload.get("subscribers", {}).get(route, ""),
                            "from": message.get("from", ""),
                            "topic": message.get("topic", ""),
                            "subject": payload.get("subject") or product.get("name", ""),
                            "product": product,
                            "ugc": payload.get("ugc", []),
                            "text": text,
                            "received": tz.iso(tz.utc_now()),
                        },
                        indent=2,
                    ),
                    encoding="utf-8",
                )
                self._counts[route] = self._counts.get(route, 0) + 1
            self._append_log(message, routes, text)
            self._save_counts()
        return routes

    def _append_log(self, message: dict, routes: list[str], text: str) -> None:
        payload = message.get("payload", {}) or {}
        product = payload.get("product", {}) or {}
        record = {
            "seq": message.get("seq"),
            "ts": message.get("ts") or tz.iso(tz.utc_now()),
            "from": message.get("from", ""),
            "to": message.get("to", ""),
            "topic": message.get("topic", ""),
            "product": product.get("pil") or product.get("code", ""),
            "name": product.get("name", ""),
            "subject": payload.get("subject", ""),
            "routes": routes,
            "characters": len(text),
            "preview": text[:160].replace("\n", " "),
        }
        with LOG_FILE.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record) + "\n")

    # -- consumption -----------------------------------------------------
    def drain_bus(self) -> list[dict]:
        out: list[dict] = []
        for message in self.bus.poll():
            if message.get("to") not in ("LOTIEM", "ALL", "BMH", "WWA"):
                continue
            if message.get("from") == "LOTIEM":
                continue
            self.dispatch(message)
            out.append(message)
        return out

    def recent(self, limit: int = 40) -> list[dict]:
        if not LOG_FILE.exists():
            return []
        lines = LOG_FILE.read_text(encoding="utf-8", errors="ignore").splitlines()
        records = []
        for line in lines[-limit:]:
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return list(reversed(records))

    def stats(self) -> dict:
        with self._lock:
            return {
                "total": self._total,
                "routes": dict(self._counts),
                "started": tz.iso(self._started),
                "enabled": self.enabled_routes(),
                "host": self.settings.get("lotiem.host"),
                "port": self.settings.get("lotiem.port"),
                "transport": self.settings.get("lotiem.transport"),
            }

    def summary(self) -> str:
        stats = self.stats()
        bits = [f"{route}: {count}" for route, count in stats["routes"].items() if count]
        return (
            f"LOTIEM {stats['host']}:{stats['port']}  |  {stats['total']} messages  |  "
            + (", ".join(bits) if bits else "no dispatches yet")
        )

    def serve(self, poll_seconds: float = 1.0, max_cycles: int | None = None) -> None:
        """Watch the file bus and fan out messages until interrupted."""
        cycles = 0
        while max_cycles is None or cycles < max_cycles:
            try:
                for message in self.drain_bus():
                    routes = self.routes_for(message)
                    print(
                        f"{tz.central_now()[0]:%H:%M:%S} LOTIEM dispatched "
                        f"{message.get('topic')} -> {', '.join(routes)}"
                    )
            except KeyboardInterrupt:
                break
            except Exception as exc:
                print(f"LOTIEM error: {exc}")
            cycles += 1
            if max_cycles is not None and cycles >= max_cycles:
                break
            time.sleep(poll_seconds)


def main() -> None:
    hub = Hub()
    print(hub.summary())
    hub.serve()


if __name__ == "__main__":
    main()
