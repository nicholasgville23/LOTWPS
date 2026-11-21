"""BMH Network - the Broadcast Message Handler hub for the WXJ75 / KBB58 chain.

Global network controls, the broadcast action bar (hazard + ticker + TRANSMIT),
the active transmitter list that opens the WXJ75 station controller, monitoring
and control, and compose/dispatch tools (text, live WAV, WarnGen).
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lotwps import (
    alerts as alert_mod,
    appkit,
    audio,
    awips,
    broadcast,
    bus as bus_mod,
    same,
    script as script_mod,
    tz,
    ui,
    zones,
)
from lotwps.config import settings as load_settings

HAZARDS = ["No hazard - scroll only"] + list(same.BMH_HAZARDS)


class NewTextMessageDialog(tk.Toplevel):
    """Send to BMH / Email / IEMBOT / Websites & Outlets."""

    ROUTES = [
        ("BMH", "Send to BMH"),
        ("EMAIL", "Email"),
        ("IEMBOT", "IEMBOT"),
        ("WEBSITES", "Websites & Outlets"),
    ]

    def __init__(self, parent, settings, bus, on_bmh=None) -> None:
        super().__init__(parent)
        self.settings = settings
        self.bus = bus
        self.on_bmh = on_bmh
        self.title("BMH  |  New Text Message")
        self.configure(background=ui.BG)
        ui.center(self, 760, 660, parent)
        self.minsize(660, 580)
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        head = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        head.pack(fill="x")
        ttk.Label(head, text="NEW TEXT MESSAGE", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  compose and dispatch", style="Muted.TLabel").pack(side="left")

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(5, weight=1)

        ttk.Label(body, text="SUBJECT", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.subject = tk.StringVar(value="Special Weather Statement")
        ttk.Entry(body, textvariable=self.subject).grid(
            row=0, column=1, sticky="ew", pady=2, padx=(6, 0)
        )

        ttk.Label(body, text="PRODUCT", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        self.product = tk.StringVar(value="Special Weather Statement")
        products = [awips.product(p).name for p in awips.PRODUCT_ORDER]
        ttk.Combobox(
            body, textvariable=self.product, state="readonly", values=products,
        ).grid(row=1, column=1, sticky="ew", pady=2, padx=(6, 0))

        ttk.Label(body, text="UGC", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        self.ugc = tk.StringVar(value="INZ001 INZ002")
        ttk.Entry(body, textvariable=self.ugc).grid(
            row=2, column=1, sticky="ew", pady=2, padx=(6, 0)
        )

        routes = ttk.LabelFrame(body, text=" Send To ", padding=8)
        routes.grid(row=3, column=0, columnspan=2, sticky="ew", pady=6)
        self.route_vars: dict[str, tk.BooleanVar] = {}
        for route, label in self.ROUTES:
            var = tk.BooleanVar(value=route in ("BMH", "IEMBOT"))
            self.route_vars[route] = var
            ttk.Checkbutton(routes, text=label, variable=var).pack(side="left", padx=6)

        ttk.Label(
            body, text="MESSAGE TEXT", style="Muted.TLabel"
        ).grid(row=4, column=0, columnspan=2, sticky="w")
        holder = ttk.Frame(body)
        holder.grid(row=5, column=0, columnspan=2, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.text = ui.text_widget(holder, height=14)
        self.text.frame.grid(row=0, column=0, sticky="nsew")
        self.text.insert(
            "1.0",
            "The National Weather Service in Chicago has issued a Special Weather "
            "Statement for northwest Indiana.\n\nA strong thunderstorm will move across "
            "Porter County through 5 PM. Wind gusts to 45 miles per hour and small hail "
            "are possible.\n\nStay tuned to NOAA Weather Radio for updates.",
        )

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="SEND", style="Accent.TButton", command=self._send).pack(
            side="left"
        )
        ttk.Button(buttons, text="CANCEL", command=self.destroy).pack(side="right")
        self.status = tk.StringVar(value="")
        ttk.Label(buttons, textvariable=self.status, style="Muted.TLabel").pack(
            side="left", padx=12
        )

    def _send(self) -> None:
        routes = [route for route, var in self.route_vars.items() if var.get()]
        if not routes:
            self.status.set("Select at least one destination.")
            return
        body_text = self.text.get("1.0", "end").strip()
        if not body_text:
            return
        ugc = zones.parse_ugc(self.ugc.get()) or ["INZ001", "INZ002"]
        prod = next(
            (awips.product(p) for p in awips.PRODUCT_ORDER if awips.product(p).name == self.product.get()),
            awips.product("SPS"),
        )
        payload = {
            "product": {"pil": prod.awips_id, "name": prod.name, "code": prod.pil},
            "ugc": ugc,
            "text": body_text,
            "subject": self.subject.get().strip(),
            "routes": routes,
            "subscribers": {
                route: self.settings.get(f"lotiem.subscribers.{route}", route)
                for route in routes
            },
        }
        self.bus.publish_product(
            body_text,
            payload["product"],
            ugc,
            {
                "subject": payload["subject"],
                "routes": routes,
                "subscribers": payload["subscribers"],
            },
        )
        if "BMH" in routes and self.on_bmh:
            self.on_bmh(payload)
        self.status.set("Dispatched to " + ", ".join(routes))
        self.after(350, self.destroy)


class SystemSettingsDialog(tk.Toplevel):
    def __init__(self, parent, settings, engine) -> None:
        super().__init__(parent)
        self.settings = settings
        self.engine = engine
        self.title("BMH  |  System Settings")
        self.configure(background=ui.BG)
        ui.center(self, 680, 560, parent)
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        head = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        head.pack(fill="x")
        ttk.Label(head, text="SYSTEM SETTINGS", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  BMH / LOTIEM", style="Muted.TLabel").pack(side="left")

        body = ttk.Frame(self, padding=12)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)

        self.fields = {
            "bmh.ip": tk.StringVar(value=str(self.settings.get("bmh.ip", "192.168.10.144"))),
            "bmh.port": tk.StringVar(value=str(self.settings.get("bmh.port", 6000))),
            "bmh.location": tk.StringVar(value=str(self.settings.get("bmh.location", ""))),
            "bmh.network_status": tk.StringVar(
                value=str(self.settings.get("bmh.network_status", "ONLINE (1)"))
            ),
            "bmh.ticker": tk.StringVar(value=str(self.settings.get("bmh.ticker", ""))),
            "lotiem.transport": tk.StringVar(value=str(self.settings.get("lotiem.transport", "file"))),
            "audio.tone_seconds": tk.StringVar(
                value=str(self.settings.get("audio.tone_seconds", 8.0))
            ),
        }
        labels = [
            ("BMH IP ADDRESS", "bmh.ip"),
            ("BMH PORT", "bmh.port"),
            ("LOCATION", "bmh.location"),
            ("NETWORK STATUS", "bmh.network_status"),
            ("TICKER TEXT", "bmh.ticker"),
            ("LOTIEM TRANSPORT (file / tcp)", "lotiem.transport"),
            ("1050 HZ TONE (SECONDS)", "audio.tone_seconds"),
        ]
        for idx, (label, key) in enumerate(labels):
            ttk.Label(body, text=label, style="Muted.TLabel").grid(
                row=idx, column=0, sticky="w", pady=3
            )
            ttk.Entry(body, textvariable=self.fields[key]).grid(
                row=idx, column=1, sticky="ew", pady=3, padx=(8, 0)
            )

        voices = self.engine.voices.describe()
        report = "\n".join(f"  {key}: {text}" for key, text in voices.items())
        ttk.Label(
            body,
            text="VOICE ENGINES\n" + report,
            style="Muted.TLabel", justify="left",
        ).grid(row=len(labels), column=0, columnspan=2, sticky="w", pady=(12, 0))

        ttk.Label(
            body,
            text="VoiceText Paul uses the pre-rendered WXJ75 assets for static IDs and "
                 "a shaped SAPI David proxy for live text. Set voices.paul.render_mode to "
                 "'assets' or 'sapi' in config/settings.json to change that.",
            style="Muted.TLabel", wraplength=600, justify="left",
        ).grid(row=len(labels) + 1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="SAVE", style="Accent.TButton", command=self._save).pack(
            side="left"
        )
        ttk.Button(buttons, text="CLOSE", command=self.destroy).pack(side="right")

    def _save(self) -> None:
        for key, var in self.fields.items():
            value = var.get().strip()
            if key in ("bmh.port",):
                try:
                    value = int(value)
                except ValueError:
                    messagebox.showwarning("System Settings", "Port must be a number.", parent=self)
                    return
            elif key == "audio.tone_seconds":
                try:
                    value = float(value)
                except ValueError:
                    messagebox.showwarning("System Settings", "Tone length must be a number.",
                                           parent=self)
                    return
            self.settings.set(key, value)
        self.settings.save()
        self.engine.ticker_text = self.settings.get("bmh.ticker", self.engine.ticker_text)
        messagebox.showinfo("System Settings", "Settings saved to config/settings.json.", parent=self)
        self.destroy()


class BMHNetwork:
    def __init__(self) -> None:
        self.root = appkit.boot(
            "BMH Network  |  Broadcast Message Handler",
            (1300, 850), (1120, 720),
        )
        self.settings = load_settings()
        self.store = alert_mod.store()
        self.bus = bus_mod.Bus("BMH")
        self.engine = broadcast.BroadcastEngine(
            "WXJ75", self.settings, on_event=self._on_event
        )
        self.engines: dict[str, broadcast.BroadcastEngine] = {"WXJ75": self.engine}
        self.controllers: dict[str, object] = {}
        self.hazard_var = tk.StringVar(value=same.BMH_HAZARDS[0])
        self.ticker_var = tk.StringVar(value=self.settings.get("bmh.ticker", "This is a test."))

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._closed = False
        self._tick_job = None
        self._tick_bus = None
        self._refresh_transmitters()
        self._refresh_alerts()
        self._poll_bus()
        self._tick()
        self.log("BMH network online - 2 transmitters, LOTIEM at "
                 f"{self.settings.get('bmh.ip')}:{self.settings.get('bmh.port')}")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self._build_menu()
        root = self.root

        header = ttk.Frame(root, style="Panel.TFrame", padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text="BMH NETWORK", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="Broadcast Message Handler  |  Valparaiso, Indiana  |  "
                 "Chicago / Northwest Indiana",
            style="Muted.TLabel",
        ).pack(side="left", padx=10)
        self.net_var = tk.StringVar(value="ONLINE (1)")
        ttk.Label(header, textvariable=self.net_var, style="Header.TLabel").pack(side="right")
        ttk.Label(header, text="NETWORK STATUS", style="Muted.TLabel").pack(
            side="right", padx=(0, 8)
        )
        self.clock_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock_var, style="Muted.TLabel").pack(
            side="right", padx=14
        )

        self.ticker = ui.Ticker(root, height=30)
        self.ticker.pack(fill="x", padx=8, pady=(6, 0))
        self.ticker.set_text(self.engine.ticker_text)

        body = ttk.Frame(root, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=2)
        body.columnconfigure(2, weight=3)
        body.rowconfigure(0, weight=1)

        left = ttk.Frame(body)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        self._build_broadcast_action(left)
        self._build_global(left)
        self._build_monitoring(left)

        middle = ttk.Frame(body)
        middle.grid(row=0, column=1, sticky="nsew", padx=6)
        middle.rowconfigure(0, weight=1)
        middle.rowconfigure(1, weight=1)
        self._build_transmitters(middle)
        self._build_dispatch(middle)

        right = ttk.Frame(body)
        right.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        right.rowconfigure(1, weight=1)
        self._build_alerts(right)
        self._build_log(right)

        self.status = ui.StatusBar(root)
        self.status.pack(fill="x", side="bottom")
        self.status.left.set("BMH ready  |  WXJ75 162.400 MHz  |  KBB58 162.425 MHz")
        self.status.middle.set(
            f"LOTIEM {self.settings.get('bmh.ip')}:{self.settings.get('bmh.port')}"
        )
        self.status.right.set("Location: Valparaiso, Indiana  |  Network Status: ONLINE (1)")

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        file_menu = tk.Menu(menubar, tearoff=False)
        file_menu.add_command(label="New Text Message", command=self._new_message)
        file_menu.add_command(label="Live Voice Message (WAV)", command=self._live_voice)
        file_menu.add_separator()
        file_menu.add_command(label="System Settings", command=self._system_settings)
        file_menu.add_command(label="Exit Station", command=self._exit_station)
        menubar.add_cascade(label="File", menu=file_menu)

        compose_menu = tk.Menu(menubar, tearoff=False)
        compose_menu.add_command(label="WarnGen", command=self._warngen)
        compose_menu.add_command(label="WatchGen", command=self._watchgen)
        compose_menu.add_command(label="Update Periodic Scroll", command=self._update_scroll)
        menubar.add_cascade(label="Compose", menu=compose_menu)

        tx_menu = tk.Menu(menubar, tearoff=False)
        tx_menu.add_command(label="WXJ75 Controller", command=lambda: self._open_controller("WXJ75"))
        tx_menu.add_command(label="KBB58 Controller", command=lambda: self._open_controller("KBB58"))
        tx_menu.add_separator()
        tx_menu.add_command(label="Start All Transmitters", command=self._start_all)
        tx_menu.add_command(label="Stop All Transmitters", command=self._stop_all)
        menubar.add_cascade(label="Transmitters", menu=tx_menu)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About BMH", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)

    def _build_broadcast_action(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Broadcast Action")
        frame.grid(row=0, column=0, sticky="new", pady=(0, 8))
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="HAZARD", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Combobox(
            frame, textvariable=self.hazard_var, state="readonly", values=HAZARDS,
        ).grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=2)

        ttk.Label(frame, text="TICKER TEXT", style="Muted.TLabel").grid(
            row=1, column=0, sticky="nw", pady=(4, 0)
        )
        self.ticker_entry = tk.Text(
            frame, height=3, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.UI_FONT, 9), padx=6, pady=4,
        )
        self.ticker_entry.grid(row=1, column=1, sticky="ew", padx=(6, 0), pady=(4, 0))
        self.ticker_entry.insert("1.0", self.engine.ticker_text)

        ttk.Button(
            frame, text="TRANSMIT", style="Accent.TButton", command=self._transmit
        ).grid(row=2, column=0, columnspan=2, sticky="ew", pady=(8, 2))
        ttk.Button(
            frame, text="UPDATE PERIODIC SCROLL", command=self._update_scroll
        ).grid(row=3, column=0, columnspan=2, sticky="ew")

    def _build_global(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Global Network Controls")
        frame.grid(row=1, column=0, sticky="nsew", pady=(0, 8))
        for idx, (label, command) in enumerate(
            [
                ("START ALL TRANSMITTERS", self._start_all),
                ("STOP ALL TRANSMITTERS", self._stop_all),
                ("SILENCE ALL / INTERRUPT", self._silence_all),
                ("REFRESH NETWORK", self._refresh_transmitters),
            ]
        ):
            ttk.Button(frame, text=label, command=command).grid(
                row=idx, column=0, sticky="ew", pady=2
            )
        frame.columnconfigure(0, weight=1)
        ttk.Label(
            frame,
            text=f"LOTIEM  {self.settings.get('bmh.ip')}:{self.settings.get('bmh.port')}\n"
                 f"Transport: {self.settings.get('lotiem.transport', 'file')}",
            style="Muted.TLabel", justify="left",
        ).grid(row=4, column=0, sticky="w", pady=(8, 0))

    def _build_monitoring(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Monitoring and Control")
        frame.grid(row=2, column=0, sticky="new")
        ttk.Button(frame, text="SYSTEM SETTINGS", command=self._system_settings).pack(
            fill="x", pady=2
        )
        ttk.Button(
            frame, text="EXIT STATION", style="Danger.TButton", command=self._exit_station
        ).pack(fill="x", pady=2)
        self.monitor_var = tk.StringVar(value="all systems nominal")
        ttk.Label(frame, textvariable=self.monitor_var, style="Muted.TLabel",
                  wraplength=300, justify="left").pack(anchor="w", pady=(8, 0))

    def _build_transmitters(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Active Transmitters")
        frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.tx_tree = ui.tree(
            frame,
            [("id", "Station", 90), ("freq", "MHz", 70), ("town", "Township", 140),
             ("status", "Status", 110)],
            height=7,
        )
        self.tx_tree.grid(row=0, column=0, sticky="nsew")
        self.tx_tree.bind("<Double-1>", lambda _e: self._open_selected())
        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="OPEN CONTROLLER", command=self._open_selected).pack(
            side="left"
        )
        ttk.Button(buttons, text="REFRESH", command=self._refresh_transmitters).pack(
            side="left", padx=4
        )
        ttk.Label(
            frame, text="double-click WXJ75 to open the BMH Station Controller",
            style="Muted.TLabel",
        ).grid(row=2, column=0, sticky="w", pady=(4, 0))

    def _build_dispatch(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Compose and Dispatch")
        frame.grid(row=1, column=0, sticky="nsew")
        for label, command in [
            ("NEW TEXT MESSAGE", self._new_message),
            ("LIVE VOICE MESSAGE (WAV)", self._live_voice),
            ("WARNGEN  /  WATCHGEN", self._warngen),
        ]:
            ttk.Button(frame, text=label, command=command).pack(fill="x", pady=3)
        ttk.Label(
            frame,
            text="Text messages route to BMH, Email, IEMBOT, and Websites & Outlets.",
            style="Muted.TLabel", wraplength=360, justify="left",
        ).pack(anchor="w", pady=(8, 0))

    def _build_alerts(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Network Alerts")
        frame.grid(row=0, column=0, sticky="nsew", pady=(0, 8))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.alert_tree = ui.tree(
            frame,
            [("event", "Event", 170), ("area", "Area", 170),
             ("status", "Act", 44), ("expires", "Expires", 66)],
            height=7,
        )
        self.alert_tree.grid(row=0, column=0, sticky="nsew")
        ttk.Button(frame, text="REFRESH ALERTS", command=self._refresh_alerts).grid(
            row=1, column=0, sticky="w", pady=(6, 0)
        )

    def _build_log(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Network Log")
        frame.grid(row=1, column=0, sticky="nsew")
        holder = ttk.Frame(frame)
        holder.pack(fill="both", expand=True)
        self.log_text = ui.tagged_log(holder, height=12)
        self.log_text.configure(state="disabled")

    # -------------------------------------------------------------- logging
    def log(self, message: str, tag: str = "") -> None:
        stamp = tz.central_now()[0].strftime("%H:%M:%S")
        self.log_text.configure(state="normal")
        self.log_text.insert("end", f"{stamp}  {message}\n", tag)
        self.log_text.see("end")
        self.log_text.configure(state="disabled")
        self.status.middle.set(message[:110])

    # ------------------------------------------------------------ engines
    def _engine_for(self, station_id: str):
        if station_id not in self.engines:
            engine = broadcast.BroadcastEngine(
                station_id, self.settings, on_event=self._on_event
            )
            self.engines[station_id] = engine
        return self.engines[station_id]

    def _refresh_transmitters(self) -> None:
        self.tx_tree.delete(*self.tx_tree.get_children())
        for station in self.settings.stations():
            engine = self.engines.get(station["id"])
            if engine is None:
                status = "STANDBY" if station.get("active") else "OFFLINE"
            elif engine.snapshot()["running"]:
                status = "ON AIR"
            else:
                status = "READY"
            self.tx_tree.insert(
                "", "end", iid=station["id"],
                values=(station["id"], station["frequency"], station["township"], status),
            )
        self.monitor_var.set(
            f"{len(self.engines)} controller running  |  "
            f"{len(self.store.active())} active alerts  |  "
            f"{self.bus.pending()} bus messages pending"
        )

    def _start_all(self) -> None:
        for station_id, engine in self.engines.items():
            engine.start()
            self.log(f"START TX {station_id}", "ok")
        self._refresh_transmitters()

    def _stop_all(self) -> None:
        for station_id, engine in self.engines.items():
            engine.stop()
            self.log(f"STOP TX {station_id}", "warn")
        self._refresh_transmitters()

    def _silence_all(self) -> None:
        for station_id, engine in self.engines.items():
            engine.silent_interrupt()
        self.log("SILENT INTERRUPT sent to every transmitter", "warn")
        self._refresh_transmitters()

    # ------------------------------------------------------------- actions
    def _transmit(self) -> None:
        hazard = self.hazard_var.get()
        ticker = self.ticker_entry.get("1.0", "end").strip()
        if not ticker:
            ticker = self.engine.ticker_text
        self.engine.transmit(None if hazard.startswith("No hazard") else hazard, ticker)
        self.ticker.set_text(ticker)
        self.settings.set("bmh.ticker", ticker)
        self.settings.save()
        self.log(
            f"TRANSMIT -> {hazard if not hazard.startswith('No hazard') else 'periodic scroll'}"
        )
        if hazard.startswith("No hazard"):
            self.hazard_var.set(HAZARDS[1])
        self._refresh_alerts()

    def _update_scroll(self) -> None:
        ticker = self.ticker_entry.get("1.0", "end").strip()
        if ticker:
            self.engine.ticker_text = ticker
            self.engine.enqueue(
                self.engine.script_for_text("Periodic Scroll", ticker, "SPS", 15)
            )
            self.ticker.set_text(ticker)
            self.settings.set("bmh.ticker", ticker)
            self.settings.save()
            self.log("periodic scroll updated", "ok")

    def _open_selected(self) -> None:
        selection = self.tx_tree.selection()
        if not selection:
            selection = self.tx_tree.get_children()
        if not selection:
            return
        self._open_controller(selection[0])

    def _open_controller(self, station_id: str) -> None:
        from bmh_station import StationController

        existing = self.controllers.get(station_id)
        try:
            if existing is not None and existing.root.winfo_exists():
                existing.root.deiconify()
                existing.root.lift()
                return
        except tk.TclError:
            pass
        controller = StationController(
            master=self.root, station_id=station_id,
            engine=self._engine_for(station_id),
        )
        self.controllers[station_id] = controller
        try:
            controller.root.transient(self.root)
        except tk.TclError:
            pass
        self.log(f"opened station controller {station_id}")

    def _new_message(self) -> None:
        NewTextMessageDialog(self.root, self.settings, self.bus, on_bmh=self._bmh_receive)

    def _bmh_receive(self, payload: dict) -> None:
        prod = payload["product"]
        text = payload["text"]
        subject = payload.get("subject") or prod["name"]
        item = self.engine.enqueue(
            self.engine.script_for_text(subject, text, prod["code"], 30), front=True
        )
        self.log(f"received from LOTWPS: {subject} ({item.seconds:.0f}s)", "accent")
        self._refresh_transmitters()

    def _live_voice(self) -> None:
        path = filedialog.askopenfilename(
            title="Live Voice Message (WAV)",
            filetypes=[("Wave audio", "*.wav"), ("All files", "*.*")],
            parent=self.root,
        )
        if not path:
            return
        try:
            seconds = audio.wav_duration(path)
        except Exception:
            seconds = 0.0
        script = script_mod.Script(
            title="Live Voice Message", product_id="SPS",
            voice=self.engine.voice, station_id="WXJ75", priority=80,
        )
        script.asset(Path(path), "LIVE_VOICE")
        script.pause(400)
        item = broadcast.QueueItem(
            item_id=f"VOICE-{tz.utc_now():%H%M%S}",
            title=f"Live Voice Message ({Path(path).name})",
            product_id="SPS", script=script, priority=80, source="VOICE",
        )
        self.engine.enqueue(item, front=True)
        self.log(f"live voice message queued: {Path(path).name} ({seconds:.1f}s)", "ok")

    def _warngen(self) -> None:
        from warngen_dialog import WarnGenDialog

        WarnGenDialog(
            self.root, engine=self.engine, title="WarnGen  |  BMH Network",
            on_issue=lambda text, prod, ugc, cell, points: self.log(
                f"WarnGen issued {prod.name} for {zones.describe_area(ugc)}", "warn"
            ),
        )

    def _watchgen(self) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, engine=self.engine, title="WatchGen  |  BMH Network",
            on_issue=lambda text, prod, ugc, cell, points: self.log(
                f"WatchGen issued {prod.name}", "warn"
            ),
        )
        dialog.product_var.set("Tornado Watch")
        dialog._update_preview()

    # -------------------------------------------------------------- alerts
    def _refresh_alerts(self) -> None:
        self.alert_tree.delete(*self.alert_tree.get_children())
        for alert in self.store.active():
            self.alert_tree.insert(
                "", "end", iid=alert.alert_id,
                values=(alert.event, alert.area, alert.status,
                        f"{alert.expires:%H:%M}Z"),
            )
        self._refresh_transmitters()

    # -------------------------------------------------------------- events
    def _on_event(self, kind: str, payload: dict) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            self.root.after(0, lambda: self._handle_event(kind, payload))
        except (RuntimeError, tk.TclError):
            pass

    def _handle_event(self, kind: str, payload: dict) -> None:
        if getattr(self, "_closed", False):
            return
        try:
            if kind == "log":
                self.log(payload.get("message", ""))
            elif kind in ("status", "queue"):
                self._refresh_transmitters()
            elif kind == "playing":
                self.status.left.set(f"ON AIR: {payload.get('title', '')}")
            elif kind == "alert":
                self._refresh_alerts()
        except tk.TclError:
            pass

    def _poll_bus(self) -> None:
        if self._closed:
            return
        try:
            for message in self.bus.poll():
                target = message.get("to", "")
                if target not in ("BMH", "ALL", "LOTIEM"):
                    continue
                self._handle_bus_message(message)
        except Exception as exc:
            self.log(f"bus poll error: {exc}", "err")
        try:
            self._tick_bus = self.root.after(2000, self._poll_bus)
        except tk.TclError:
            self._tick_bus = None

    def _handle_bus_message(self, message: dict) -> None:
        topic = message.get("topic")
        payload = message.get("payload", {})
        if topic == "product":
            if message.get("from") == "BMH":
                return
            prod = payload.get("product", {})
            subject = payload.get("options", {}).get("subject") or prod.get("name", "Product")
            text = payload.get("text", "")
            if text:
                self.engine.enqueue(
                    self.engine.script_for_text(subject, text, prod.get("code", "SPS"), 30),
                    front=True,
                )
                self.log(f"LOTIEM product received: {subject}", "accent")
        elif topic == "alert":
            self._refresh_alerts()
            self.log("LOTIEM alert update received", "warn")
        elif topic == "status":
            action = payload.get("action") or payload.get("message") or "status"
            self.log(f"LOTIEM: {action}")

    # --------------------------------------------------------------- timers
    def _tick(self) -> None:
        if self._closed:
            return
        now, label = tz.central_now()
        self.clock_var.set(f"{now:%H:%M:%S} {label}  {now:%a %b} {now.day}")
        running = sum(1 for e in self.engines.values() if e.snapshot()["running"])
        self.net_var.set(f"ONLINE ({max(1, running)})" if running else "ONLINE (1)")
        self._tick_bus_guard()
        try:
            self._tick_job = self.root.after(1000, self._tick)
        except tk.TclError:
            pass

    def _tick_bus_guard(self) -> None:
        # make sure the bus poller is alive even if the window was rebuilt
        if not getattr(self, "_tick_bus", None):
            self._poll_bus()

    def _system_settings(self) -> None:
        SystemSettingsDialog(self.root, self.settings, self.engine)

    def _exit_station(self) -> None:
        if not messagebox.askyesno(
            "Exit Station", "Shut down BMH and stop every transmitter?", parent=self.root
        ):
            return
        for controller in list(self.controllers.values()):
            try:
                controller.root.destroy()
            except Exception:
                pass
        for engine in self.engines.values():
            engine.shutdown()
        self.log("BMH station shutdown")
        self._closed = True
        for job in (self._tick_job, self._tick_bus):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self.root.destroy()

    def _close(self) -> None:
        self._closed = True
        for job in (self._tick_job, self._tick_bus):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        for engine in self.engines.values():
            try:
                engine.shutdown()
            except Exception:
                pass
        self.root.destroy()

    def _about(self) -> None:
        messagebox.showinfo(
            "About BMH",
            "BMH Network  -  Broadcast Message Handler\n"
            "BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS\n\n"
            "Transmitters: WXJ75 162.400 MHz Porter Township, "
            "KBB58 162.425 MHz Lake Township\n"
            "Location: Valparaiso, Indiana\n"
            f"LOTIEM: {self.settings.get('bmh.ip')}:{self.settings.get('bmh.port')}\n"
            "Voices: VoiceText Paul, Microsoft David, Microsoft Zira",
            parent=self.root,
        )

    def mainloop(self) -> None:
        self.root.mainloop()


def main() -> None:
    BMHNetwork().mainloop()


if __name__ == "__main__":
    main()
