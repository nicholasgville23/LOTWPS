"""Tkinter desktop shell for LOTWPS / LOTIEM.

The app is a forecaster-oriented local workstation prototype. NWS data is live;
message dispatch, official WarnGen, public EAS activation and RF transmission
are intentionally not implemented.
"""

from __future__ import annotations

import queue
import threading
import tkinter as tk
import webbrowser
from tkinter import filedialog, messagebox, simpledialog, ttk
from tkinter.scrolledtext import ScrolledText

from .bmh import LocalBMHQueue, check_tcp_reachability
from .broadcast import BroadcastLoop
from .config import APP_SETTINGS_FILE, load_app_settings, load_stations, write_json
from .models import AlertPriority, Station, sort_alerts
from .nws import NWSClient
from .speech import SpeechEngine
from .workstation import build_product_draft, make_product_id, make_wmo_header


HAZARDS = (
    "Tornado Emergency",
    "Tornado Warning",
    "Severe Thunderstorm Warning",
    "Flash Flood Warning",
    "Extreme Wind Warning",
    "Special Weather Statement",
    "Tornado Watch",
    "Severe Thunderstorm Watch",
    "Required Weekly Test (lab text only)",
    "Required Monthly Test (lab text only)",
)

MODES = (
    "Winter Weather",
    "Flooding",
    "Severe Weather",
    "Severe Weather Possible",
    "Off the Air",
    "Station ID Only",
    "Current Time Only",
    "General",
    "Zone Forecast",
    "Severe Weather and Alert Summary",
)

CATEGORIES = ("TOR", "SVR", "FFW", "EWW", "SPS", "HWO", "ZFP", "AFD")


class LOTWPSApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.settings = load_app_settings()
        self.stations = [Station.from_dict(item) for item in load_stations()]
        if not self.stations:
            raise RuntimeError("No enabled stations are configured in config/stations.json")

        self.nws = NWSClient(str(self.settings["nws_user_agent"]))
        self.speech = SpeechEngine(str(self.settings.get("voicetext_exe", "")))
        self.bmh_queue = LocalBMHQueue()
        self.ui_queue: queue.Queue[tuple[str, object]] = queue.Queue()
        self.station_data: dict[str, dict] = {}
        self.all_alerts = []
        self.broadcast: BroadcastLoop | None = None
        self.cycle_number = 0

        self.root.title(str(self.settings["window_title"]))
        self.root.geometry("1320x860")
        self.root.minsize(1020, 680)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

        self._build_shell()
        self._build_dashboard()
        self._build_workstation()
        self._build_warngen()
        self._build_bmh()
        self._build_station_controller()
        self._build_live_queue()
        self._build_settings()
        self.root.after(150, self._poll_ui_queue)
        self.refresh_weather()

    def _build_shell(self) -> None:
        header = ttk.Frame(self.root, padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(header, text="KLOT LOTIEM TEXT WORKSTATION", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(
            header,
            text="LOCAL LAB MODE  |  NO RF TRANSMISSION  |  NO PUBLIC EAS ACTIVATION",
            foreground="#a12d2d",
            font=("Segoe UI", 9, "bold"),
        ).pack(side="right")
        self.status_var = tk.StringVar(value="Starting LOTWPS…")
        ttk.Label(self.root, textvariable=self.status_var, relief="sunken", anchor="w").pack(
            side="bottom", fill="x"
        )
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        self.dashboard_tab = ttk.Frame(self.notebook, padding=10)
        self.workstation_tab = ttk.Frame(self.notebook, padding=10)
        self.warngen_tab = ttk.Frame(self.notebook, padding=10)
        self.bmh_tab = ttk.Frame(self.notebook, padding=10)
        self.station_tab = ttk.Frame(self.notebook, padding=10)
        self.queue_tab = ttk.Frame(self.notebook, padding=10)
        self.settings_tab = ttk.Frame(self.notebook, padding=10)
        for tab, title in (
            (self.dashboard_tab, "Active Alerts / Status"),
            (self.workstation_tab, "Text Workstation"),
            (self.warngen_tab, "WarnGen / WatchGen Draft"),
            (self.bmh_tab, "BMH Network"),
            (self.station_tab, "Station Controller"),
            (self.queue_tab, "Live Queue"),
            (self.settings_tab, "Settings"),
        ):
            self.notebook.add(tab, text=title)

    def _build_dashboard(self) -> None:
        controls = ttk.Frame(self.dashboard_tab)
        controls.pack(fill="x", pady=(0, 8))
        ttk.Button(controls, text="REFRESH NWS DATA", command=self.refresh_weather).pack(side="left")
        ttk.Button(controls, text="OPEN NWS API DOCS", command=lambda: webbrowser.open(
            "https://www.weather.gov/documentation/services-web-api"
        )).pack(side="left", padx=6)
        ttk.Button(controls, text="OPEN EAS TOOLS (LAB ONLY)", command=self.open_eas_tools).pack(side="right")

        self.station_tree = ttk.Treeview(
            self.dashboard_tab,
            columns=("location", "frequency", "clock", "condition", "status"),
            show="headings",
            height=5,
        )
        for column, label, width in (
            ("location", "Station / Location", 230),
            ("frequency", "Configured MHz", 120),
            ("clock", "Local Station Time", 190),
            ("condition", "Latest Observation", 430),
            ("status", "NWS Status", 170),
        ):
            self.station_tree.heading(column, text=label)
            self.station_tree.column(column, width=width, anchor="w")
        self.station_tree.pack(fill="x", pady=(0, 12))
        self._refresh_station_rows()

        ttk.Label(self.dashboard_tab, text="ACTIVE NWS ALERTS", font=("Segoe UI", 10, "bold")).pack(
            anchor="w", pady=(0, 4)
        )
        self.alert_tree = ttk.Treeview(
            self.dashboard_tab,
            columns=("priority", "event", "area", "expires", "severity"),
            show="headings",
            height=15,
        )
        for column, label, width in (
            ("priority", "Priority", 105),
            ("event", "Event", 240),
            ("area", "Affected Area", 430),
            ("expires", "Expires", 190),
            ("severity", "NWS Severity", 130),
        ):
            self.alert_tree.heading(column, text=label)
            self.alert_tree.column(column, width=width, anchor="w")
        self.alert_tree.pack(fill="both", expand=True)

    def _build_workstation(self) -> None:
        header = ttk.LabelFrame(self.workstation_tab, text="AWIPS Header Block — editable draft", padding=8)
        header.pack(fill="x")
        self.header_type = tk.StringVar(value="TTAAii")
        self.cccc = tk.StringVar(value="KLOT")
        self.bbb = tk.StringVar(value=str(self.settings.get("default_bbb", "NOR")))
        self.category = tk.StringVar(value="SPS")
        self.designator = tk.StringVar(value="LOT")
        self.addressee = tk.StringVar(value="ALL")

        fields = (
            ("WMO Type", self.header_type, ("TTAAii", "TTBBii", "SMUSxx")),
            ("CCCC", self.cccc, ("KLOT",)),
            ("BBB", self.bbb, ("NOR", "COR", "AMD")),
            ("Product Category", self.category, CATEGORIES),
            ("Designator", self.designator, ("LOT",)),
            ("Addressee", self.addressee, ("ALL",)),
        )
        for index, (label, variable, values) in enumerate(fields):
            group = ttk.Frame(header)
            group.grid(row=0, column=index, padx=4, sticky="ew")
            ttk.Label(group, text=label).pack(anchor="w")
            ttk.Combobox(group, textvariable=variable, values=values, width=12).pack(fill="x")
            header.columnconfigure(index, weight=1)
        ttk.Button(header, text="GENERATE HEADER", command=self.generate_header).grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 0)
        )
        self.header_preview = tk.StringVar(value="WMO header preview will appear here.")
        ttk.Label(header, textvariable=self.header_preview).grid(
            row=1, column=2, columnspan=4, sticky="w", padx=8, pady=(8, 0)
        )

        targets = ttk.LabelFrame(self.workstation_tab, text="New Text Message — destination selections", padding=8)
        targets.pack(fill="x", pady=8)
        self.target_vars = {
            "BMH local queue": tk.BooleanVar(value=True),
            "Email (not connected)": tk.BooleanVar(value=False),
            "IEMBOT (not connected)": tk.BooleanVar(value=False),
            "Websites & outlets (not connected)": tk.BooleanVar(value=False),
        }
        for label, variable in self.target_vars.items():
            ttk.Checkbutton(targets, text=label, variable=variable).pack(side="left", padx=6)
        ttk.Label(targets, text="Wrap at").pack(side="left", padx=(16, 4))
        self.wrap_width = tk.IntVar(value=72)
        ttk.Spinbox(targets, from_=40, to=120, textvariable=self.wrap_width, width=5).pack(side="left")
        ttk.Label(targets, text="characters").pack(side="left", padx=3)

        ttk.Label(self.workstation_tab, text="MESSAGE EDITOR  (right-click for segment actions)").pack(anchor="w")
        self.editor = ScrolledText(self.workstation_tab, height=18, wrap="word", undo=True)
        self.editor.pack(fill="both", expand=True)
        self.editor.insert(
            "1.0",
            "Enter the product text here. Use the header generator above to add an editable draft header.\n"
        )
        self.editor_menu = tk.Menu(self.root, tearoff=False)
        self.editor_menu.add_command(label="Add Segment", command=self.add_segment)
        self.editor_menu.add_command(label="Edit Segment", command=self.edit_segment)
        self.editor_menu.add_command(label="Remove Segment", command=self.remove_segment)
        self.editor_menu.add_command(label="Combine Segments", command=self.combine_segments)
        self.editor.bind("<Button-3>", self._show_editor_menu)

        actions = ttk.Frame(self.workstation_tab)
        actions.pack(fill="x", pady=(8, 0))
        for label, command in (
            ("ADD SEGMENT", self.add_segment),
            ("EDIT SEGMENT", self.edit_segment),
            ("REMOVE SEGMENT", self.remove_segment),
            ("COMBINE SEGMENTS", self.combine_segments),
            ("PREVIEW / QUEUE LOCAL", self.queue_workstation_message),
            ("SAVE TEXT", self.save_text),
        ):
            ttk.Button(actions, text=label, command=command).pack(side="left", padx=(0, 5))

    def _build_warngen(self) -> None:
        ttk.Label(
            self.warngen_tab,
            text="WarnGen / WatchGen — local draft composer, not the official AWIPS WarnGen client.",
            foreground="#a12d2d",
        ).pack(anchor="w", pady=(0, 8))
        form = ttk.Frame(self.warngen_tab)
        form.pack(fill="x")
        ttk.Label(form, text="Hazard").grid(row=0, column=0, sticky="w")
        self.warn_hazard = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Combobox(form, textvariable=self.warn_hazard, values=HAZARDS, width=42).grid(
            row=0, column=1, sticky="w", padx=6
        )
        ttk.Label(form, text="Affected counties / UGC / zone text").grid(row=1, column=0, sticky="w", pady=6)
        self.warn_area = tk.StringVar(value="Porter County, Indiana; Lake County, Indiana")
        ttk.Entry(form, textvariable=self.warn_area, width=72).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Label(form, text="Expiration (local time)").grid(row=2, column=0, sticky="w")
        self.warn_expiration = tk.StringVar(value="Set expiration after reviewing official guidance")
        ttk.Entry(form, textvariable=self.warn_expiration, width=72).grid(row=2, column=1, sticky="ew", padx=6)
        ttk.Label(form, text="Warning / call-to-action text").grid(row=3, column=0, sticky="nw", pady=6)
        self.warn_body = ScrolledText(self.warngen_tab, height=18, wrap="word")
        self.warn_body.pack(fill="both", expand=True, pady=6)
        self.warn_body.insert(
            "1.0",
            "Enter the verified hazard description, timing, impacts, and protective actions. "
            "This composer does not issue an alert or validate polygon geometry."
        )
        buttons = ttk.Frame(self.warngen_tab)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="BUILD DRAFT IN TEXT WORKSTATION", command=self.build_warning_draft).pack(
            side="left"
        )
        ttk.Button(buttons, text="OPEN EAS TOOLS WARNGEN", command=lambda: webbrowser.open(
            "https://eas.tools/?tool=warngen"
        )).pack(side="left", padx=6)
        form.columnconfigure(1, weight=1)

    def _build_bmh(self) -> None:
        ttk.Label(
            self.bmh_tab,
            text="BMH Network — local message queue and station reachability monitor only.",
            foreground="#a12d2d",
        ).pack(anchor="w", pady=(0, 8))
        config = ttk.LabelFrame(self.bmh_tab, text="Global Network Controls", padding=8)
        config.pack(fill="x")
        self.bmh_host = tk.StringVar(value=str(self.settings.get("bmh_target_host", "127.0.0.1")))
        self.bmh_port = tk.IntVar(value=int(self.settings.get("bmh_target_port", 6000)))
        self.bmh_station = tk.StringVar(value=self.stations[0].station_id)
        ttk.Label(config, text="Station endpoint").grid(row=0, column=0, sticky="w")
        ttk.Entry(config, textvariable=self.bmh_host, width=22).grid(row=0, column=1, padx=5)
        ttk.Label(config, text="Port").grid(row=0, column=2, sticky="w")
        ttk.Spinbox(config, from_=1, to=65535, textvariable=self.bmh_port, width=8).grid(row=0, column=3, padx=5)
        ttk.Button(config, text="CHECK TCP (NO DATA SENT)", command=self.check_bmh_connection).grid(
            row=0, column=4, padx=8
        )
        ttk.Label(config, text="Station").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(
            config, textvariable=self.bmh_station,
            values=[station.station_id for station in self.stations], state="readonly", width=18
        ).grid(row=1, column=1, sticky="w", padx=5)
        self.bmh_connection_status = tk.StringVar(value="Not checked")
        ttk.Label(config, textvariable=self.bmh_connection_status).grid(
            row=1, column=2, columnspan=3, sticky="w", padx=8
        )

        compose = ttk.LabelFrame(self.bmh_tab, text="Broadcast Action / Ticker Text", padding=8)
        compose.pack(fill="both", expand=True, pady=8)
        self.bmh_hazard = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Label(compose, text="Hazard").pack(anchor="w")
        ttk.Combobox(compose, textvariable=self.bmh_hazard, values=HAZARDS, width=48).pack(anchor="w", pady=3)
        ttk.Label(compose, text="Ticker / local preview text").pack(anchor="w")
        self.ticker_editor = ScrolledText(compose, height=8, wrap="word")
        self.ticker_editor.pack(fill="both", expand=True, pady=4)
        self.ticker_editor.insert("1.0", "Enter a clearly labelled local test or informational ticker message.")
        actions = ttk.Frame(compose)
        actions.pack(fill="x", pady=4)
        ttk.Button(actions, text="UPDATE PERIODIC SCROLL (LOCAL)", command=self.queue_bmh_message).pack(side="left")
        ttk.Button(actions, text="PREVIEW MESSAGE", command=self.preview_bmh_message).pack(side="left", padx=6)
        ttk.Button(actions, text="OPEN EAS TOOLS (LAB ONLY)", command=self.open_eas_tools).pack(side="right")

        active = ttk.LabelFrame(self.bmh_tab, text="Configured Simulated Transmitters", padding=8)
        active.pack(fill="x")
        self.bmh_tree = ttk.Treeview(active, columns=("location", "frequency", "state"), show="headings", height=3)
        for column, label, width in (
            ("location", "Location", 260), ("frequency", "Configured MHz", 140), ("state", "Status", 400)
        ):
            self.bmh_tree.heading(column, text=label)
            self.bmh_tree.column(column, width=width, anchor="w")
        self.bmh_tree.pack(fill="x")
        for station in self.stations:
            self.bmh_tree.insert(
                "", "end", iid=station.station_id,
                values=(station.location, station.frequency_mhz or "—", "SIMULATED / NOT RF-CONTROLLED")
            )

    def _build_station_controller(self) -> None:
        ttk.Label(
            self.station_tab,
            text="Station controller — local SAPI audio only. No connection to an RF transmitter is made.",
            foreground="#a12d2d",
        ).pack(anchor="w", pady=(0, 8))
        row = ttk.Frame(self.station_tab)
        row.pack(fill="x")
        self.controller_station = tk.StringVar(value=self.stations[0].station_id)
        self.controller_voice = tk.StringVar(value=str(self.settings.get("default_voice", "David")))
        self.controller_mode = tk.StringVar(value="General")
        ttk.Label(row, text="Station").pack(side="left")
        ttk.Combobox(
            row, textvariable=self.controller_station,
            values=[station.station_id for station in self.stations], state="readonly", width=12
        ).pack(side="left", padx=5)
        ttk.Label(row, text="Voice").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            row, textvariable=self.controller_voice,
            values=("Paul", "David", "Zira"), state="readonly", width=14
        ).pack(side="left", padx=5)
        ttk.Label(row, text="Operational mode").pack(side="left", padx=(12, 0))
        ttk.Combobox(
            row, textvariable=self.controller_mode, values=MODES, state="readonly", width=28
        ).pack(side="left", padx=5)

        controls = ttk.Frame(self.station_tab)
        controls.pack(fill="x", pady=12)
        ttk.Button(controls, text="START LOCAL AUDIO LOOP", command=self.start_audio_loop).pack(side="left")
        ttk.Button(controls, text="STOP LOOP", command=self.stop_audio_loop).pack(side="left", padx=6)
        ttk.Button(controls, text="READ CURRENT TIME", command=self.read_current_time).pack(side="left", padx=6)
        ttk.Button(controls, text="READ LATEST NWS SUMMARY", command=self.read_latest_summary).pack(side="left", padx=6)
        self.controller_status = tk.StringVar(value="Audio loop stopped.")
        ttk.Label(self.station_tab, textvariable=self.controller_status, wraplength=1000).pack(
            anchor="w", pady=6
        )

        manual = ttk.LabelFrame(self.station_tab, text="Manual Local Voice Message", padding=8)
        manual.pack(fill="both", expand=True, pady=8)
        self.voice_text = ScrolledText(manual, height=10, wrap="word")
        self.voice_text.pack(fill="both", expand=True)
        self.voice_text.insert("1.0", "Type a local information message to preview with the selected voice.")
        ttk.Button(manual, text="READ NOW (LOCAL)", command=self.read_manual_message).pack(
            anchor="e", pady=(6, 0)
        )

    def _build_live_queue(self) -> None:
        controls = ttk.Frame(self.queue_tab)
        controls.pack(fill="x")
        ttk.Label(
            controls,
            text="Queue items are retained in memory for this session. They are not sent to station transmitters.",
            foreground="#a12d2d",
        ).pack(side="left")
        ttk.Button(controls, text="REFRESH", command=self.refresh_live_queue).pack(side="right")
        self.queue_tree = ttk.Treeview(
            self.queue_tab, columns=("station", "hazard", "created", "message"), show="headings", height=18
        )
        for column, label, width in (
            ("station", "Station", 100),
            ("hazard", "Hazard / Type", 240),
            ("created", "Created (UTC)", 190),
            ("message", "Message", 600),
        ):
            self.queue_tree.heading(column, text=label)
            self.queue_tree.column(column, width=width, anchor="w")
        self.queue_tree.pack(fill="both", expand=True, pady=8)

    def _build_settings(self) -> None:
        panel = ttk.LabelFrame(self.settings_tab, text="Application / integration settings", padding=10)
        panel.pack(fill="x", anchor="n")
        self.voice_setting = tk.StringVar(value=str(self.settings.get("default_voice", "David")))
        self.voicetext_path = tk.StringVar(value=str(self.settings.get("voicetext_exe", "")))
        self.nws_agent = tk.StringVar(value=str(self.settings.get("nws_user_agent", "")))
        self.refresh_interval = tk.IntVar(value=int(self.settings.get("refresh_seconds", 300)))
        ttk.Label(panel, text="Default voice").grid(row=0, column=0, sticky="w", pady=5)
        ttk.Combobox(panel, textvariable=self.voice_setting, values=("Paul", "David", "Zira"), state="readonly").grid(
            row=0, column=1, sticky="w", padx=6
        )
        ttk.Label(panel, text="VoiceText editor executable").grid(row=1, column=0, sticky="w", pady=5)
        ttk.Entry(panel, textvariable=self.voicetext_path, width=74).grid(row=1, column=1, sticky="ew", padx=6)
        ttk.Button(panel, text="BROWSE", command=self.browse_voicetext).grid(row=1, column=2)
        ttk.Label(panel, text="NWS User-Agent (include contact information)").grid(
            row=2, column=0, sticky="w", pady=5
        )
        ttk.Entry(panel, textvariable=self.nws_agent, width=74).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6)
        ttk.Label(panel, text="Refresh seconds").grid(row=3, column=0, sticky="w", pady=5)
        ttk.Spinbox(panel, from_=60, to=3600, textvariable=self.refresh_interval, width=10).grid(
            row=3, column=1, sticky="w", padx=6
        )
        ttk.Button(panel, text="SAVE SETTINGS", command=self.save_settings).grid(
            row=4, column=1, sticky="w", pady=10
        )
        panel.columnconfigure(1, weight=1)
        notes = (
            "Stations and coverage are configured in config/stations.json. "
            "Each station has its own IANA timezone; both supplied Northwest Indiana examples default to America/Chicago. "
            "The VoiceText VTEditor executable is treated as a manual editor launch target until its supported automation "
            "interface is confirmed. David and Zira use installed Windows SAPI voices."
        )
        ttk.Label(self.settings_tab, text=notes, wraplength=1000, justify="left").pack(anchor="w", pady=12)

    def _refresh_station_rows(self) -> None:
        for item in self.station_tree.get_children():
            self.station_tree.delete(item)
        for station in self.stations:
            local_clock = station.local_time().strftime("%a %I:%M:%S %p %Z")
            data = self.station_data.get(station.station_id, {})
            observation = data.get("observation") or {}
            description = observation.get("textDescription") or "Awaiting NWS observation"
            self.station_tree.insert(
                "", "end", iid=station.station_id,
                values=(
                    f"{station.station_id} — {station.location}",
                    f"{station.frequency_mhz:.3f}" if station.frequency_mhz else "—",
                    local_clock,
                    description,
                    "LIVE" if data else "NOT LOADED",
                ),
            )

    def refresh_weather(self) -> None:
        self.status_var.set("Retrieving current NWS data…")
        self._refresh_station_rows()

        def worker() -> None:
            for station in self.stations:
                try:
                    result = self.nws.fetch_station(station)
                    self.ui_queue.put(("station_result", (station, result)))
                except Exception as exc:
                    self.ui_queue.put(("station_error", (station.station_id, str(exc))))
            self.ui_queue.put(("refresh_done", None))

        threading.Thread(target=worker, name="LOTWPS-NWS-refresh", daemon=True).start()

    def _poll_ui_queue(self) -> None:
        try:
            while True:
                kind, payload = self.ui_queue.get_nowait()
                if kind == "station_result":
                    station, result = payload
                    self.station_data[station.station_id] = result
                    self.all_alerts.extend(result.get("alerts", []))
                    self._render_alerts()
                    self._refresh_station_rows()
                elif kind == "station_error":
                    station_id, error = payload
                    self.status_var.set(f"{station_id}: NWS error — {error}")
                elif kind == "refresh_done":
                    self.status_var.set("NWS refresh complete. Data reflects the API response time.")
                elif kind == "broadcast_status":
                    self.controller_status.set(str(payload))
                    self.status_var.set(str(payload))
        except queue.Empty:
            pass
        self.root.after(200, self._poll_ui_queue)

    def _render_alerts(self) -> None:
        for item in self.alert_tree.get_children():
            self.alert_tree.delete(item)
        unique = {alert.identifier: alert for alert in self.all_alerts if alert.identifier}
        alerts = sort_alerts(list(unique.values()))
        for index, alert in enumerate(alerts):
            priority = AlertPriority(alert.priority).name
            self.alert_tree.insert(
                "", "end", iid=str(index),
                values=(priority, alert.event, alert.area, alert.expires, alert.severity),
            )

    def generate_header(self) -> None:
        try:
            header = make_wmo_header(self.header_type.get(), self.cccc.get(), self.bbb.get())
            product_id = make_product_id(self.category.get(), self.designator.get())
        except ValueError as exc:
            messagebox.showerror("Invalid header", str(exc))
            return
        self.header_preview.set(f"{header}    PRODUCT: {product_id}    ADDRESSEE: {self.addressee.get().upper()}")
        self.editor.insert(
            "1.0",
            f"DRAFT ONLY — NOT AN OFFICIAL NWS PRODUCT\n{header}\n"
            f"PRODUCT: {product_id}    ADDRESSEE: {self.addressee.get().upper()}\n\n",
        )

    def _show_editor_menu(self, event: tk.Event) -> None:
        self.editor.mark_set(tk.INSERT, f"@{event.x},{event.y}")
        self.editor_menu.tk_popup(event.x_root, event.y_root)

    def add_segment(self) -> None:
        self.editor.insert(tk.INSERT, "\n\n[NEW SEGMENT]\n")
        self.editor.focus_set()

    def edit_segment(self) -> None:
        try:
            selected = self.editor.get("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Edit Segment", "Select the segment text first.")
            return
        replacement = simpledialog.askstring("Edit Segment", "Edit selected segment:", initialvalue=selected)
        if replacement is not None:
            self.editor.delete("sel.first", "sel.last")
            self.editor.insert(tk.INSERT, replacement)

    def remove_segment(self) -> None:
        try:
            self.editor.delete("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Remove Segment", "Select the segment text first.")

    def combine_segments(self) -> None:
        try:
            selected = self.editor.get("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Combine Segments", "Select the adjacent segment text to combine.")
            return
        combined = " ".join(line.strip() for line in selected.splitlines() if line.strip())
        self.editor.delete("sel.first", "sel.last")
        self.editor.insert(tk.INSERT, combined)

    def queue_workstation_message(self) -> None:
        selected = self.editor.get("1.0", "end-1c").strip()
        if not selected:
            messagebox.showwarning("Empty message", "Enter message text first.")
            return
        if self.target_vars["BMH local queue"].get():
            self.bmh_queue.add(self.bmh_station.get(), self.category.get(), selected)
            self.refresh_live_queue()
        not_connected = [
            name for name in ("Email (not connected)", "IEMBOT (not connected)", "Websites & outlets (not connected)")
            if self.target_vars[name].get()
        ]
        if not_connected:
            messagebox.showinfo(
                "Dispatch adapters not configured",
                "The selected external destinations are recorded as intent only; no message was sent to: "
                + ", ".join(not_connected),
            )
        else:
            messagebox.showinfo("Local queue", "Draft added to the in-memory local BMH queue only.")

    def save_text(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save draft text", defaultextension=".txt",
            filetypes=(("Text files", "*.txt"), ("All files", "*.*")),
        )
        if path:
            try:
                with open(path, "w", encoding="utf-8", newline="\n") as stream:
                    stream.write(self.editor.get("1.0", "end-1c"))
                self.status_var.set(f"Saved draft to {path}")
            except OSError as exc:
                messagebox.showerror("Save failed", str(exc))

    def build_warning_draft(self) -> None:
        body = self.warn_body.get("1.0", "end-1c").strip()
        area = self.warn_area.get().strip()
        if not body or not area:
            messagebox.showwarning("Incomplete draft", "Add affected-area text and message content.")
            return
        draft_body = (
            f"{self.warn_hazard.get().upper()}\n"
            f"AFFECTED AREA (USER-ENTERED): {area}\n"
            f"EXPIRATION (USER-ENTERED): {self.warn_expiration.get()}\n\n"
            f"{body}\n"
        )
        self.category.set("SVR" if "Thunderstorm" in self.warn_hazard.get() else "TOR" if "Tornado" in self.warn_hazard.get() else "SPS")
        draft = build_product_draft(draft_body, self.category.get(), "LOT", "ALL")
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", draft)
        self.notebook.select(self.workstation_tab)

    def queue_bmh_message(self) -> None:
        text = self.ticker_editor.get("1.0", "end-1c").strip()
        if not text:
            messagebox.showwarning("Empty ticker", "Enter ticker text first.")
            return
        self.bmh_queue.add(self.bmh_station.get(), self.bmh_hazard.get(), text)
        self.refresh_live_queue()
        self.status_var.set("Ticker text added to the local in-memory preview queue; nothing was transmitted.")

    def preview_bmh_message(self) -> None:
        text = self.ticker_editor.get("1.0", "end-1c").strip()
        messagebox.showinfo("Local ticker preview", f"{self.bmh_hazard.get()}\n\n{text}\n\nLOCAL PREVIEW ONLY — NOT TRANSMITTED")

    def check_bmh_connection(self) -> None:
        host = self.bmh_host.get().strip()
        try:
            port = int(self.bmh_port.get())
        except (ValueError, tk.TclError):
            messagebox.showerror("Invalid endpoint", "Port must be an integer from 1 to 65535.")
            return
        if not host or not 1 <= port <= 65535:
            messagebox.showerror("Invalid endpoint", "Enter a host and a port from 1 to 65535.")
            return
        ok, message = check_tcp_reachability(host, port)
        self.bmh_connection_status.set(message)
        self.status_var.set("TCP endpoint reachable." if ok else "TCP endpoint not reachable.")

    def refresh_live_queue(self) -> None:
        for item in self.queue_tree.get_children():
            self.queue_tree.delete(item)
        for index, item in enumerate(self.bmh_queue.items()):
            self.queue_tree.insert(
                "", "end", iid=str(index),
                values=(item.station_id, item.hazard, item.created_at, item.text[:240]),
            )

    def _get_selected_station(self) -> Station:
        station_id = self.controller_station.get()
        for station in self.stations:
            if station.station_id == station_id:
                return station
        return self.stations[0]

    def start_audio_loop(self) -> None:
        if self.broadcast and self.broadcast.running:
            messagebox.showinfo("Already running", "The local audio briefing loop is already running.")
            return
        station = self._get_selected_station()
        self.broadcast = BroadcastLoop(
            self.nws,
            self.speech,
            lambda message: self.ui_queue.put(("broadcast_status", message)),
            int(self.settings.get("broadcast_interval_seconds", 900)),
        )
        try:
            self.broadcast.start(station, self.controller_voice.get())
        except Exception as exc:
            messagebox.showerror("Unable to start loop", str(exc))
            return
        self.controller_status.set(f"{station.station_id}: local audio briefing loop started.")

    def stop_audio_loop(self) -> None:
        if self.broadcast:
            self.broadcast.stop()
        self.controller_status.set("Local audio briefing loop stopped.")

    def read_current_time(self) -> None:
        station = self._get_selected_station()
        text = f"The local time at {station.location} is {station.local_time():%I:%M %p %Z}."
        self._read_text(text)

    def read_latest_summary(self) -> None:
        station = self._get_selected_station()
        data = self.station_data.get(station.station_id)
        if not data:
            messagebox.showinfo("No data", "Refresh NWS data first.")
            return
        from .workstation import build_broadcast_script
        text = build_broadcast_script(
            station, data.get("alerts", []), data.get("forecast_periods", []), self.cycle_number
        )
        self.cycle_number += 1
        self._read_text(text)

    def read_manual_message(self) -> None:
        self._read_text(self.voice_text.get("1.0", "end-1c").strip())

    def _read_text(self, text: str) -> None:
        voice = self.controller_voice.get()
        def worker() -> None:
            try:
                result = self.speech.speak(text, voice)
                self.ui_queue.put(("broadcast_status", result))
            except Exception as exc:
                self.ui_queue.put(("broadcast_status", str(exc)))
        threading.Thread(target=worker, name="LOTWPS-SAPI", daemon=True).start()

    def browse_voicetext(self) -> None:
        path = filedialog.askopenfilename(
            title="Select VoiceText Editor executable",
            filetypes=(("Windows applications", "*.exe"), ("All files", "*.*")),
        )
        if path:
            self.voicetext_path.set(path)

    def save_settings(self) -> None:
        self.settings.update({
            "default_voice": self.voice_setting.get(),
            "voicetext_exe": self.voicetext_path.get().strip(),
            "nws_user_agent": self.nws_agent.get().strip(),
            "refresh_seconds": int(self.refresh_interval.get()),
            "bmh_target_host": self.bmh_host.get().strip(),
            "bmh_target_port": int(self.bmh_port.get()),
        })
        if not self.settings["nws_user_agent"]:
            messagebox.showerror("Missing User-Agent", "Set a descriptive NWS User-Agent with contact information.")
            return
        try:
            write_json(APP_SETTINGS_FILE, self.settings)
            self.nws = NWSClient(self.settings["nws_user_agent"])
            self.speech = SpeechEngine(self.settings["voicetext_exe"])
            self.status_var.set(f"Settings saved to {APP_SETTINGS_FILE}")
        except Exception as exc:
            messagebox.showerror("Settings not saved", str(exc))

    @staticmethod
    def open_eas_tools() -> None:
        messagebox.showwarning(
            "EAS Tools — lab/testing use only",
            "EAS Tools is an independent browser toolkit. LOTWPS does not transmit SAME headers, "
            "EAS Attention Signals, 1050 Hz alert tones, or EOM signals. Do not distribute EAS "
            "tones or headers over broadcast, radio, cable, PA, or other public systems except "
            "as specifically authorized by applicable rules."
        )
        webbrowser.open("https://eas.tools/")

    def close(self) -> None:
        if self.broadcast:
            self.broadcast.stop()
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    try:
        LOTWPSApp(root)
    except Exception as exc:
        messagebox.showerror("LOTWPS startup error", str(exc))
        root.destroy()
        raise
    root.mainloop()


if __name__ == "__main__":
    main()
