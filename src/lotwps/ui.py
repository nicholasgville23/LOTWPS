from __future__ import annotations

import struct
import tkinter as tk
import wave
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

from .broadcast import BroadcastLoop, LocalQueue, QueueItem
from .models import Station
from .network import BMHNetwork
from .nws_client import NWSClient
from .products import alert_summary, alerts_from_geojson, forecast_text
from .priority import sort_alerts
from .regional import alert_matches_station, station_local_time
from .same import EVENT_CODES, build_same_header, write_test_alert_wav, _append_tone
from .storage import JSONStore
from .tts import VoiceEngine


MODES = [
    "WINTER WEATHER", "FLOODING", "SEVERE WEATHER", "SEVERE WEATHER POSSIBLE",
    "OFF THE AIR", "STATION ID ONLY", "CURRENT TIME ONLY", "GENERAL",
    "ZONE FORECAST", "SEVERE WEATHER AND ALERT SUMMARY",
]
HAZARDS = [
    "Severe Thunderstorm Warning", "Tornado Warning", "Tornado Emergency",
    "Flash Flood Warning", "Special Weather Statement", "Extreme Wind Warning",
    "Required Weekly Test", "Required Monthly Test",
]


class LOTWPSApp:
    """Tkinter front end for local weather processing and simulated BMH nodes."""

    def __init__(self, root: tk.Tk, config: dict):
        self.root, self.config = root, config
        self.root.title("KLOT LOTIEM TEXT WORKSTATION / BMH Network")
        self.root.geometry("1360x850")
        self.stations = [Station.from_dict(x) for x in config["network"]["stations"]]
        self.station_by_id = {x.station_id: x for x in self.stations}
        self.selected_station = tk.StringVar(value=self.stations[0].station_id if self.stations else "KLOT")
        self.network = BMHNetwork(config["network"]["stations"])
        self.queue, self.alerts = LocalQueue(), []
        self.store = JSONStore(Path("data") / "lotwps_state.json")
        self.broadcast = BroadcastLoop(self.queue, self._play_local_item)
        self._build()
        self._refresh_queue()
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        bar = ttk.Frame(self.root, padding=8)
        bar.pack(fill="x")
        ttk.Label(bar, text="KLOT LOTIEM TEXT WORKSTATION", font=("Segoe UI", 17, "bold")).pack(side="left")
        ttk.Label(bar, text="LOTWPS • LOTIEM • BMH | SIMULATION / LOCAL AUDIO ONLY", foreground="#9a4500").pack(side="right")
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=8, pady=8)
        self.text_tab, self.bmh_tab = ttk.Frame(self.tabs, padding=8), ttk.Frame(self.tabs, padding=8)
        self.awips_tab, self.settings_tab = ttk.Frame(self.tabs, padding=8), ttk.Frame(self.tabs, padding=8)
        for frame, title in [(self.text_tab, "Text Workstation"), (self.bmh_tab, "BMH Network"),
                             (self.awips_tab, "AWIPS / WarnGen"), (self.settings_tab, "Settings / Status")]:
            self.tabs.add(frame, text=title)
        self._build_text()
        self._build_bmh()
        self._build_awips()
        self._build_settings()

    def _build_text(self):
        self.text_tab.columnconfigure(0, weight=3)
        self.text_tab.columnconfigure(1, weight=1)
        self.text_tab.rowconfigure(1, weight=1)
        header = ttk.LabelFrame(self.text_tab, text="AWIPS / WMO Header Block", padding=7)
        header.grid(row=0, column=0, columnspan=2, sticky="ew", pady=(0, 8))
        self.header_vars = {}
        for index, (name, default) in enumerate([
            ("TTAAii", "WHUS53"), ("CCCC", "KLOT"), ("BBB", "NOR"),
            ("Version", "A"), ("WSFO ID", "CHI"), ("Product", "LOT"), ("Addressee", "ALL")
        ]):
            ttk.Label(header, text=name).grid(row=0, column=index, sticky="w", padx=3)
            var = tk.StringVar(value=default)
            self.header_vars[name] = var
            ttk.Entry(header, textvariable=var, width=11).grid(row=1, column=index, padx=3, sticky="ew")
        editor = ttk.LabelFrame(self.text_tab, text="New Text Message / Segment Editor", padding=8)
        editor.grid(row=1, column=0, sticky="nsew", padx=(0, 8))
        editor.rowconfigure(2, weight=1)
        editor.columnconfigure(0, weight=1)
        line = ttk.Frame(editor)
        line.grid(row=0, column=0, sticky="ew")
        self.hazard_var = tk.StringVar(value="Special Weather Statement")
        ttk.Label(line, text="Hazard:").pack(side="left")
        ttk.Combobox(line, textvariable=self.hazard_var, values=HAZARDS, state="readonly", width=31).pack(side="left", padx=5)
        self.product_var = tk.StringVar(value="SVSLOT")
        ttk.Label(line, text="Product ID:").pack(side="left")
        ttk.Entry(line, textvariable=self.product_var, width=12).pack(side="left")
        ttk.Label(editor, text="Message text — right-click for segment actions").grid(row=1, column=0, sticky="w", pady=4)
        self.editor = tk.Text(editor, wrap="word", undo=True)
        self.editor.grid(row=2, column=0, sticky="nsew")
        self.editor.insert("1.0", "THIS IS A SIMULATED DEVELOPMENT TEST MESSAGE. NOT AN OFFICIAL WARNING.")
        self.editor.bind("<Button-3>", self._segment_menu)
        actions = ttk.Frame(editor)
        actions.grid(row=3, column=0, sticky="ew", pady=6)
        for title, method in [("Add Segment", self._add_segment), ("Edit Segment", self._edit_segment),
                              ("Remove Segment", self._remove_segment), ("Combine Segment", self._combine_segment),
                              ("Build Hazard Segment", self._hazard_segment), ("Add Header", self._add_header)]:
            ttk.Button(actions, text=title, command=method).pack(side="left", padx=2)
        side = ttk.Frame(self.text_tab)
        side.grid(row=1, column=1, sticky="nsew")
        dispatch = ttk.LabelFrame(side, text="New Text Message Options", padding=7)
        dispatch.pack(fill="x")
        self.send_vars = {x: tk.BooleanVar(value=(x == "BMH")) for x in ("BMH", "Email", "IEMBOT", "Websites & Outlets")}
        for key, var in self.send_vars.items():
            ttk.Checkbutton(dispatch, text=f"Send to {key}", variable=var).pack(anchor="w")
        ttk.Label(dispatch, text="External destinations are not connected in this starter.", foreground="#9a4500", wraplength=260).pack(anchor="w", pady=3)
        ttk.Button(dispatch, text="Enter / Queue for BMH", command=self._dispatch).pack(fill="x", pady=2)
        for title, method in [("Build 7-day Zone Forecast", self._build_forecast),
                              ("Build HWO", self._build_hwo), ("Refresh Active Alerts", self._refresh_alerts),
                              ("Insert Alert Summary", self._insert_alert_summary), ("Local Time / Station ID", self._build_time_id)]:
            ttk.Button(dispatch, text=title, command=method).pack(fill="x", pady=2)
        voice = ttk.Frame(dispatch)
        voice.pack(fill="x", pady=3)
        self.voice_var = tk.StringVar(value="paul")
        ttk.Label(voice, text="Voice").pack(side="left")
        ttk.Combobox(voice, textvariable=self.voice_var, values=["paul", "david", "zira"], state="readonly", width=8).pack(side="left", padx=3)
        ttk.Button(voice, text="Synthesize / Queue WAV", command=self._synthesize).pack(side="left")
        ttk.Button(dispatch, text="View Sent / Queued Messages", command=self._view_sent).pack(fill="x", pady=2)
        active = ttk.LabelFrame(side, text="Active Alerts", padding=5)
        active.pack(fill="both", expand=True, pady=(8, 0))
        self.active_list = tk.Listbox(active)
        self.active_list.pack(fill="both", expand=True)

    def _build_bmh(self):
        self.bmh_tab.columnconfigure(0, weight=1)
        self.bmh_tab.columnconfigure(1, weight=2)
        self.bmh_tab.rowconfigure(0, weight=1)
        left = ttk.LabelFrame(self.bmh_tab, text="Active Transmitters / Global Network Controls", padding=7)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.station_tree = ttk.Treeview(left, columns=("status", "freq", "location"), show="headings")
        for col, width in [("status", 135), ("freq", 85), ("location", 180)]:
            self.station_tree.heading(col, text=col.title())
            self.station_tree.column(col, width=width)
        self.station_tree.pack(fill="both", expand=True)
        for station in self.stations:
            freq = f"{station.frequency_mhz:.3f} MHz" if station.frequency_mhz else "Not set"
            self.station_tree.insert("", "end", iid=station.station_id, values=("SIMULATED ONLINE", freq, station.location))
        self.station_tree.bind("<<TreeviewSelect>>", self._station_selected)
        ttk.Label(left, text="Station controls are in-memory simulation only. No IP sockets or RF hardware are contacted.", foreground="#9a4500", wraplength=330).pack(anchor="w", pady=6)
        self.station_status = ttk.Label(left, text="Select a station")
        self.station_status.pack(anchor="w")
        for action in ("START TX", "STOP TX", "NEXT PRODUCT", "RESTART SERVICE"):
            ttk.Button(left, text=action, command=lambda value=action: self._station_command(value)).pack(fill="x", pady=2)
        right = ttk.Frame(self.bmh_tab)
        right.grid(row=0, column=1, sticky="nsew")
        builder = ttk.LabelFrame(right, text="Weather Message / SAME-EAS Builder — TEST ONLY", padding=7)
        builder.pack(fill="x")
        row = ttk.Frame(builder)
        row.pack(fill="x")
        self.bmh_hazard = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Label(row, text="Hazard:").pack(side="left")
        ttk.Combobox(row, textvariable=self.bmh_hazard, values=HAZARDS, state="readonly", width=30).pack(side="left", padx=4)
        self.duration_var = tk.StringVar(value="15")
        ttk.Label(row, text="Duration:").pack(side="left")
        ttk.Entry(row, textvariable=self.duration_var, width=6).pack(side="left")
        ttk.Label(builder, text="Warning Message / Call to Action Text:").pack(anchor="w", pady=(6, 2))
        self.bmh_message = tk.Text(builder, height=4, wrap="word")
        self.bmh_message.pack(fill="x")
        self.bmh_message.insert("1.0", "THIS IS A REQUIRED TEST MESSAGE. NO REAL-WORLD WARNING IS IN EFFECT.")
        row2 = ttk.Frame(builder)
        row2.pack(fill="x", pady=4)
        ttk.Button(row2, text="Update Periodic Scroll", command=self._update_ticker).pack(side="left", padx=2)
        ttk.Button(row2, text="SEND SAME ALERT (TEST FILE)", command=self._send_same_test).pack(side="left", padx=2)
        ttk.Button(row2, text="1050 HZ", command=self._tone_test).pack(side="left", padx=2)
        ttk.Button(row2, text="SILENT INTERRUPT", command=self._stop_loop).pack(side="left", padx=2)
        self.ticker_var = tk.StringVar(value="LOTWPS / LOTIEM DEVELOPMENT NETWORK — SIMULATED STATUS")
        ttk.Entry(builder, textvariable=self.ticker_var).pack(fill="x", pady=3)
        modes = ttk.LabelFrame(right, text="Broadcast Cycles / Operating Mode", padding=7)
        modes.pack(fill="x", pady=(8, 0))
        self.mode_var = tk.StringVar(value="GENERAL")
        ttk.Combobox(modes, textvariable=self.mode_var, values=MODES, state="readonly", width=34).pack(side="left")
        ttk.Button(modes, text="NEW MODE", command=self._set_mode).pack(side="left", padx=3)
        ttk.Button(modes, text="RESET MODE", command=lambda: self.mode_var.set("GENERAL")).pack(side="left", padx=3)
        queue_box = ttk.LabelFrame(right, text="Live Queue / Manual Local Audio Playout", padding=7)
        queue_box.pack(fill="both", expand=True, pady=(8, 0))
        self.queue_tree = ttk.Treeview(queue_box, columns=("product", "title", "status"), show="headings", height=7)
        for col, width in [("product", 100), ("title", 330), ("status", 100)]:
            self.queue_tree.heading(col, text=col.title())
            self.queue_tree.column(col, width=width)
        self.queue_tree.pack(fill="both", expand=True)
        row3 = ttk.Frame(queue_box)
        row3.pack(fill="x", pady=4)
        ttk.Button(row3, text="START LOCAL LOOP", command=self._start_loop).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(row3, text="STOP LOOP", command=self._stop_loop).pack(side="left", expand=True, fill="x", padx=2)
        ttk.Button(row3, text="REFRESH NOW", command=self._refresh_queue).pack(side="left", expand=True, fill="x", padx=2)

    def _build_awips(self):
        self.awips_tab.columnconfigure(0, weight=1)
        self.awips_tab.columnconfigure(1, weight=1)
        self.awips_tab.rowconfigure(2, weight=1)
        ttk.Label(self.awips_tab, text="KLOT AWIPS / WarnGen / WatchGen Tools", font=("Segoe UI", 14, "bold")).grid(row=0, column=0, columnspan=2, sticky="w")
        ttk.Label(self.awips_tab, text="Enter LAT,LON polygon vertices. This is a local annotation helper, not a radar feed or operational WarnGen.", wraplength=900).grid(row=1, column=0, columnspan=2, sticky="w", pady=5)
        self.polygon_text = tk.Text(self.awips_tab, height=12)
        self.polygon_text.grid(row=2, column=0, sticky="nsew", padx=(0, 8))
        self.polygon_text.insert("1.0", "41.8000,-87.9000\n41.8000,-87.5000\n41.5000,-87.5000\n41.5000,-87.9000")
        tools = ttk.LabelFrame(self.awips_tab, text="WarnGen / WatchGen", padding=8)
        tools.grid(row=2, column=1, sticky="nsew")
        self.polygon_name = tk.StringVar(value="NEW STORM POLYGON")
        ttk.Label(tools, text="Polygon name").pack(anchor="w")
        ttk.Entry(tools, textvariable=self.polygon_name).pack(fill="x")
        self.polygon_kind = tk.StringVar(value="Single Storm")
        ttk.Radiobutton(tools, text="Single Storm", variable=self.polygon_kind, value="Single Storm").pack(anchor="w")
        ttk.Radiobutton(tools, text="Line of Storms", variable=self.polygon_kind, value="Line of Storms").pack(anchor="w")
        ttk.Button(tools, text="CREATE / SAVE POLYGON", command=self._save_polygon).pack(fill="x", pady=5)
        ttk.Button(tools, text="RESTORE UI", command=lambda: self.tabs.select(self.text_tab)).pack(fill="x", pady=5)
        self.polygon_list = tk.Listbox(self.awips_tab, height=8)
        self.polygon_list.grid(row=3, column=0, columnspan=2, sticky="nsew", pady=5)

    def _build_settings(self):
        ttk.Label(self.settings_tab, text="Framework Status", font=("Segoe UI", 14, "bold")).pack(anchor="w")
        info = [
            "LOTWPS: sender-side weather processing and forecaster workstation.",
            "LOTIEM: receiving-side message ledger and future approved distribution gateway.",
            "Office: " + self.config["app"].get("office", "LOT"),
            "Time zone: " + self.config["app"].get("timezone", "America/Chicago") + " (CST/CDT by IANA ZoneInfo).",
            "NWS User-Agent: " + self.config["nws"].get("user_agent", "not set"),
            "Network transport: SIMULATION ONLY. No TCP listener/client is enabled.",
            "RF transmit and live EAS/IPAWS distribution: NOT IMPLEMENTED.",
            "Voice profiles: Paul, David, Zira; depends on the host's installed SAPI voices.",
            "VTEditor_ENG.exe may be GUI-only; configure a documented VoiceText CLI/SDK wrapper if available.",
            "Climate normals/records are not fabricated; configure verified station values in config.json.",
        ]
        text = tk.Text(self.settings_tab, wrap="word")
        text.pack(fill="both", expand=True, pady=5)
        text.insert("1.0", "\n\n".join(info))
        text.configure(state="disabled")

    def _client(self):
        nws = self.config["nws"]
        return NWSClient(nws["base_url"], nws["user_agent"], nws["timeout_seconds"])

    def _selected(self):
        return self.station_by_id.get(self.selected_station.get())

    def _segment_menu(self, event):
        menu = tk.Menu(self.root, tearoff=False)
        for label, method in [("Add Segment", self._add_segment), ("Edit Segment", self._edit_segment),
                              ("Remove Segment", self._remove_segment), ("Combine Segment", self._combine_segment)]:
            menu.add_command(label=label, command=method)
        menu.tk_popup(event.x_root, event.y_root)

    def _add_segment(self):
        value = simpledialog.askstring("Add Segment", "Enter segment text:", parent=self.root)
        if value:
            self.editor.insert("insert", "\n\n" + value.strip())

    def _edit_segment(self):
        try:
            start, end = self.editor.index("sel.first"), self.editor.index("sel.last")
        except tk.TclError:
            messagebox.showinfo("Edit Segment", "Select the segment text first.")
            return
        value = simpledialog.askstring("Edit Segment", "Replacement text:", parent=self.root)
        if value is not None:
            self.editor.delete(start, end)
            self.editor.insert(start, value)

    def _remove_segment(self):
        try:
            self.editor.delete("sel.first", "sel.last")
        except tk.TclError:
            messagebox.showinfo("Remove Segment", "Select the segment text first.")

    def _combine_segment(self):
        value = " ".join(x.strip() for x in self.editor.get("1.0", "end-1c").splitlines() if x.strip())
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", value)

    def _hazard_segment(self):
        self.editor.insert("end", f"\n\n{self.hazard_var.get().upper()}. DRAFT ONLY — VERIFY SOURCE, EVENT, GEOGRAPHIC AREA, AND VALID TIME.")

    def _add_header(self):
        header = " ".join(f"{key}:{value.get()}" for key, value in self.header_vars.items())
        self.editor.insert("1.0", header + "\n\n")

    def _dispatch(self):
        station = self._selected()
        text = self.editor.get("1.0", "end-1c").strip()
        if not station or not text:
            messagebox.showwarning("Message", "Select a station and enter a message.")
            return
        item = QueueItem.create(self.product_var.get().strip() or "TEXT", self.hazard_var.get(), text, station_id=station.station_id)
        self.queue.add(item)
        selected_destinations = [name for name, var in self.send_vars.items() if var.get()]
        self.store.append("messages", {"product_id": item.product_id, "title": item.title, "text": text, "station_id": station.station_id, "destinations_selected": selected_destinations, "dispatch_status": "LOCAL QUEUE ONLY"})
        self._refresh_queue()
        messagebox.showinfo("Queued", "Draft saved to the local queue. External destinations are not connected.")

    def _build_forecast(self):
        station = self._selected()
        if not station or station.latitude is None or station.longitude is None:
            messagebox.showwarning("Coordinates", "Configure station coordinates in config.json.")
            return
        try:
            data = self._client().forecast_from_point(station.latitude, station.longitude)
            body = forecast_text(data, station.timezone, 14)
            self.product_var.set("ZFPLOT")
            self.editor.insert("end", "\n\nSEVEN-DAY ZONE FORECAST\n" + body)
        except Exception as exc:
            messagebox.showerror("Forecast", str(exc))

    def _build_hwo(self):
        try:
            data = self._client().latest_product("HWO", self.config["app"].get("office", "LOT"))
            body = data.get("properties", {}).get("productText", "") if data else ""
            if not body:
                messagebox.showinfo("HWO", "No HWO text was returned for this office.")
                return
            self.product_var.set("HWOLOT")
            self.editor.insert("end", "\n\nHAZARDOUS WEATHER OUTLOOK\n" + body)
        except Exception as exc:
            messagebox.showerror("HWO", str(exc))

    def _refresh_alerts(self):
        station = self._selected()
        if not station or station.latitude is None or station.longitude is None:
            messagebox.showwarning("Coordinates", "Configure station coordinates in config.json.")
            return
        try:
            data = self._client().active_alerts(station.latitude, station.longitude)
            alerts = alerts_from_geojson(data)
            allow = bool(self.config["region"].get("allow_routine_without_codes", True))
            self.alerts = [x for x in sort_alerts(alerts) if alert_matches_station(x, station, allow)]
            self.active_list.delete(0, "end")
            for alert in self.alerts:
                self.active_list.insert("end", f"{alert.priority.name}: {alert.event} — {alert.area_desc}")
            self.store.write({**self.store.read(), "alerts": [{"id": x.identifier, "event": x.event, "priority": x.priority.name, "area": x.area_desc} for x in self.alerts]})
        except Exception as exc:
            messagebox.showerror("NWS Alerts", str(exc))

    def _insert_alert_summary(self):
        self.product_var.set("ALERTSUM")
        self.editor.insert("end", "\n\n" + alert_summary(self.alerts))

    def _build_time_id(self):
        station = self._selected()
        if station:
            now = station_local_time(station)
            self.product_var.set("CURRENT_TIME")
            self.editor.insert("end", f"\n\nThis is {station.station_id}, serving {station.location}. The time is {now:%I:%M %p %Z}, {now:%A, %B %d, %Y}.")

    def _synthesize(self):
        station = self._selected()
        text = self.editor.get("1.0", "end-1c").strip()
        if not station or not text:
            return
        output = Path(self.config["broadcast"]["output_dir"]) / f"{station.station_id}_{self.voice_var.get()}_{datetime.now():%Y%m%d_%H%M%S}.wav"
        try:
            audio = VoiceEngine(self.config["voices"]).synthesize(text, output, self.voice_var.get())
            self.queue.add(QueueItem.create(self.product_var.get(), self.hazard_var.get(), text, str(audio), station.station_id))
            self._refresh_queue()
            messagebox.showinfo("Voice ready", f"Created local speech WAV:\n{audio}")
        except Exception as exc:
            messagebox.showerror("Voice synthesis", str(exc))

    def _view_sent(self):
        rows = self.store.read().get("messages", [])[-10:]
        value = "\n\n".join(f"{x.get('product_id')} — {x.get('title')}\n{x.get('text','')[:200]}" for x in rows)
        messagebox.showinfo("Sent / Queued", value or "No local messages have been stored.")

    def _station_selected(self, _event=None):
        selected = self.station_tree.selection()
        if selected:
            self.selected_station.set(selected[0])
            value = self.network.status[selected[0]]
            self.station_status.configure(text=f"{selected[0]} — {value.status} — {value.mode}")

    def _station_command(self, action):
        station = self.selected_station.get()
        try:
            status = self.network.command(station, action)
            self.station_status.configure(text=f"{station} — {status.status} — {status.mode}")
            self.station_tree.set(station, "status", status.status)
        except Exception as exc:
            messagebox.showerror("Station Controller", str(exc))

    def _update_ticker(self):
        self.store.append("audit", {"action": "UPDATE PERIODIC SCROLL", "text": self.ticker_var.get(), "mode": self.mode_var.get()})
        messagebox.showinfo("Ticker", "Ticker saved locally for the simulated network.")

    def _set_mode(self):
        try:
            status = self.network.set_mode(self.selected_station.get(), self.mode_var.get())
            self.station_status.configure(text=f"{status.station_id} — {status.status} — {status.mode}")
        except Exception as exc:
            messagebox.showerror("Mode", str(exc))

    def _send_same_test(self):
        station = self._selected()
        if not station:
            return
        hazard, speech = self.bmh_hazard.get(), self.bmh_message.get("1.0", "end-1c").strip()
        if not speech.upper().startswith("THIS IS A") and not speech.upper().startswith("TEST"):
            if not messagebox.askyesno("Test-only builder", "Message is not clearly labelled TEST. Continue creating a local test WAV?"):
                return
        try:
            header = build_same_header(hazard, station.same_fips, int(self.duration_var.get()), station_id=station.station_id)
            folder = Path(self.config["broadcast"]["output_dir"])
            speech_path = None
            try:
                speech_path = VoiceEngine(self.config["voices"]).synthesize(speech, folder / f"{station.station_id}_PAUL_TEST_SPEECH.wav", "paul")
            except Exception as voice_error:
                if not messagebox.askyesno("Paul voice unavailable", f"{voice_error}\n\nCreate SAME + tone + EOM without speech?"):
                    return
            output = folder / f"{station.station_id}_{EVENT_CODES.get(hazard,'TST')}_TEST.wav"
            write_test_alert_wav(output, header, spoken_wav=speech_path,
                                 sample_rate=int(self.config["broadcast"]["sample_rate"]),
                                 header_repeats=int(self.config["broadcast"]["header_repeats"]),
                                 eom_repeats=int(self.config["broadcast"]["eom_repeats"]),
                                 attention_tone_seconds=float(self.config["broadcast"]["attention_tone_seconds"]))
            self.queue.add(QueueItem.create(EVENT_CODES.get(hazard, "TEST"), hazard + " — TEST", speech, str(output), station.station_id))
            self._refresh_queue()
            self.store.append("audit", {"action": "GENERATED TEST SAME AUDIO", "station": station.station_id, "header": header, "file": str(output)})
            messagebox.showinfo("Test WAV created", f"{output}\n\nNo RF transmission or EAS distribution occurred.")
        except Exception as exc:
            messagebox.showerror("SAME test generator", str(exc))

    def _tone_test(self):
        station = self._selected()
        if not station:
            return
        import math
        import struct
        rate, seconds = int(self.config["broadcast"]["sample_rate"]), float(self.config["broadcast"]["attention_tone_seconds"])
        values = []
        _append_tone(values, 1050.0, seconds, rate)
        output = Path(self.config["broadcast"]["output_dir"]) / f"{station.station_id}_1050HZ_TEST.wav"
        output.parent.mkdir(parents=True, exist_ok=True)
        with wave.open(str(output), "wb") as target:
            target.setnchannels(1); target.setsampwidth(2); target.setframerate(rate)
            target.writeframes(struct.pack("<" + "h" * len(values), *values))
        messagebox.showinfo("1050 Hz test", f"Created local test WAV:\n{output}")

    def _refresh_queue(self):
        if not hasattr(self, "queue_tree"):
            return
        for row in self.queue_tree.get_children():
            self.queue_tree.delete(row)
        for item in self.queue.items():
            self.queue_tree.insert("", "end", iid=item.item_id, values=(item.product_id, item.title, item.status))
        self.root.after(1500, self._refresh_queue)

    def _play_local_item(self, item):
        if not item.audio_path:
            return
        path = Path(item.audio_path)
        if not path.exists():
            raise FileNotFoundError(path)
        try:
            import winsound
            winsound.PlaySound(str(path), winsound.SND_FILENAME | winsound.SND_SYNC)
        except ImportError as exc:
            raise RuntimeError("Windows WAV playback is used by this starter.") from exc

    def _start_loop(self):
        self.broadcast.start()
        messagebox.showinfo("Local playout", "Manual local audio loop started. Only queued WAV files make sound.")

    def _stop_loop(self):
        self.broadcast.stop()
        try:
            import winsound
            winsound.PlaySound(None, winsound.SND_PURGE)
        except ImportError:
            pass

    def _save_polygon(self):
        coordinates = []
        for line in self.polygon_text.get("1.0", "end-1c").splitlines():
            if not line.strip():
                continue
            try:
                lat, lon = map(float, [x.strip() for x in line.split(",")])
            except (ValueError, TypeError):
                messagebox.showerror("Polygon", f"Invalid coordinate: {line}")
                return
            if not (-90 <= lat <= 90 and -180 <= lon <= 180):
                messagebox.showerror("Polygon", f"Coordinate out of range: {line}")
                return
            coordinates.append([lat, lon])
        if len(coordinates) < 3:
            messagebox.showwarning("Polygon", "At least three coordinate pairs are required.")
            return
        data = self.store.read()
        data.setdefault("polygons", []).append({"name": self.polygon_name.get(), "kind": self.polygon_kind.get(), "coordinates": coordinates, "created_at": datetime.now().astimezone().isoformat()})
        self.store.write(data)
        self.polygon_list.insert("end", f"{self.polygon_name.get()} — {self.polygon_kind.get()} — {len(coordinates)} points")

    def close(self):
        self.broadcast.stop()
        self.root.destroy()
