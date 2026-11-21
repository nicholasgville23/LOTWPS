"""LOTIEM TCP daemon: newline-delimited JSON on 10.0.0.117:28894.

The file bus is the default transport, but the LOTIEM daemon also listens on
TCP so other machines can post the same JSON messages. Every accepted message
is routed through :class:`lotiem.hub.Hub`.
"""

from __future__ import annotations

import json
import socket
import socketserver
import threading
import time

from lotwps import paths, tz
from lotwps.config import settings as global_settings

from .hub import Hub

LOG = paths.LOGS / "lotiem-server.log"


def _log(line: str) -> None:
    stamp = tz.utc_now().strftime("%Y-%m-%d %H:%M:%SZ")
    with LOG.open("a", encoding="utf-8") as handle:
        handle.write(f"{stamp} {line}\n")


class _Handler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server: "LOTIEMServer" = self.server.lotiem  # type: ignore[attr-defined]
        try:
            raw = self.rfile.readline(1_048_576)
        except OSError:
            return
        if not raw:
            return
        try:
            message = json.loads(raw.decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            self._reply({"status": "error", "error": f"bad json: {exc}"})
            return
        routes = server.hub.dispatch(message)
        server.accepted += 1
        _log(
            f"accepted {message.get('topic', '?')} from {message.get('from', '?')} "
            f"-> {','.join(routes) or 'no routes'}"
        )
        self._reply(
            {
                "status": "ok",
                "seq": message.get("seq"),
                "routes": routes,
                "received": tz.iso(tz.utc_now()),
            }
        )

    def _reply(self, payload: dict) -> None:
        try:
            self.wfile.write(json.dumps(payload).encode("utf-8") + b"\n")
            self.wfile.flush()
        except OSError:
            pass


class _Server(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class LOTIEMServer:
    def __init__(self, host: str | None = None, port: int | None = None) -> None:
        settings = global_settings()
        self.host = host or settings.get("lotiem.bind_host", "0.0.0.0")
        self.port = int(port or settings.get("lotiem.port", 28894))
        self.hub = Hub(settings)
        self.accepted = 0
        self._server = _Server((self.host, self.port), _Handler)
        self._server.lotiem = self  # type: ignore[attr-defined]
        self._thread: threading.Thread | None = None

    def start_background(self) -> None:
        self._thread = threading.Thread(
            target=self._server.serve_forever, name="LOTIEM-TCP", daemon=True
        )
        self._thread.start()

    def serve_forever(self) -> None:
        print(f"LOTIEM TCP daemon listening on {self.host}:{self.port}")
        _log(f"listening on {self.host}:{self.port}")
        try:
            self._server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            self.shutdown()

    def shutdown(self) -> None:
        try:
            self._server.shutdown()
        except Exception:
            pass
        try:
            self._server.server_close()
        except Exception:
            pass
        _log(f"shutdown after {self.accepted} messages")

    def wait(self, seconds: float) -> None:
        time.sleep(seconds)


def port_available(host: str = "127.0.0.1", port: int = 28894) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.3):
            return False
    except OSError:
        return True


def main() -> None:
    LOTIEMServer().serve_forever()


if __name__ == "__main__":
    main()
