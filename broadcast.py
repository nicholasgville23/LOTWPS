"""The transmitting engine shared by BMH, the station controller and the radio GUI.

One worker thread pulls the highest-priority item from the queue, renders its
VTML script to WAV (SAPI / VoiceText assets / tones / SAME) and plays it. Alerts
and tests jump the queue; the routine cycle refills itself so the station runs
continuously until STOP TX.
"""

from __future__ import annotations

import heapq
import itertools
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from . import audio, awips, alerts as alert_mod, paths, same, script as script_mod, tz, zones
from .config import Settings, settings as global_settings
from .voices import PaulVoice, VoiceEngine
from .weather import WeatherModel, display_name, spell_callsign

STATIC_ASSET_KEYS = {
    "STATION_ID", "SHORT_ID", "LONG_ID", "EMR_STATION_ID", "SLGT_STATION_ID",
    "ADVANCE", "OFF_AIR", "PREPAREDNESS_ACTIONS",
}

STATE_STOPPED = "STOPPED"
STATE_IDLE = "IDLE"
STATE_RENDERING = "RENDERING"
STATE_PLAYING = "PLAYING"


@dataclass
class QueueItem:
    item_id: str
    title: str
    product_id: str
    script: script_mod.Script
    priority: int = 10
    source: str = "CYCLE"
    asset_key: str = ""
    created: datetime = field(default_factory=tz.utc_now)

    @property
    def seconds(self) -> float:
        try:
            return self.script.expected_seconds()
        except Exception:
            return 0.0


