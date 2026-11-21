"""NWR-1: NOAA Weather Radio receiver and broadcast console for WXJ75 / KBB58.

Runs the continuous broadcast loop, previews the EAS details channel, and sends
SAME alerts, RWT/RMT tests and 1050 Hz tones through the shared engine.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lotwps import alerts as alert_mod, appkit, audio, awips, broadcast, same, tz, ui, zones

PRODUCT_BUTTONS = [
    ("FORECAST", "ZFPLOT"),
    ("ZONE FORECAST", "ZFPLOT"),
    ("OBSERVATIONS", "RWRLOT"),
    ("HAZARD OUTLOOK", "HWOLOT"),
    ("CLIMATE", "CLILOT"),
    ("MARINE", "MFMLOT"),
    ("DISCUSSION", "AFDLOT"),
]

STATIC_BUTTONS = [
    ("CURRENT TIME", "CURRENT_TIME"),
    ("STATION ID", "STATION_ID"),
    ("LONG ID", "LONG_ID"),
    ("SHORT ID", "SHORT_ID"),
    ("PREPAREDNESS", "PREPAREDNESS_ACTIONS"),
    ("SEVERE MESSAGE", "SEVERE_MESSAGE"),
]

ALERT_EVENTS = [
    "Tornado Warning",
    "Severe Thunderstorm Warning",
    "Flash Flood Warning",
    "Special Weather Statement",
    "Extreme Wind Warning",
    "Tornado Watch",
    "Severe Thunderstorm Watch",
]


class RadioConsole:
    def __init__(self) -> None:
        self.root = appkit.boot(
            "NWR-1  NOAA Weather Radio  |  KLOT Broadcast Console",
            (1280, 840),
            (1100, 720),
        )
        self.settings = __import__("lotwps.config", fromlist=["settings"]).settings()
        self.store = alert_mod.store()
        self.station_id = "WXJ75"
        self.station = self.settings.station(self.station_id)
        self.engine = broadcast.BroadcastEngine(
            self.station_id, self.settings, on_event=self._on_event
        )
        self.engine.alerts = self.store
        self.engine.ticker_text = self.settings.get("bmh.ticker", "This is a test.")

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh_alerts()
        self._tick_job = None
        self._closed = False
        self._tick()
        self.log("NWR-1 console online - transmitter idle")
        self.log(f"Voices: {self.engine.voices.describe()}")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        root = self.root

        header = ttk.Frame(root, style="Panel.TFrame", padding=(12, 8))
        header.pack(fill="x")
        title = ttk.Frame(header, style="Panel.TFrame")
        title.pack(side="left")
        ttk.Label(title, text="NOAA WEATHER RADIO", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title,
            text="National Weather Service  |  Chicago/Romeoville, IL  |  "
                 "all hazards 24 hours a day",
            style="Muted.TLabel",
        ).pack(anchor="w")
        self.clock_var = tk.StringVar(value="--:--:--")
        ttk.Label(header, textvariable=self.clock_var, style="Header.TLabel").pack(side="right")
        self.tz_var = tk.StringVar(value="CST")
        ttk.Label(header, textvariable=self.tz_var, style="Muted.TLabel").pack(
            side="right", padx=(0, 10)
        )

        body = ttk.Frame(root, padding=(10, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=4)
        body.columnconfigure(2, weight=3)
        body.rowconfigure(1, weight=1)

        self._build_receiver(body)
        self._build_eas(body)
        self._build_alerts(body)
        self._build_products(body)
        self._build_log(body)

        self.status = ui.StatusBar(root)
        self.status.pack(fill="x", side="bottom")
        self.status.right.set(
            f"Location: Valparaiso, Indiana   |   IP {self.settings.get('bmh.ip')}:"
            f"{self.settings.get('bmh.port')}   |   Network Status: ONLINE (1)"
        )
        self.status.middle.set("VoiceText Paul  |  SAPI David / Zira")

    def _build_receiver(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Receiver")
        frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8), pady=(0, 8))

        face = tk.Frame(frame, background="#07130d", highlightthickness=1,
                        highlightbackground="#1d4d33")
        face.pack(fill="x")

        row = tk.Frame(face, background="#07130d")
        row.pack(fill="x", padx=10, pady=(8, 0))
        self.station_var = tk.StringVar(value="WXJ75  Valparaiso, IN")
        picker = ttk.Combobox(
            row, textvariable=self.station_var, state="readonly", width=24,
            values=[f"{s['id']}  {s['city']}, {s['state']}" for s in self.settings.stations()],
        )
        picker.pack(side="left")
        picker.bind("<<ComboboxSelected>>", self._on_station_change)
        self.tx_led = tk.Canvas(row, width=10, height=10, background="#07130d",
                                highlightthickness=0)
        self.tx_led.pack(side="right", padx=(0, 2))
        self._led_dot = self.tx_led.create_oval(1, 1, 9, 9, fill=ui.DANGER, outline="")
        tk.Label(row, text="TX", background="#07130d", foreground="#68a884",
                 font=(ui.MONO, 7)).pack(side="right", padx=(0, 4))

        self.freq_var = tk.StringVar(value="162.400")
        tk.Label(
            face, textvariable=self.freq_var, background="#07130d", foreground="#63f7a6",
            font=(ui.MONO, 30, "bold"),
        ).pack(anchor="w", padx=10)
        tk.Label(
            face, text="MHz   WXJ75   PORTER TOWNSHIP", background="#07130d",
            foreground="#3f8a63", font=(ui.MONO, 8),
        ).pack(anchor="w", padx=12, pady=(0, 6))

        self.signal = tk.Canvas(face, height=26, background="#07130d", highlightthickness=0)
        self.signal.pack(fill="x", padx=8, pady=(0, 6))
        for i, height in enumerate((6, 10, 14, 20, 24)):
            self.signal.create_rectangle(
                8 + i * 9, 26 - height, 14 + i * 9, 26,
                fill="#2fbf71" if i < 4 else "#1b3a2a", outline="",
            )
        self.signal.create_text(
            70, 13, anchor="w", text="162.4000 MHz    WXJ75/NWS",
            fill="#3f8a63", font=(ui.MONO, 7),
        )

        controls = ttk.Frame(frame)
        controls.pack(fill="x", pady=(8, 4))
        self.tx_button = ttk.Button(
            controls, text="START TX", style="Accent.TButton", command=self._toggle_tx
        )
        self.tx_button.pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(controls, text="NEXT", command=self._next).pack(side="left", padx=2)
        ttk.Button(controls, text="RESTART", command=self._restart).pack(side="left", padx=2)

        state_row = ttk.Frame(frame)
        state_row.pack(fill="x", pady=2)
        self.state_var = tk.StringVar(value="STOPPED")
        ttk.Label(state_row, text="STATE", style="Muted.TLabel").pack(side="left")
        ttk.Label(state_row, textvariable=self.state_var, style="Value.TLabel").pack(
            side="left", padx=(6, 14)
        )
        self.mode_var = tk.StringVar(value=self.engine.mode)
        ttk.Label(state_row, text="MODE", style="Muted.TLabel").pack(side="left")
        mode = ttk.Combobox(
            state_row, textvariable=self.mode_var, state="readonly", width=22,
            values=self.settings.mode_list(),
        )
        mode.pack(side="left", padx=4)
        mode.bind("<<ComboboxSelected>>", lambda _e: self.engine.set_mode(self.mode_var.get()))

        voice_row = ttk.Frame(frame)
        voice_row.pack(fill="x", pady=(6, 0))
        ttk.Label(voice_row, text="VOICE", style="Muted.TLabel").pack(side="left")
        self.voice_var = tk.StringVar(value="paul")
        voice = ttk.Combobox(
            voice_row, textvariable=self.voice_var, state="readonly", width=10,
            values=self.engine.voices.keys(),
        )
        voice.pack(side="left", padx=4)
        voice.bind("<<ComboboxSelected>>", self._on_voice_change)
        ttk.Button(voice_row, text="TEST", command=self._test_voice).pack(side="left", padx=2)

        queue_box = ttk.Frame(frame)
        queue_box.pack(fill="both", expand=True, pady=(8, 0))
        head = ttk.Frame(queue_box)
        head.pack(fill="x")
        ttk.Label(head, text="BROADCAST QUEUE", style="Header.TLabel").pack(side="left")
        self.queue_len_var = tk.StringVar(value="0 items")
        ttk.Label(head, textvariable=self.queue_len_var, style="Muted.TLabel").pack(side="right")
        self.queue_list = tk.Listbox(
            queue_box, height=8, background=ui.FIELD, foreground=ui.TEXT,
            selectbackground=ui.ACCENT_DARK, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 8),
        )
        self.queue_list.pack(fill="both", expand=True, pady=(4, 0))

    def _build_eas(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "EAS Details Channel")
        frame.grid(row=0, column=1, sticky="nsew", padx=(0, 8), pady=(0, 8))

        self.ticker = ui.Ticker(frame, height=28)
        self.ticker.pack(fill="x", pady=(0, 8))

        now_row = ttk.Frame(frame, style="Panel.TFrame")
        now_row.pack(fill="x")
        ttk.Label(now_row, text="NOW PLAYING", style="Muted.TLabel").pack(side="left")
        self.now_var = tk.StringVar(value="--")
        ttk.Label(now_row, textvariable=self.now_var, style="Header.TLabel").pack(
            side="left", padx=(8, 0)
        )
        self.elapsed_var = tk.StringVar(value="")
        ttk.Label(now_row, textvariable=self.elapsed_var, style="Muted.TLabel").pack(side="right")

        self.preview = tk.Text(
            frame, height=10, wrap="word", background="#050c11", foreground="#b9d6eb",
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 9), padx=8, pady=6, state="disabled",
        )
        self.preview.pack(fill="both", expand=True, pady=6)

        same_row = ttk.Frame(frame, style="Panel.TFrame")
        same_row.pack(fill="x")
        ttk.Label(same_row, text="SAME", style="Muted.TLabel").pack(side="left")
        self.same_var = tk.StringVar(value="ZCZC-...")
        ttk.Label(same_row, textvariable=self.same_var, style="Value.TLabel").pack(
            side="left", padx=6
        )

        actions = ttk.Frame(frame, style="Panel.TFrame")
        actions.pack(fill="x", pady=(8, 0))
        ttk.Button(actions, text="1050 Hz TONE", command=lambda: self.engine.tone_only()).pack(
            side="left", padx=(0, 4)
        )
        ttk.Button(actions, text="SAME RETONE", command=self._retone_selected).pack(
            side="left", padx=4
        )
        ttk.Button(
            actions, text="SILENT INTERRUPT", style="Danger.TButton",
            command=lambda: self.engine.silent_interrupt(),
        ).pack(side="right")
        ttk.Button(actions, text="READ ALERT", command=self._read_selected).pack(
            side="right", padx=4
        )

        self.hazard_var = tk.StringVar(value=ALERT_EVENTS[0])
        hazard_row = ttk.Frame(frame, style="Panel.TFrame")
        hazard_row.pack(fill="x", pady=(8, 0))
        ttk.Label(hazard_row, text="HAZARD", style="Muted.TLabel").pack(side="left")
        ttk.Combobox(
            hazard_row, textvariable=self.hazard_var, state="readonly", width=28,
            values=ALERT_EVENTS,
        ).pack(side="left", padx=6)

        ttk.Label(frame, text="CUSTOM MESSAGE", style="Muted.TLabel").pack(
            anchor="w", pady=(6, 2)
        )
        self.message = tk.Text(
            frame, height=3, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.UI_FONT, 9), padx=6, pady=4,
        )
        self.message.pack(fill="x")
        self.message.insert("1.0", "This is a test.")

        send_row = ttk.Frame(frame, style="Panel.TFrame")
        send_row.pack(fill="x", pady=(6, 0))
        ttk.Button(
            send_row, text="SEND SAME ALERT", style="Accent.TButton",
            command=self._send_alert,
        ).pack(side="left")
        ttk.Button(
            send_row, text="RWT", command=lambda: self.engine.send_test("Required Weekly Test")
        ).pack(side="left", padx=4)
        ttk.Button(
            send_row, text="RMT", command=lambda: self.engine.send_test("Required Monthly Test")
        ).pack(side="left")
        ttk.Button(send_row, text="CLEAR", command=self._clear_alerts).pack(side="right")

    def _build_alerts(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Active Alerts")
        frame.grid(row=0, column=2, sticky="nsew", pady=(0, 8))

        columns = [("event", "Event", 130), ("area", "Area", 120),
                   ("status", "Act", 44), ("expires", "Expires", 64)]
        self.alert_tree = ui.tree(frame, columns, height=12)
        self.alert_tree.pack(fill="both", expand=True)
        self.alert_tree.bind("<Double-1>", lambda _e: self._read_selected())

        row = ttk.Frame(frame, style="Panel.TFrame")
        row.pack(fill="x", pady=(6, 0))
        ttk.Button(row, text="REFRESH", command=self._refresh_alerts).pack(side="left")
        ttk.Button(row, text="CANCEL", command=self._cancel_selected).pack(side="left", padx=4)

        ttk.Label(
            frame,
            text="Priority: Tornado Emergency > Warning > Watch > Advisory > Statement",
            style="Muted.TLabel", wraplength=300, justify="left",
        ).pack(anchor="w", pady=(8, 0))

        self.summary_var = tk.StringVar(value="No active alerts.")
        ttk.Label(
            frame, textvariable=self.summary_var, style="Muted.TLabel",
            wraplength=300, justify="left",
        ).pack(anchor="w", pady=(4, 0))

    def _build_products(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Programs")
        frame.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        for idx, (label, pid) in enumerate(PRODUCT_BUTTONS):
            ttk.Button(
                frame, text=label, command=lambda p=pid: self._read_product(p)
            ).grid(row=idx // 2, column=idx % 2, sticky="ew", padx=2, pady=2)
        for idx, (label, key) in enumerate(STATIC_BUTTONS):
            base = len(PRODUCT_BUTTONS)
            ttk.Button(
                frame, text=label, command=lambda k=key: self._read_static(k)
            ).grid(row=(base + idx) // 2, column=idx % 2, sticky="ew", padx=2, pady=2)
        frame.columnconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)

    def _build_log(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Transmitter Log")
        frame.grid(row=1, column=1, columnspan=2, sticky="nsew")
        holder = ttk.Frame(frame)
        holder.pack(fill="both", expand=True)
        self.log_text = ui.tagged_log(holder, height=9)
        self.log_text.configure(state="disabled")

    # -------------------------------------------------------------- helpers
    def log(self, message: str, tag: str = "") -> None:
        stamp = tz.central_now()[0].strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp}  {message}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _on_event(self, kind: str, payload: dict) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            self.root.after(0, lambda: self._handle_event(kind, payload))
        except RuntimeError:
            pass

    def _handle_event(self, kind: str, payload: dict) -> None:
        if kind == "log":
            self.log(payload.get("message", ""))
        elif kind == "status":
            self._update_status(payload)
        elif kind == "queue":
            self._refresh_queue()
        elif kind == "playing":
            self.now_var.set(payload.get("title", "--"))
            self.elapsed_var.set(f"{float(payload.get('seconds', 0)):.0f} s")
            self._show_current_script()
        elif kind == "ticker":
            self._update_ticker()
        elif kind == "alert":
            self._refresh_alerts()

    def _update_status(self, snap: dict | None = None) -> None:
        snap = snap or self.engine.snapshot()
        self.state_var.set(snap["state"])
        running = snap["running"]
        self.tx_button.configure(text="STOP TX" if running else "START TX")
        self.tx_led.itemconfigure(self._led_dot, fill=ui.OK if running else ui.DANGER)
        self.queue_len_var.set(f"{snap['queue']} items")
        if snap.get("current"):
            self.now_var.set(snap["current"])
        self.status.left.set(
            f"{snap['station']}  |  {snap['mode']}  |  {snap['state']}  |  "
            f"queue {snap['queue']}  |  played {snap['played']}"
        )

    def _refresh_queue(self) -> None:
        self.queue_list.delete(0, "end")
        for row in self.engine.queue_snapshot():
            self.queue_list.insert(
                "end", f"{row['priority']:>3}  {row['source'][:6]:<6} {row['title']}"
            )
        self._update_status()

    def _show_current_script(self) -> None:
        item = self.engine.current
        text = item.script.text() if item else "Transmitter idle."
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text or "(asset playback)")
        self.preview.configure(state="disabled")

    def _update_ticker(self) -> None:
        active = self.engine.active_alerts()
        pieces = [self.engine.ticker_text]
        for alert in active[:3]:
            pieces.append(
                f"{alert.event.upper()} FOR {alert.area.upper()} UNTIL "
                f"{alert.expires:%I:%M %p} {tz.central_from_utc(alert.expires)[1]}"
            )
        self.ticker.set_text("   ...   ".join(pieces))
        self.summary_var.set(self.engine.alerts.summary())

    # ------------------------------------------------------------- actions
    def _toggle_tx(self) -> None:
        if self.engine.snapshot()["running"]:
            self.engine.stop()
            self.log("STOP TX - transmitter off", "warn")
        else:
            self.engine.start()
            self.log("START TX - continuous broadcast loop", "ok")
        self._update_status()
        self._refresh_queue()

    def _next(self) -> None:
        self.engine.next_product()

    def _restart(self) -> None:
        self.engine.restart_service()
        self._update_status()
        self._refresh_queue()

    def _read_product(self, pid: str) -> None:
        item = self.engine.enqueue_product(pid)
        self.log(f"queued {item.title}")
        self._refresh_queue()
        if not self.engine.snapshot()["running"]:
            self.log("transmitter is stopped - press START TX to broadcast", "warn")

    def _read_static(self, key: str) -> None:
        item = self.engine.enqueue_static(key)
        self.log(f"queued {item.title}")
        self._refresh_queue()

    def _on_voice_change(self, _event=None) -> None:
        self.engine.voice = self.voice_var.get()
        self.log(f"voice set to {self.voice_var.get()}")

    def _test_voice(self) -> None:
        key = self.voice_var.get()
        try:
            path = self.engine.voices.test_voice(key)
            self.log(f"voice test rendered: {path.name}", "ok")
            audio.player().play(path)
        except Exception as exc:
            self.log(f"voice test failed: {exc}", "err")

    def _on_station_change(self, _event=None) -> None:
        text = self.station_var.get()
        station_id = text.split()[0]
        if station_id == self.station_id:
            return
        self.log(f"switching transmitter to {station_id}")
        self.engine.shutdown()
        self.station_id = station_id
        self.station = self.settings.station(station_id)
        self.freq_var.set(self.station["frequency"])
        self.engine = broadcast.BroadcastEngine(
            station_id, self.settings, on_event=self._on_event
        )
        self.engine.alerts = self.store
        self.engine.voice = self.voice_var.get()
        self.engine.ticker_text = self.settings.get("bmh.ticker", "This is a test.")
        self._update_status()
        self._refresh_queue()

    def _selected_alert(self):
        selection = self.alert_tree.selection()
        if not selection:
            return None
        return self.store.by_id(selection[0])

    def _read_selected(self) -> None:
        alert = self._selected_alert()
        if alert:
            self.engine.read_alert(alert)
            self.log(f"reading {alert.event} {alert.alert_id}", "warn")

    def _retone_selected(self) -> None:
        alert = self._selected_alert()
        if alert:
            self.engine.retone(alert)
            self.log(f"SAME retone queued for {alert.alert_id}", "warn")

    def _cancel_selected(self) -> None:
        alert = self._selected_alert()
        if alert:
            self.store.cancel(alert.alert_id)
            self.log(f"cancelled {alert.alert_id}", "warn")
            self._refresh_alerts()
            self._update_ticker()

    def _clear_alerts(self) -> None:
        self.store.clear()
        self.log("all alerts cleared")
        self._refresh_alerts()
        self._update_ticker()

    def _refresh_alerts(self) -> None:
        for row in self.alert_tree.get_children():
            self.alert_tree.delete(row)
        for alert in self.store.filtered(
            self.engine.listeners, self.engine.filter_enabled, self.engine.allow_uncoded
        ):
            self.alert_tree.insert(
                "", "end", iid=alert.alert_id,
                values=(
                    alert.event,
                    alert.area,
                    alert.status,
                    f"{alert.expires:%H:%M}Z",
                ),
            )
        self.summary_var.set(self.store.summary())
        self._update_ticker()

    def _send_alert(self) -> None:
        event = self.hazard_var.get()
        ugc = list(self.station.get("ugc", ["INZ001", "INZ002"]))
        message = self.message.get("1.0", "end").strip()
        alert = self.engine.send_same_alert(event, ugc, message)
        self.same_var.set(alert.same_header)
        self.log(f"SAME ALERT {event} -> {alert.same_header}", "warn")
        self._refresh_alerts()
        self._update_ticker()

    # -------------------------------------------------------------- timers
    def _tick(self) -> None:
        if self._closed:
            return
        now, label = tz.central_now()
        self.clock_var.set(f"{now:%H:%M:%S}")
        self.tz_var.set(f"{label}  {now:%a %b} {now.day}")
        if not self.engine.snapshot()["running"]:
            self.state_var.set("STOPPED")
        self._update_status()
        try:
            self._tick_job = self.root.after(1000, self._tick)
        except RuntimeError:
            pass

    def _close(self) -> None:
        self._closed = True
        if self._tick_job:
            try:
                self.root.after_cancel(self._tick_job)
            except Exception:
                pass
        try:
            self.engine.shutdown()
        finally:
            self.root.destroy()

    def mainloop(self) -> None:
        self.root.mainloop()


def main() -> None:
    RadioConsole().mainloop()


if __name__ == "__main__":
    main()