class BroadcastEngine:
    def __init__(
        self,
        station_id: str = "WXJ75",
        app_settings: Settings | None = None,
        on_event=None,
    ):
        self.settings = app_settings or global_settings()
        self.station_id = station_id
        self.station = self.settings.station(station_id)
        self.alerts = alert_mod.store()
        self.voices = VoiceEngine(self.settings)
        self.on_event = on_event
        self.mode = self.settings.get("broadcast.default_mode", "General")
        self.voice = self.station.get("voice", self.settings.get("voices.default", "paul"))
        self.state = STATE_STOPPED
        self.current: QueueItem | None = None
        self.ticker_text = self.settings.get("bmh.ticker", "This is a test.")
        self.listeners = self.settings.get("broadcast.listening_area.ugc", [])
        self.filter_enabled = self.settings.listening_filter()
        self.allow_uncoded = self.settings.get("broadcast.listening_area.allow_uncoded", True)

        self._queue: list[tuple[int, int, QueueItem]] = []
        self._counter = itertools.count()
        self._lock = threading.RLock()
        self._loop_item: QueueItem | None = None
        self._running = False
        self._shutdown = False
        self._skip = threading.Event()
        self._log: list[tuple[str, str]] = []
        self._history: list[dict] = []
        self._model: WeatherModel | None = None
        self._model_key: tuple[date, int] | None = None
        self._played = 0
        self._auto_cycle = True

        self._thread = threading.Thread(target=self._worker, name=f"TX-{station_id}", daemon=True)
        self._thread.start()

    # -- events ----------------------------------------------------------
    def _emit(self, kind: str, payload: dict | None = None) -> None:
        if self.on_event:
            try:
                self.on_event(kind, payload or {})
            except Exception:
                pass

    def log(self, message: str) -> None:
        stamp = tz.central_now()[0].strftime("%H:%M:%S")
        self._log.append((stamp, f"[{self.station_id}] {message}"))
        del self._log[:-400]
        self._emit("log", {"message": message, "stamp": stamp})

    def log_lines(self, count: int = 200) -> list[str]:
        return [f"{stamp} {msg}" for stamp, msg in self._log[-count:]]

    # -- model / scripts -------------------------------------------------
    def _ensure_model(self) -> WeatherModel:
        now = tz.central_now()[0]
        key = (now.date(), now.hour)
        if self._model is None or self._model_key != key:
            self._model = WeatherModel(start=now.date())
            self._model_key = key
        return self._model

    def _new_script(self, title: str, product_id: str, priority: int = 10) -> script_mod.Script:
        return script_mod.Script(
            title=title,
            product_id=product_id,
            voice=self.voice,
            station_id=self.station_id,
            priority=priority,
        )

    def _say_paragraphs(self, script: script_mod.Script, text: str, pause_ms: int = 700) -> None:
        for para in [p.strip() for p in text.split("\n\n") if p.strip()]:
            script.say(para)
            script.pause(pause_ms)

    def _asset_for(self, key: str) -> Path | None:
        paul = self.voices.get("paul")
        if not isinstance(paul, PaulVoice):
            return None
        mode = paul.mode
        if mode == "sapi":
            return None
        if mode == "auto" and key.upper() not in STATIC_ASSET_KEYS:
            return None
        return paul.asset_path(key)

    def script_for_static(self, key: str) -> QueueItem:
        model = self._ensure_model()
        text = model.static_message(key, self.station)
        override = self.settings.get(f"broadcast.static_overrides.{key.upper()}", "")
        if override:
            text = str(override)
        script = self._new_script(key, key)
        asset = None if override else self._asset_for(key)
        if asset:
            script.asset(asset, key)
        else:
            script.say(text)
        script.pause(500)
        return QueueItem(
            item_id=f"{key}-{next(self._counter)}",
            title=key,
            product_id=key,
            script=script,
            priority=12,
            source="STATIC",
            asset_key=key,
        )

    def script_for_product(self, pid: str) -> QueueItem:
        prod = awips.product(pid)
        model = self._ensure_model()
        script = self._new_script(prod.name, prod.pil, prod.priority)
        city = self.station.get("city", "Valparaiso")

        if prod.pil == "ZFPLOT":
            script.say(model.key_messages())
            script.pause(1000)
            self._say_paragraphs(script, model.radio_forecast(city, self.station, 7))
            script.say(model.climate_summary_script())
            script.pause(600)
        elif prod.pil == "AFDLOT":
            self._say_paragraphs(script, model.discussion_script())
        elif prod.pil == "HWOLOT":
            self._say_paragraphs(script, model.hazardous_outlook())
        elif prod.pil == "RWRLOT":
            self._say_paragraphs(script, model.roundup())
        elif prod.pil == "CLILOT":
            script.say(model.climate_summary_script())
            script.pause(700)
            script.say(model.summary_script(self.active_alerts()))
        elif prod.pil == "MFMLOT":
            self._say_paragraphs(script, model.marine_script())
        elif prod.pil in ("SPS", "SVS"):
            script.say(model.summary_script(self.active_alerts()))
        else:
            script.say(model.key_messages())

        if prod.pil in ("ZFPLOT", "AFDLOT", "HWOLOT", "RWRLOT", "CLILOT", "MFMLOT"):
            asset = self._asset_for(prod.pil)
            if asset:
                script = self._new_script(prod.name, prod.pil, prod.priority)
                script.asset(asset, prod.pil)

        return QueueItem(
            item_id=f"{prod.pil}-{next(self._counter)}",
            title=prod.name,
            product_id=prod.pil,
            script=script,
            priority=prod.priority,
            source="PRODUCT",
        )

    def script_for_text(self, title: str, text: str, product_id: str = "SPS", priority: int = 20) -> QueueItem:
        script = self._new_script(title, product_id, priority)
        self._say_paragraphs(script, text)
        return QueueItem(
            item_id=f"{product_id}-{next(self._counter)}",
            title=title,
            product_id=product_id,
            script=script,
            priority=priority,
            source="TEXT",
        )

    # -- queue -----------------------------------------------------------
    def enqueue(self, item: QueueItem, front: bool = False, clear_routine: bool = False) -> QueueItem:
        with self._lock:
            if clear_routine and not front:
                self._queue = [q for q in self._queue if q[2].priority >= 60]
            priority = 999 if front else item.priority
            heapq.heappush(self._queue, (-priority, next(self._counter), item))
        self.log(f"queued {item.title}")
        self._emit("queue", {"length": self.queue_length()})
        return item

    def enqueue_product(self, pid: str, front: bool = False) -> QueueItem:
        return self.enqueue(self.script_for_product(pid), front=front)

    def enqueue_static(self, key: str, front: bool = False) -> QueueItem:
        return self.enqueue(self.script_for_static(key), front=front)

    def _pop_queue(self) -> QueueItem | None:
        with self._lock:
            if self._queue:
                return heapq.heappop(self._queue)[2]
        return None

    def queue_snapshot(self) -> list[dict]:
        with self._lock:
            items = sorted(self._queue, key=lambda q: q[0])
            return [
                {
                    "id": item.item_id,
                    "title": item.title,
                    "product_id": item.product_id,
                    "priority": item.priority,
                    "source": item.source,
                    "seconds": item.seconds,
                }
                for _, _, item in items
            ]

    def queue_length(self) -> int:
        with self._lock:
            return len(self._queue)

    def clear_queue(self) -> None:
        with self._lock:
            self._queue.clear()
        self._emit("queue", {"length": 0})

    def history(self, count: int = 40) -> list[dict]:
        return list(reversed(self._history[-count:]))

    # -- transport -------------------------------------------------------
    def start(self) -> None:
        self._running = True
        self.state = STATE_IDLE
        if not self.queue_length():
            self.fill_cycle()
        self.log("START TX - broadcast loop running")
        self._emit("status", self.snapshot())

    def stop(self) -> None:
        self._running = False
        self._skip.set()
        audio.player().stop()
        self.state = STATE_STOPPED
        self.current = None
        self.log("STOP TX - broadcast loop halted")
        self._emit("status", self.snapshot())

    def restart_service(self) -> None:
        self.log("RESTART SERVICE requested")
        self.stop()
        time.sleep(0.2)
        self.clear_queue()
        self._loop_item = None
        self._running = True
        self.fill_cycle()
        self.start()

    def next_product(self) -> None:
        self._skip.set()
        audio.player().stop()
        self.log("NEXT PRODUCT - skipping current item")
        self._emit("status", self.snapshot())

    def set_mode(self, mode: str) -> None:
        if mode not in self.settings.modes():
            raise KeyError(mode)
        self.mode = mode
        self.log(f"broadcast mode set to {mode}")
        self._emit("status", self.snapshot())

    def snapshot(self) -> dict:
        return {
            "station": self.station_id,
            "state": self.state,
            "mode": self.mode,
            "running": self._running,
            "queue": self.queue_length(),
            "current": self.current.title if self.current else "",
            "ticker": self.ticker_text,
            "played": self._played,
        }

    # -- cycle -----------------------------------------------------------
    def fill_cycle(self) -> None:
        entries = self.settings.modes().get(self.mode, [])
        if not entries:
            entries = ["ADVANCE", "@AUTO_ID", "CURRENT_TIME", "@PRODUCT:ZFPLOT", "LONG_ID"]
        before = self.queue_length()
        for token in entries:
            for item in self._resolve_token(token):
                self.enqueue(item)
        added = self.queue_length() - before
        self.log(f"cycle '{self.mode}' filled with {added} product(s)")

    def _resolve_token(self, token: str) -> list[QueueItem]:
        token = token.strip()
        if not token:
            return []
        upper = token.upper()
        model = self._ensure_model()
        active = self.active_alerts()

        if upper.startswith("@PRODUCT:"):
            pid = token.split(":", 1)[1]
            try:
                return [self.script_for_product(pid)]
            except KeyError:
                self.log(f"unknown product token {token}")
                return []
        if upper == "@AUTO_ID":
            key = "SEVERE_MESSAGE" if self.mode == "Severe Weather" else "STATION_ID"
            return [self.script_for_static(key)]
        if upper == "@AUTO_SEVERE_ID":
            key = "SEVERE_MESSAGE" if active else "STATION_ID"
            return [self.script_for_static(key)]
        if upper == "@ACTIVE_ALERTS":
            return [self.script_for_text("Active Alerts", model.summary_script(active), "SPS", 40)]
        if upper == "@SEVERE_DYNAMIC":
            return [self.script_for_text("Severe Weather Summary", model.severe_dynamic(active), "SPS", 45)]
        if upper == "@NEW_CON_ALERTS":
            recent = [a for a in self.alerts.newest(8) if a.status in ("NEW", "CON")]
            return [self.script_for_text("New/Continued Alerts", model.summary_script(recent), "SPS", 40)]
        if upper == "@CAN_EXP_ALERTS":
            expired = self.alerts.cancelled() + self.alerts.expiring(20)
            text = (
                model.summary_script(expired)
                if expired
                else "There are no cancelled or expiring alerts at this time."
            )
            return [self.script_for_text("Cancelled/Expiring Alerts", text, "SPS", 40)]
        try:
            return [self.script_for_static(upper)]
        except Exception:
            self.log(f"unresolved cycle entry {token}")
            return []

    # -- alerts ----------------------------------------------------------
    def active_alerts(self) -> list:
        return self.alerts.filtered(
            self.listeners, self.filter_enabled, self.allow_uncoded
        )

    def _station_callsign(self) -> str:
        return f"{self.station_id}/NWS"

    def send_same_alert(
        self,
        event: str,
        ugc: list[str] | None = None,
        message: str = "",
        duration_min: int = 45,
        interrupt: bool = True,
        custom_headline: str = "",
    ):
        ugc = ugc or self.station.get("ugc", ["INZ001", "INZ002"])
        headline = custom_headline or f"{event} for {zones.describe_area(ugc)}"
        alert = self.alerts.issue(
            event,
            ugc,
            headline=headline,
            description=message or headline,
            instruction="",
            duration_min=duration_min,
            purge_min=min(60, duration_min),
            callsign=self._station_callsign(),
        )
        item = self.alert_item(alert)
        if interrupt:
            self.clear_queue()
            self.enqueue(item, front=True)
            self._skip.set()
            audio.player().stop()
        else:
            self.enqueue(item, front=True)
        self.log(f"SAME ALERT sent: {event} {alert.same_header}")
        self._emit("alert", {"alert": alert.to_dict()})
        return alert

    def alert_item(self, alert) -> QueueItem:
        script = script_mod.alert_script(
            alert,
            self.station,
            voice=self.voice,
            tone_seconds=float(self.settings.get("audio.tone_seconds", 8.0)),
        )
        self._ensure_model()
        return QueueItem(
            item_id=f"EAS-{alert.alert_id}",
            title=f"EAS {alert.event}",
            product_id=alert.prod_id,
            script=script,
            priority=100 if alert.tier in ("Emergency", "Warning") else 60,
            source="ALERT",
        )

    def read_alert(self, alert, front: bool = True) -> QueueItem:
        alert.ensure_header()
        item = self.alert_item(alert)
        self.enqueue(item, front=front)
        return item

    def retone(self, alert) -> None:
        alert.ensure_header()
        script = self._new_script("SAME Retone", alert.prod_id, 95)
        for _ in range(3):
            script.same_header(alert.same_header)
            script.pause(900)
        script.tone(float(self.settings.get("audio.tone_seconds", 8.0)))
        item = QueueItem(
            item_id=f"RETONE-{next(self._counter)}",
            title="SAME Retone",
            product_id=alert.prod_id,
            script=script,
            priority=95,
            source="ALERT",
        )
        self.enqueue(item, front=True)
        self._skip.set()
        audio.player().stop()
        self.log(f"SAME retone for {alert.alert_id}")

    def tone_only(self, seconds: float | None = None) -> None:
        seconds = seconds or float(self.settings.get("audio.tone_seconds", 8.0))
        script = self._new_script("1050 Hz Tone", "TONE", 95)
        script.tone(seconds)
        self.enqueue(
            QueueItem(
                f"TONE-{next(self._counter)}", "1050 Hz Tone", "TONE", script, 95, "ALERT"
            ),
            front=True,
        )
        self._skip.set()
        audio.player().stop()
        self.log("1050 Hz tone transmitted")

    def silent_interrupt(self) -> None:
        self.clear_queue()
        self._loop_item = None
        audio.player().stop()
        self.log("SILENT INTERRUPT - queue cleared, transmitter muted")
        self._emit("status", self.snapshot())

    def send_test(self, kind: str = "Required Weekly Test") -> None:
        script = script_mod.test_script(
            self.station,
            event=kind,
            voice=self.voice,
            tone_seconds=float(self.settings.get("audio.tone_seconds", 8.0)),
        )
        item = QueueItem(
            item_id=f"TEST-{next(self._counter)}",
            title=kind,
            product_id="RWT" if "Weekly" in kind else "RMT",
            script=script,
            priority=70,
            source="TEST",
        )
        self.clear_queue()
        self.enqueue(item, front=True)
        self._skip.set()
        audio.player().stop()
        self.alerts.issue(
            kind,
            self.station.get("ugc", ["INZ001", "INZ002"]),
            headline=f"{kind} for {self.station.get('coverage', 'the listening area')}",
            duration_min=15,
            purge_min=15,
            callsign=self._station_callsign(),
        )
        self.log(f"test transmitted: {kind}")

    def transmit(self, hazard: str | None, ticker: str) -> None:
        """BMH network TRANSMIT: refresh the scroll and send a hazard if selected."""
        self.ticker_text = ticker.strip() or self.ticker_text
        self._emit("ticker", {"text": self.ticker_text})
        if hazard:
            self.send_same_alert(
                hazard,
                message=ticker.strip(),
                custom_headline=f"{hazard} for the WXJ75 listening area",
            )
            self.log(f"BMH TRANSMIT with hazard {hazard}")
        else:
            self.log("BMH TRANSMIT periodic scroll update")
            self.enqueue(
                self.script_for_text("Periodic Scroll", self.ticker_text, "SPS", 15)
            )

    def broadcast_test_wednesday(self) -> None:
        now, _ = tz.central_now()
        if now.weekday() != 2:
            self.log("Required Weekly Test skipped - not Wednesday")
            return
        if 11 <= now.hour < 12:
            self.send_test("Required Weekly Test")
        else:
            self.log("Required Weekly Test scheduled window is 11 AM to noon")

    # -- looping ---------------------------------------------------------
    def loop_product(self, pid: str) -> QueueItem:
        item = self.script_for_product(pid)
        self._loop_item = item
        self.enqueue(item, front=True)
        self.log(f"LOOP PRODUCT {pid}")
        return item

    def loop_item(self, item: QueueItem) -> None:
        self._loop_item = item
        self.enqueue(item, front=True)
        self.log(f"LOOP {item.title}")

    def stop_loop(self) -> None:
        self._loop_item = None
        self.log("loop stopped")

    def read_now(self, pid: str) -> QueueItem:
        item = self.script_for_product(pid)
        self.enqueue(item, front=True)
        self._skip.set()
        audio.player().stop()
        return item

    # -- worker ----------------------------------------------------------
    def _worker(self) -> None:
        while not self._shutdown:
            if not self._running:
                time.sleep(0.15)
                continue
            item = self._pop_queue()
            if item is None:
                if self._auto_cycle:
                    self.fill_cycle()
                    if self.queue_length() == 0:
                        time.sleep(0.5)
                else:
                    time.sleep(0.3)
                continue
            try:
                self._run_item(item)
            except Exception as exc:  # keep the transmitter alive
                self.log(f"playback error: {exc}")
                time.sleep(0.2)

    def _run_item(self, item: QueueItem) -> None:
        self._skip.clear()
        self.current = item
        self.state = STATE_RENDERING
        self._emit("status", self.snapshot())
        try:
            path = item.script.render(self.voices)
        except Exception as exc:
            self.log(f"render failed for {item.title}: {exc}")
            self.current = None
            self.state = STATE_IDLE
            return
        if self._skip.is_set() or not self._running:
            self.current = None
            self.state = STATE_IDLE
            return
        self.state = STATE_PLAYING
        self._emit("status", self.snapshot())
        self._emit("playing", {"title": item.title, "path": str(path), "seconds": item.seconds})
        audio.player().play(path)
        self._played += 1
        self._history.append(
            {
                "title": item.title,
                "product_id": item.product_id,
                "finished": tz.central_now()[0].strftime("%H:%M:%S"),
                "source": item.source,
            }
        )
        del self._history[:-200]
        self.current = None
        self.state = STATE_IDLE
        self._emit("status", self.snapshot())
        if self._loop_item and self._loop_item.item_id == item.item_id:
            self.enqueue(item)
        self._emit("queue", {"length": self.queue_length()})

    def shutdown(self, timeout: float = 2.0) -> None:
        self.stop()
        self._shutdown = True
        audio.player().stop()
        self._thread.join(timeout=timeout)
