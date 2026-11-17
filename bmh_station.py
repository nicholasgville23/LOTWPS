"""BMH Station Controller for WXJ75 / KBB58.

The full engineer's console for one transmitter: weather messages and the
SAME/EAS builder, transport controls, listening area, broadcast cycles, static
messages, the live queue, active alerts and the product catalog.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk

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
from lotwps.weather import WeatherModel

STATIC_KEYS = [
    "ADVANCE", "EMR_STATION_ID", "PREPAREDNESS_ACTIONS", "SLGT_STATION_ID",
    "OFF_AIR", "STATION_ID", "SHORT_ID", "LONG_ID", "SEVERE_MESSAGE",
    "CURRENT_TIME",
]

QUICK_READS = [
    ("STATION_ID", "STATION_ID"),
    ("CURRENT_TIME", "CURRENT_TIME"),
    ("SVR_STATION_ID", "SEVERE_MESSAGE"),
    ("SEVERE_MESSAGE", "SEVERE_MESSAGE"),
    ("NWSLOT", "NWSLOT"),
    ("SUMMARY", "SUMMARY"),
    ("EMR_STATION_ID", "EMR_STATION_ID"),
    ("PREPAREDNESS", "PREPAREDNESS_ACTIONS"),
]

EVENTS = [
    "Tornado Warning", "Tornado Emergency", "Severe Thunderstorm Warning",
    "Flash Flood Warning", "Extreme Wind Warning", "Special Weather Statement",
    "Severe Weather Statement", "Tornado Watch", "Severe Thunderstorm Watch",
    "Winter Storm Warning", "Winter Weather Advisory", "Blizzard Warning",
    "Ice Storm Warning", "High Wind Warning", "Wind Advisory",
    "Dense Fog Advisory", "Small Craft Advisory", "Gale Warning",
    "Excessive Heat Warning", "Heat Advisory",
    "Required Weekly Test", "Required Monthly Test",
]

DEFAULT_CALL_TO_ACTION = (
    "PRECAUTIONARY/PREPAREDNESS ACTIONS...\n\n"
    "A Tornado Warning has been issued for the listening area. Take shelter now in "
    "a basement or an interior room on the lowest floor of a sturdy building. "
    "Avoid windows. If you are outdoors, in a mobile home, or in a vehicle, move "
    "to the closest substantial shelter and protect yourself from flying debris."
)


class StationController:
    def __init__(self, master=None, station_id: str = "WXJ75", engine=None) -> None:
        self.settings = load_settings()
        self.store = alert_mod.store()
        self.station_id = station_id
        self.station = self.settings.station(station_id)
        self.parent = master

        if master is None:
            self.root = appkit.boot(
                f"BMH Station Controller  |  {station_id}",
                (1240, 820), (1060, 700),
            )
            self.standalone = True
        else:
            self.root = tk.Toplevel(master)
            self.root.title(f"BMH Station Controller  |  {station_id}")
            self.root.configure(background=ui.BG)
            ui.center(self.root, 1240, 820, master)
            self.root.minsize(1060, 700)
            self.standalone = False

        self.owns_engine = engine is None
        self._previous_event_handler = engine.on_event if engine is not None else None
        self.engine = engine or broadcast.BroadcastEngine(
            station_id, self.settings, on_event=self._on_event
        )
        self.engine.on_event = self._on_event
        self._closed = False
        self._tick_job = None
        self.model = WeatherModel(start=tz.central_now()[0].date())
        self.bus = bus_mod.Bus("BMH")

        self.hazards = list(EVENTS)
        self._static_index = 0
        self._rwt_day = None
        self._queue_rows: list[dict] = []

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._refresh_all()
        self._tick()
        self.log(f"{station_id} station controller online - {self.station['frequency']} MHz")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        header = ttk.Frame(self.root, style="Panel.TFrame", padding=(12, 8))
        header.pack(fill="x")
        self.title_var = tk.StringVar(
            value=f"{self.station_id}  {self.station['frequency']} MHz  "
                  f"{self.station['township']}"
        )
        ttk.Label(header, textvariable=self.title_var, style="Title.TLabel").pack(side="left")
        self.tx_var = tk.StringVar(value="STOPPED")
        ttk.Label(header, textvariable=self.tx_var, style="Header.TLabel").pack(
            side="right", padx=(8, 0)
        )
        ttk.Label(header, text="TRANSMITTER", style="Muted.TLabel").pack(side="right")
        self.clock_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock_var, style="Muted.TLabel").pack(
            side="right", padx=12
        )

        notebook = ttk.Notebook(self.root)
        notebook.pack(fill="both", expand=True, padx=8, pady=8)
        self._tab_weather(notebook)
        self._tab_control(notebook)
        self._tab_listening(notebook)
        self._tab_cycles(notebook)
        self._tab_static(notebook)
        self._tab_queue(notebook)
        self._tab_alerts(notebook)
        self._tab_products(notebook)

        self.status = ui.StatusBar(self.root)
        self.status.pack(fill="x", side="bottom")
        self.status.left.set(
            f"{self.station_id}  |  {self.station['township']}  |  "
            f"{self.station['coverage']}"
        )
        self.status.right.set(
            f"IP {self.settings.get('bmh.ip')}:{self.settings.get('bmh.port')}  |  "
            f"Network Status ONLINE (1)"
        )

    # ------------------------------------------------------ weather tab
    def _tab_weather(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Weather Message")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        hazard = ui.section(tab, "Hazard Category")
        hazard.grid(row=0, column=0, sticky="nsew", padx=(0, 6), pady=(0, 8))
        hazard.columnconfigure(1, weight=1)

        self.hazard_var = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Label(hazard, text="HAZARD", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        self.hazard_box = ttk.Combobox(
            hazard, textvariable=self.hazard_var, state="readonly", values=self.hazards,
        )
        self.hazard_box.grid(row=0, column=1, sticky="ew", padx=4)
        ttk.Button(hazard, text="ADD HAZARD", command=self._add_hazard).grid(
            row=0, column=2, padx=(4, 0)
        )
        self.wednesday_var = tk.BooleanVar(
            value=bool(self.settings.get("broadcast.wednesday_test", True))
        )
        ttk.Checkbutton(
            hazard, text="RMT / RWT every Wednesday (11 AM - noon)",
            variable=self.wednesday_var, command=self._save_wednesday,
        ).grid(row=1, column=0, columnspan=3, sticky="w", pady=(6, 0))
        ttk.Button(hazard, text="SEND RWT NOW", command=lambda: self._test("Required Weekly Test")).grid(
            row=2, column=0, sticky="w", pady=(6, 0)
        )
        ttk.Button(hazard, text="SEND RMT NOW", command=lambda: self._test("Required Monthly Test")).grid(
            row=2, column=1, sticky="w", padx=4, pady=(6, 0)
        )
        ttk.Button(hazard, text="UPDATE PERIODIC SCROLL", command=self._update_scroll).grid(
            row=2, column=2, sticky="e", pady=(6, 0)
        )

        message = ui.section(tab, "Warning Message / Call to Action")
        message.grid(row=0, column=1, sticky="nsew", padx=(6, 0), pady=(0, 8))
        message.rowconfigure(0, weight=1)
        message.columnconfigure(0, weight=1)
        holder = ttk.Frame(message)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.call_text = ui.text_widget(holder, height=7)
        self.call_text.frame.grid(row=0, column=0, sticky="nsew")
        self.call_text.insert("1.0", DEFAULT_CALL_TO_ACTION)
        row = ttk.Frame(message)
        row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(
            row, text="SEND WARNING MESSAGE", style="Accent.TButton",
            command=self._send_warning_message,
        ).pack(side="left")
        ttk.Button(row, text="RESET", command=self._reset_call_text).pack(side="left", padx=4)

        same_frame = ui.section(tab, "SAME / EAS Builder  -  northeast Illinois / northwest Indiana")
        same_frame.grid(row=1, column=0, columnspan=2, sticky="nsew")
        same_frame.columnconfigure(1, weight=1)
        same_frame.rowconfigure(0, weight=1)

        list_holder = ttk.Frame(same_frame)
        list_holder.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        ttk.Label(list_holder, text="UGC ZONES", style="Muted.TLabel").pack(anchor="w")
        self.ugc_list = tk.Listbox(
            list_holder, height=9, selectmode="extended", exportselection=False,
            background=ui.FIELD, foreground=ui.TEXT, selectbackground=ui.ACCENT_DARK,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 8),
        )
        self.ugc_list.pack(fill="both", expand=True, pady=(2, 4))
        for z in zones.ZONE_LIST:
            if z.state in ("IL", "IN") or z.marine:
                self.ugc_list.insert("end", f"{z.ugc}  {z.label}")
        self._select_ugc(self.station.get("ugc", ["INZ001", "INZ002"]))
        ugc_buttons = ttk.Frame(list_holder)
        ugc_buttons.pack(fill="x")
        ttk.Button(ugc_buttons, text="SELECT IL", command=lambda: self._bulk_ugc("IL")).pack(
            side="left"
        )
        ttk.Button(ugc_buttons, text="SELECT IN", command=lambda: self._bulk_ugc("IN")).pack(
            side="left", padx=3
        )
        ttk.Button(ugc_buttons, text="CLEAR", command=self._clear_ugc).pack(side="left")
        self.ugc_list.bind("<<ListboxSelect>>", lambda _e: self._update_same_preview())

        builder = ttk.Frame(same_frame)
        builder.grid(row=0, column=1, sticky="nsew")
        builder.columnconfigure(1, weight=1)

        self.same_message = tk.StringVar(value="This is a test.")
        ttk.Label(builder, text="MESSAGE", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(builder, textvariable=self.same_message).grid(
            row=0, column=1, sticky="ew", padx=4
        )
        self.same_purge = tk.IntVar(value=45)
        ttk.Label(builder, text="PURGE (MIN)", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Spinbox(builder, from_=1, to=180, textvariable=self.same_purge, width=6).grid(
            row=1, column=1, sticky="w", padx=4, pady=2
        )
        ttk.Label(builder, text="HEADER", style="Muted.TLabel").grid(row=2, column=0, sticky="nw")
        self.same_preview = tk.Text(
            builder, height=4, wrap="char", background="#050c11", foreground=ui.OK,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 9), padx=8, pady=6, state="disabled",
        )
        self.same_preview.grid(row=2, column=1, sticky="nsew", padx=4, pady=2)
        builder.rowconfigure(2, weight=1)

        send_row = ttk.Frame(builder)
        send_row.grid(row=3, column=0, columnspan=2, sticky="ew", pady=(8, 0))
        ttk.Button(
            send_row, text="SEND SAME ALERT", style="Accent.TButton",
            command=self._send_same_alert,
        ).pack(side="left")
        ttk.Button(send_row, text="RETONE", command=self._retone_selected).pack(side="left", padx=4)
        ttk.Button(
            send_row, text="1050 HZ TONE", command=lambda: self.engine.tone_only()
        ).pack(side="left")
        ttk.Button(
            send_row, text="SILENT INTERRUPT", style="Danger.TButton",
            command=self.engine.silent_interrupt,
        ).pack(side="right")

        self._update_same_preview()

    # ------------------------------------------------------ control tab
    def _tab_control(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Transmitter Control")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)

        transport = ui.section(left, "Transport")
        transport.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        self.tx_button = ttk.Button(
            transport, text="START TX", style="Accent.TButton", command=self._toggle_tx
        )
        self.tx_button.grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(transport, text="STOP TX", style="Danger.TButton",
                   command=self._stop_tx).grid(row=0, column=1, sticky="ew", padx=2, pady=2)
        ttk.Button(transport, text="NEXT PRODUCT", command=self.engine.next_product).grid(
            row=1, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(transport, text="RESTART SERVICE", command=self._restart).grid(
            row=1, column=1, sticky="ew", padx=2, pady=2
        )
        transport.columnconfigure(0, weight=1)
        transport.columnconfigure(1, weight=1)
        self.state_detail = tk.StringVar(value="STOPPED")
        ttk.Label(transport, textvariable=self.state_detail, style="Value.TLabel").grid(
            row=2, column=0, columnspan=2, sticky="w", padx=2, pady=(6, 0)
        )

        modes = ui.section(left, "Operational Modes")
        modes.grid(row=1, column=0, sticky="nsew")
        modes.rowconfigure(0, weight=1)
        modes.columnconfigure(0, weight=1)
        self.mode_list = tk.Listbox(
            modes, height=10, exportselection=False, background=ui.FIELD,
            foreground=ui.TEXT, selectbackground=ui.ACCENT_DARK, relief="flat",
            highlightthickness=1, highlightbackground=ui.BORDER, font=(ui.MONO, 9),
        )
        self.mode_list.grid(row=0, column=0, sticky="nsew")
        for mode in self.settings.mode_list():
            self.mode_list.insert("end", mode)
        self.mode_list.bind("<<ListboxSelect>>", self._on_mode_select)
        ttk.Button(modes, text="APPLY MODE NOW", command=self._apply_mode).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )

        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.columnconfigure(0, weight=1)
        right.rowconfigure(1, weight=1)

        quick = ui.section(right, "Quick Read IDs")
        quick.grid(row=0, column=0, sticky="new", pady=(0, 8))
        for idx, (label, key) in enumerate(QUICK_READS):
            ttk.Button(
                quick, text=label, command=lambda k=key: self._quick_read(k)
            ).grid(row=idx // 2, column=idx % 2, sticky="ew", padx=2, pady=2)
        quick.columnconfigure(0, weight=1)
        quick.columnconfigure(1, weight=1)

        manual = ui.section(right, "Manual Product Control")
        manual.grid(row=1, column=0, sticky="nsew")
        manual.columnconfigure(0, weight=1)
        self.manual_product = tk.StringVar(value="Zone Forecast Product")
        self.product_names = [awips.product(p).name for p in awips.PRODUCT_ORDER]
        ttk.Combobox(
            manual, textvariable=self.manual_product, state="readonly",
            values=self.product_names,
        ).grid(row=0, column=0, sticky="ew", padx=2, pady=2)
        ttk.Button(manual, text="READ NOW", command=self._manual_read).grid(
            row=1, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(manual, text="LOOP", command=self._manual_loop).grid(
            row=2, column=0, sticky="ew", padx=2, pady=2
        )
        ttk.Button(manual, text="STOP LOOP", command=self._stop_loop).grid(
            row=3, column=0, sticky="ew", padx=2, pady=2
        )
        self.now_playing = tk.StringVar(value="--")
        ttk.Label(manual, text="NOW PLAYING", style="Muted.TLabel").grid(
            row=4, column=0, sticky="w", pady=(8, 0)
        )
        ttk.Label(manual, textvariable=self.now_playing, style="Header.TLabel",
                  wraplength=380, justify="left").grid(row=5, column=0, sticky="w")
        self.loop_var = tk.StringVar(value="")
        ttk.Label(manual, textvariable=self.loop_var, style="Muted.TLabel").grid(
            row=6, column=0, sticky="w"
        )

    # ---------------------------------------------------- listening tab
    def _tab_listening(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Listening Area")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        text = self.settings.get("broadcast.listening_area.text", "")
        ttk.Label(tab, text=text, style="Muted.TLabel", wraplength=1080,
                  justify="left").grid(row=0, column=0, sticky="w", pady=(0, 8))

        area = ui.section(tab, "Filtering")
        area.grid(row=1, column=0, sticky="nsew")
        area.columnconfigure(0, weight=1)
        area.rowconfigure(2, weight=1)

        self.filter_var = tk.BooleanVar(value=self.engine.filter_enabled)
        self.uncoded_var = tk.BooleanVar(value=self.engine.allow_uncoded)
        ttk.Checkbutton(
            area, text="Enable listening-area filter (only alerts covering the UGC below)",
            variable=self.filter_var, command=self._save_listening,
        ).grid(row=0, column=0, sticky="w")
        ttk.Checkbutton(
            area, text="Allow uncoded routine products", variable=self.uncoded_var,
            command=self._save_listening,
        ).grid(row=1, column=0, sticky="w", pady=(2, 6))

        ttk.Label(area, text="ILLINOIS / INDIANA UGC (one per line)", style="Muted.TLabel").grid(
            row=2, column=0, sticky="nw"
        )
        holder = ttk.Frame(area)
        holder.grid(row=3, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.listen_text = ui.text_widget(holder, height=12)
        self.listen_text.frame.grid(row=0, column=0, sticky="nsew")
        self.listen_text.insert("1.0", "\n".join(self.settings.listening_ugc()))
        area.rowconfigure(3, weight=1)
        buttons = ttk.Frame(area)
        buttons.grid(row=4, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="SAVE LISTENING AREA", style="Accent.TButton",
                   command=self._save_listening_text).pack(side="left")
        ttk.Button(buttons, text="ALL IL/IN", command=self._all_listening).pack(
            side="left", padx=4
        )
        self.listen_count = tk.StringVar(value="")
        ttk.Label(buttons, textvariable=self.listen_count, style="Muted.TLabel").pack(
            side="right"
        )
        self._update_listen_count()

    # ------------------------------------------------------- cycles tab
    def _tab_cycles(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Broadcast Cycles")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        modes = ui.section(tab, "Modes")
        modes.grid(row=0, column=0, rowspan=2, sticky="nsew", padx=(0, 6))
        modes.rowconfigure(0, weight=1)
        modes.columnconfigure(0, weight=1)
        self.cycle_modes = tk.Listbox(
            modes, exportselection=False, background=ui.FIELD, foreground=ui.TEXT,
            selectbackground=ui.ACCENT_DARK, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 9),
        )
        self.cycle_modes.grid(row=0, column=0, sticky="nsew")
        for mode in self.settings.mode_list():
            self.cycle_modes.insert("end", mode)
        self.cycle_modes.bind("<<ListboxSelect>>", self._load_cycle)
        row = ttk.Frame(modes)
        row.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(row, text="NEW MODE", command=self._new_mode).pack(side="left")
        ttk.Button(row, text="DELETE MODE", command=self._delete_mode).pack(side="left", padx=4)
        ttk.Button(row, text="RESET MODE", command=self._reset_mode).pack(side="left")

        entries = ui.section(tab, "Cycle Entries")
        entries.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        entries.columnconfigure(0, weight=1)
        entries.rowconfigure(1, weight=1)
        ttk.Label(entries, text="--- SPECIAL ---", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.special_list = tk.Listbox(
            entries, height=9, exportselection=False, background=ui.FIELD,
            foreground=ui.WARN, selectbackground=ui.ACCENT_DARK, relief="flat",
            highlightthickness=1, highlightbackground=ui.BORDER, font=(ui.MONO, 8),
        )
        self.special_list.grid(row=1, column=0, sticky="nsew")
        for token in self.settings.get("broadcast.special_entries", []):
            self.special_list.insert("end", token)
        ttk.Button(entries, text="ADD ENTRY TO CYCLE", command=self._add_cycle_entry).grid(
            row=2, column=0, sticky="ew", pady=(4, 0)
        )

        order = ui.section(tab, "Cycle Order")
        order.grid(row=1, column=1, sticky="nsew", padx=(6, 0), pady=(8, 0))
        order.columnconfigure(0, weight=1)
        order.rowconfigure(1, weight=1)
        self.cycle_order = tk.Listbox(
            order, height=9, exportselection=False, background=ui.FIELD,
            foreground=ui.TEXT, selectbackground=ui.ACCENT_DARK, relief="flat",
            highlightthickness=1, highlightbackground=ui.BORDER, font=(ui.MONO, 8),
        )
        self.cycle_order.grid(row=1, column=0, sticky="nsew")
        ttk.Label(order, text="CYCLE ORDER (1-8)", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        row = ttk.Frame(order)
        row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(row, text="ADD CUSTOM", command=self._add_custom_entry).pack(side="left")
        ttk.Button(row, text="UP", command=lambda: self._move_cycle(-1)).pack(side="left", padx=3)
        ttk.Button(row, text="DOWN", command=lambda: self._move_cycle(1)).pack(side="left")
        ttk.Button(row, text="REMOVE", command=self._remove_cycle).pack(side="left", padx=3)
        ttk.Button(row, text="SAVE CYCLES", style="Accent.TButton",
                   command=self._save_cycles).pack(side="right")
        self._select_first(self.cycle_modes)

    # ------------------------------------------------------- static tab
    def _tab_static(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Static Messages")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        left = ttk.Frame(tab)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        left.rowconfigure(0, weight=1)
        self.static_list = tk.Listbox(
            left, width=26, exportselection=False, background=ui.FIELD,
            foreground=ui.TEXT, selectbackground=ui.ACCENT_DARK, relief="flat",
            highlightthickness=1, highlightbackground=ui.BORDER, font=(ui.MONO, 9),
        )
        self.static_list.grid(row=0, column=0, sticky="nsew")
        for key in STATIC_KEYS:
            self.static_list.insert("end", key)
        self.static_list.bind("<<ListboxSelect>>", self._load_static)
        self.static_list.select_set(0)
        ttk.Button(left, text="ADVANCE", command=self._advance_static).grid(
            row=1, column=0, sticky="ew", pady=(6, 0)
        )

        right = ttk.Frame(tab)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        head = ttk.Frame(right)
        head.grid(row=0, column=0, sticky="ew")
        self.static_title = tk.StringVar(value=STATIC_KEYS[0])
        ttk.Label(head, textvariable=self.static_title, style="Header.TLabel").pack(side="left")
        self.static_custom = tk.StringVar(value="")
        ttk.Label(head, textvariable=self.static_custom, style="Muted.TLabel").pack(
            side="right"
        )

        ttk.Label(
            right, text="Message text (edit to override the built-in script)",
            style="Muted.TLabel",
        ).grid(row=1, column=0, sticky="w", pady=(4, 2))
        holder = ttk.Frame(right)
        holder.grid(row=2, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.static_text = ui.text_widget(holder, height=14)
        self.static_text.frame.grid(row=0, column=0, sticky="nsew")

        buttons = ttk.Frame(right)
        buttons.grid(row=3, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="READ NOW", style="Accent.TButton",
                   command=self._read_static).pack(side="left")
        ttk.Button(buttons, text="SAVE EDIT", command=self._save_static).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="RESTORE DEFAULT", command=self._restore_static).pack(
            side="left"
        )
        self._load_static()

    # -------------------------------------------------------- queue tab
    def _tab_queue(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Live Queue")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(1, weight=1)

        top = ui.section(tab, "Queue Status")
        top.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        for col in range(4):
            top.columnconfigure(col, weight=1)

        self.q_status = tk.StringVar(value="STOPPED")
        self.q_mode = tk.StringVar(value=self.engine.mode)
        self.q_current = tk.StringVar(value="--")
        self.q_length = tk.StringVar(value="0")
        for idx, (label, var) in enumerate(
            [("STATUS", self.q_status), ("MODE", self.q_mode),
             ("CURRENTLY PLAYING", self.q_current), ("QUEUE LENGTH", self.q_length)]
        ):
            ttk.Label(top, text=label, style="Muted.TLabel").grid(
                row=0, column=idx, sticky="w", padx=4
            )
            ttk.Label(top, textvariable=var, style="Value.TLabel").grid(
                row=1, column=idx, sticky="w", padx=4
            )

        voice_row = ttk.Frame(top)
        voice_row.grid(row=2, column=0, columnspan=4, sticky="w", pady=(8, 0), padx=2)
        ttk.Label(voice_row, text="VOICE FOR VTML PAUL", style="Muted.TLabel").pack(side="left")
        self.voice_var = tk.StringVar(value=self.engine.voice)
        voice_box = ttk.Combobox(
            voice_row, textvariable=self.voice_var, state="readonly", width=12,
            values=[f"{k} - {v}" for k, v in self.engine.voices.labels().items()],
        )
        voice_box.pack(side="left", padx=6)
        voice_box.set(f"{self.engine.voice} - {self.engine.voices.labels().get(self.engine.voice, '')}")
        voice_box.bind("<<ComboboxSelected>>", self._on_voice_change)
        ttk.Button(voice_row, text="TEST VOICE", command=self._test_voice).pack(side="left")

        queue = ui.section(tab, "Queue")
        queue.grid(row=1, column=0, sticky="nsew")
        queue.columnconfigure(0, weight=1)
        queue.rowconfigure(0, weight=1)
        holder = ttk.Frame(queue)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.queue_tree = ui.tree(
            holder, [("n", "#", 40), ("title", "Item", 320), ("pri", "Pri", 50),
                     ("sec", "Sec", 60), ("src", "Source", 90)],
            height=12,
        )
        self.queue_tree.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(holder, orient="vertical", command=self.queue_tree.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.queue_tree.configure(yscrollcommand=scroll.set)

        buttons = ttk.Frame(queue)
        buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="REFRESH NOW", command=self._refresh_queue).pack(side="left")
        ttk.Button(buttons, text="READ SELECTED NOW", command=self._read_queue_selected).pack(
            side="left", padx=4
        )
        ttk.Button(buttons, text="LOOP SELECTED", command=self._loop_queue_selected).pack(
            side="left"
        )
        ttk.Button(buttons, text="STOP LOOP", command=self._stop_loop).pack(side="left", padx=4)
        ttk.Button(buttons, text="CLEAR QUEUE", command=self._clear_queue).pack(side="right")

    # -------------------------------------------------------- alerts tab
    def _tab_alerts(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Active Alerts")
        tab.columnconfigure(0, weight=1)
        tab.rowconfigure(0, weight=1)

        frame = ui.section(tab, "Active Alerts")
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(0, weight=1)
        frame.rowconfigure(0, weight=1)
        holder = ttk.Frame(frame)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.alert_tree = ui.tree(
            holder,
            [("id", "Alert ID", 190), ("event", "Summary", 220), ("action", "Action", 60),
             ("expires", "Expires", 80)],
            height=13,
        )
        self.alert_tree.grid(row=0, column=0, sticky="nsew")
        self.alert_tree.bind("<Double-1>", lambda _e: self._edit_alert())
        ttk.Scrollbar(holder, orient="vertical", command=self.alert_tree.yview).grid(
            row=0, column=1, sticky="ns"
        )

        buttons = ttk.Frame(frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        for label, command in [
            ("REFRESH LIST", self._refresh_alerts),
            ("EDIT SELECTED", self._edit_alert),
            ("SAME RETONE", self._retone_selected),
            ("1050 HZ", lambda: self.engine.tone_only()),
            ("SILENT INTERRUPT", self.engine.silent_interrupt),
            ("@Products", self._alert_products),
        ]:
            ttk.Button(buttons, text=label, command=command).pack(side="left", padx=2)
        self.alert_summary = tk.StringVar(value="No active alerts.")
        ttk.Label(frame, textvariable=self.alert_summary, style="Muted.TLabel",
                  wraplength=1060, justify="left").grid(row=2, column=0, sticky="w", pady=(6, 0))

    # ------------------------------------------------------- products tab
    def _tab_products(self, notebook: ttk.Notebook) -> None:
        tab = ttk.Frame(notebook, padding=8)
        notebook.add(tab, text="Products")
        tab.columnconfigure(0, weight=1)
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(0, weight=1)

        tree_frame = ui.section(tab, "Product Catalog")
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        self.product_tree = ui.tree(
            tree_frame,
            [("pil", "PIL", 80), ("name", "Product", 210), ("cat", "Category", 80),
             ("pri", "Pri", 40), ("dur", "Min", 46)],
            height=14,
        )
        self.product_tree.grid(row=0, column=0, sticky="nsew")
        for pid in awips.PRODUCT_ORDER:
            prod = awips.product(pid)
            self.product_tree.insert(
                "", "end", iid=pid,
                values=(prod.awips_id, prod.name, prod.category, prod.priority, prod.duration),
            )
        self.product_tree.bind("<Double-1>", lambda _e: self._preview_product())

        buttons = ttk.Frame(tree_frame)
        buttons.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="PREVIEW", command=self._preview_product).pack(side="left")
        ttk.Button(buttons, text="READ NOW", style="Accent.TButton",
                   command=self._product_read).pack(side="left", padx=4)
        ttk.Button(buttons, text="QUEUE", command=self._product_queue).pack(side="left")
        ttk.Button(buttons, text="LOOP", command=self._product_loop).pack(side="left", padx=4)

        preview = ui.section(tab, "Script Preview")
        preview.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        preview.columnconfigure(0, weight=1)
        preview.rowconfigure(0, weight=1)
        holder = ttk.Frame(preview)
        holder.grid(row=0, column=0, sticky="nsew")
        self.product_preview = ui.scrolled_text(holder, height=16)
        self.product_preview.configure(state="disabled")
        self.product_info = tk.StringVar(value="Select a product and press PREVIEW.")
        ttk.Label(preview, textvariable=self.product_info, style="Muted.TLabel",
                  wraplength=520, justify="left").grid(row=1, column=0, sticky="w", pady=(6, 0))

    # ------------------------------------------------------------- helpers
    def log(self, message: str, tag: str = "") -> None:
        if hasattr(self, "status"):
            self.status.middle.set(message[:120])

    def _selected_text(self, widget: tk.Listbox) -> str:
        selection = widget.curselection()
        return widget.get(selection[0]) if selection else ""

    def _select_first(self, widget: tk.Listbox) -> None:
        if widget.size():
            widget.selection_set(0)
            widget.event_generate("<<ListboxSelect>>")

    def _select_ugc(self, ugc: list[str]) -> None:
        wanted = {u.upper() for u in ugc}
        for i in range(self.ugc_list.size()):
            if self.ugc_list.get(i).split()[0] in wanted:
                self.ugc_list.selection_set(i)

    def _bulk_ugc(self, state: str) -> None:
        for i in range(self.ugc_list.size()):
            token = self.ugc_list.get(i).split()[0]
            z = zones.zone(token)
            if z and z.state == state:
                self.ugc_list.selection_set(i)
        self._update_same_preview()

    def _clear_ugc(self) -> None:
        self.ugc_list.selection_clear(0, "end")
        self._update_same_preview()

    def _selected_ugc(self) -> list[str]:
        out = []
        for index in self.ugc_list.curselection():
            token = self.ugc_list.get(index).split()[0]
            if token.startswith("LMZ") or token in zones.ZONES:
                out.append(token)
        return out or list(self.station.get("ugc", ["INZ001", "INZ002"]))

    def _current_hazard(self) -> str:
        return self.hazard_var.get()

    def _product_by_name(self, name: str) -> awips.Product:
        for pid in awips.PRODUCT_ORDER:
            prod = awips.product(pid)
            if prod.name == name:
                return prod
        return awips.product("ZFPLOT")

    # --------------------------------------------------- weather actions
    def _add_hazard(self) -> None:
        value = simpledialog.askstring(
            "Add Hazard", "Hazard category (SAME event name):", parent=self.root
        )
        if not value:
            return
        value = value.strip()
        if value not in self.hazards:
            self.hazards.append(value)
            self.hazard_box.configure(values=self.hazards)
        self.hazard_var.set(value)
        self.log(f"hazard category added: {value}")

    def _save_wednesday(self) -> None:
        self.settings.set("broadcast.wednesday_test", bool(self.wednesday_var.get()))
        self.settings.save()

    def _test(self, kind: str) -> None:
        self.engine.send_test(kind)
        self.log(f"{kind} transmitted")

    def _update_scroll(self) -> None:
        scroll = self.settings.get("bmh.ticker", "This is a test.")
        self.engine.ticker_text = scroll
        self.engine.enqueue(self.engine.script_for_text("Periodic Scroll", scroll, "SPS", 15))
        self.log("periodic scroll updated")

    def _reset_call_text(self) -> None:
        self.call_text.delete("1.0", "end")
        self.call_text.insert("1.0", DEFAULT_CALL_TO_ACTION)

    def _send_warning_message(self) -> None:
        body = self.call_text.get("1.0", "end").strip()
        if not body:
            return
        event = self._current_hazard()
        item = self.engine.enqueue(
            self.engine.script_for_text(f"{event} Call to Action", body, "SPS", 45),
            front=True,
        )
        self.log(f"warning message queued: {item.title}")
        self._refresh_queue()

    def _update_same_preview(self) -> None:
        event = self._current_hazard()
        ugc = self._selected_ugc()
        try:
            header = same.same_header(
                event, zones.same_list(ugc),
                purge_minutes=int(self.same_purge.get()) if hasattr(self, "same_purge") else 45,
                callsign=f"{self.station_id}/NWS",
            )
        except Exception as exc:
            header = f"(cannot build header: {exc})"
        if hasattr(self, "same_preview"):
            self.same_preview.configure(state="normal")
            self.same_preview.delete("1.0", "end")
            self.same_preview.insert("1.0", header)
            self.same_preview.configure(state="disabled")

    def _send_same_alert(self) -> None:
        event = self._current_hazard()
        ugc = self._selected_ugc()
        message = self.same_message.get().strip()
        alert = self.engine.send_same_alert(
            event, ugc, message=message, duration_min=int(self.same_purge.get()),
        )
        self.log(f"SAME alert {event} -> {alert.same_header}")
        self._refresh_alerts()

    # --------------------------------------------------- control actions
    def _toggle_tx(self) -> None:
        if self.engine.snapshot()["running"]:
            self._stop_tx()
        else:
            self.engine.start()
            self.log("START TX")
            self._refresh_queue()

    def _stop_tx(self) -> None:
        self.engine.stop()
        self.log("STOP TX")
        self._refresh_queue()

    def _restart(self) -> None:
        self.engine.restart_service()
        self.log("RESTART SERVICE complete")
        self._refresh_queue()

    def _on_mode_select(self, _event=None) -> None:
        mode = self._selected_text(self.mode_list)
        if mode:
            self.engine.set_mode(mode)
            self.log(f"broadcast mode -> {mode}")

    def _apply_mode(self) -> None:
        self._on_mode_select()
        self.engine.fill_cycle()
        self._refresh_queue()

    def _quick_read(self, key: str) -> None:
        item = self.engine.enqueue_static(key, front=True)
        self.log(f"quick read: {item.title}")
        self._refresh_queue()

    def _manual_read(self) -> None:
        prod = self._product_by_name(self.manual_product.get())
        self.engine.read_now(prod.pil)
        self.log(f"READ NOW {prod.name}")
        self._refresh_queue()

    def _manual_loop(self) -> None:
        prod = self._product_by_name(self.manual_product.get())
        self.engine.loop_product(prod.pil)
        self.loop_var.set(f"LOOPING: {prod.name}")
        self.log(f"LOOP {prod.name}")
        self._refresh_queue()

    def _stop_loop(self) -> None:
        self.engine.stop_loop()
        self.loop_var.set("")
        self.log("loop stopped")

    # --------------------------------------------------- listening actions
    def _save_listening(self) -> None:
        self.engine.filter_enabled = bool(self.filter_var.get())
        self.engine.allow_uncoded = bool(self.uncoded_var.get())
        self.settings.set("broadcast.listening_area.enable_filter", self.engine.filter_enabled)
        self.settings.set("broadcast.listening_area.allow_uncoded", self.engine.allow_uncoded)
        self.settings.save()
        self._refresh_alerts()

    def _save_listening_text(self) -> None:
        ugc = zones.parse_ugc(self.listen_text.get("1.0", "end"))
        if not ugc:
            messagebox.showwarning("Listening Area", "No valid UGC zones found.", parent=self.root)
            return
        self.settings.set("broadcast.listening_area.ugc", ugc)
        self.settings.save()
        self.engine.listeners = ugc
        self._update_listen_count()
        self._refresh_alerts()
        self.log(f"listening area saved: {len(ugc)} zones")

    def _all_listening(self) -> None:
        ugc = [z.ugc for z in zones.ZONE_LIST if z.state in ("IL", "IN")]
        self.listen_text.delete("1.0", "end")
        self.listen_text.insert("1.0", "\n".join(ugc))
        self._update_listen_count()

    def _update_listen_count(self) -> None:
        ugc = zones.parse_ugc(self.listen_text.get("1.0", "end"))
        self.listen_count.set(f"{len(ugc)} zones configured")

    # ------------------------------------------------------ cycles actions
    def _selected_mode(self) -> str:
        return self._selected_text(self.cycle_modes)

    def _load_cycle(self, _event=None) -> None:
        mode = self._selected_mode()
        self.cycle_order.delete(0, "end")
        for idx, token in enumerate(self.settings.modes().get(mode, []), start=1):
            self.cycle_order.insert("end", f"{idx}. {token}")

    def _add_cycle_entry(self) -> None:
        token = self._selected_text(self.special_list)
        if not token:
            return
        self.cycle_order.insert("end", f"{self.cycle_order.size() + 1}. {token}")
        self._renumber_cycle()

    def _add_custom_entry(self) -> None:
        token = simpledialog.askstring(
            "Add Cycle Entry", "Product, static key or @token:", parent=self.root
        )
        if not token:
            return
        self.cycle_order.insert("end", f"{self.cycle_order.size() + 1}. {token.strip()}")
        self._renumber_cycle()

    def _renumber_cycle(self) -> None:
        items = [self.cycle_order.get(i).split(". ", 1)[-1] for i in range(self.cycle_order.size())]
        self.cycle_order.delete(0, "end")
        for idx, token in enumerate(items, start=1):
            self.cycle_order.insert("end", f"{idx}. {token}")

    def _move_cycle(self, delta: int) -> None:
        selection = self.cycle_order.curselection()
        if not selection:
            return
        index = selection[0]
        new = max(0, min(self.cycle_order.size() - 1, index + delta))
        if new == index:
            return
        token = self.cycle_order.get(index).split(". ", 1)[-1]
        self.cycle_order.delete(index)
        self.cycle_order.insert(new, f"{new + 1}. {token}")
        self._renumber_cycle()
        self.cycle_order.selection_set(new)

    def _remove_cycle(self) -> None:
        selection = self.cycle_order.curselection()
        if selection:
            self.cycle_order.delete(selection[0])
            self._renumber_cycle()

    def _mode_entries(self) -> list[str]:
        return [
            self.cycle_order.get(i).split(". ", 1)[-1]
            for i in range(self.cycle_order.size())
        ]

    def _save_cycles(self) -> None:
        mode = self._selected_mode()
        if not mode:
            return
        self.settings.set(f"broadcast.modes.{mode}", self._mode_entries())
        self.settings.save()
        self.log(f"cycle '{mode}' saved ({self.cycle_order.size()} entries)")
        messagebox.showinfo("Broadcast Cycles", f"Cycle '{mode}' saved.", parent=self.root)

    def _new_mode(self) -> None:
        name = simpledialog.askstring("New Mode", "Mode name:", parent=self.root)
        if not name:
            return
        name = name.strip()
        self.settings.set(f"broadcast.modes.{name}", ["ADVANCE", "@AUTO_ID", "CURRENT_TIME"])
        self.settings.save()
        self.cycle_modes.insert("end", name)
        self.mode_list.insert("end", name)
        self.cycle_modes.selection_clear(0, "end")
        self.cycle_modes.selection_set("end")
        self._load_cycle()
        self.log(f"mode created: {name}")

    def _delete_mode(self) -> None:
        mode = self._selected_mode()
        if not mode:
            return
        if mode == "General":
            messagebox.showwarning("Delete Mode", "The General mode cannot be deleted.",
                                   parent=self.root)
            return
        if not messagebox.askyesno("Delete Mode", f"Delete broadcast mode '{mode}'?",
                                   parent=self.root):
            return
        data = self.settings.modes()
        data.pop(mode, None)
        self.settings.set("broadcast.modes", data)
        self.settings.save()
        for widget in (self.cycle_modes, self.mode_list):
            index = None
            for i in range(widget.size()):
                if widget.get(i) == mode:
                    index = i
            if index is not None:
                widget.delete(index)
        self._load_cycle()
        self.log(f"mode deleted: {mode}")

    def _reset_mode(self) -> None:
        mode = self._selected_mode()
        if not mode:
            return
        default = __import__("lotwps.config", fromlist=["DEFAULTS"]).DEFAULTS["broadcast"]["modes"]
        entries = default.get(mode, ["ADVANCE", "@AUTO_ID", "CURRENT_TIME"])
        self.settings.set(f"broadcast.modes.{mode}", list(entries))
        self.settings.save()
        self._load_cycle()
        self.log(f"mode reset: {mode}")

    # ------------------------------------------------------ static actions
    def _current_static(self) -> str:
        selection = self.static_list.curselection()
        return self.static_list.get(selection[0]) if selection else STATIC_KEYS[0]

    def _static_text_for(self, key: str) -> str:
        override = self.settings.get(f"broadcast.static_overrides.{key}", "")
        if override:
            return str(override)
        return self.model.static_message(key, self.station)

    def _load_static(self, _event=None) -> None:
        key = self._current_static()
        self.static_title.set(key)
        override = self.settings.get(f"broadcast.static_overrides.{key}", "")
        self.static_custom.set("CUSTOM OVERRIDE" if override else "built-in script")
        self.static_text.delete("1.0", "end")
        self.static_text.insert("1.0", self._static_text_for(key))

    def _read_static(self) -> None:
        key = self._current_static()
        self.engine.enqueue_static(key, front=True)
        self.log(f"static read: {key}")
        self._refresh_queue()

    def _advance_static(self) -> None:
        key = STATIC_KEYS[self._static_index % len(STATIC_KEYS)]
        self._static_index += 1
        self.engine.enqueue_static(key, front=True)
        for index in range(self.static_list.size()):
            if self.static_list.get(index) == key:
                self.static_list.selection_clear(0, "end")
                self.static_list.selection_set(index)
        self._load_static()
        self.log(f"ADVANCE -> {key}")

    def _save_static(self) -> None:
        key = self._current_static()
        text = self.static_text.get("1.0", "end").strip()
        if not text:
            return
        self.settings.set(f"broadcast.static_overrides.{key}", text)
        self.settings.save()
        self.static_custom.set("CUSTOM OVERRIDE")
        self.log(f"static override saved: {key}")

    def _restore_static(self) -> None:
        key = self._current_static()
        overrides = self.settings.get("broadcast.static_overrides", {})
        overrides.pop(key, None)
        self.settings.set("broadcast.static_overrides", overrides)
        self.settings.save()
        self._load_static()
        self.log(f"static override cleared: {key}")

    # ------------------------------------------------------- queue actions
    def _on_voice_change(self, _event=None) -> None:
        value = self.voice_var.get()
        key = value.split(" - ", 1)[0].strip()
        if key in self.engine.voices.keys():
            self.engine.voice = key
            self.log(f"voice -> {key}")

    def _test_voice(self) -> None:
        try:
            path = self.engine.voices.test_voice(self.engine.voice)
            audio.player().play(path)
            self.log(f"voice test: {path.name}")
        except Exception as exc:
            self.log(f"voice test failed: {exc}")

    def _refresh_queue(self) -> None:
        self._queue_rows = self.engine.queue_snapshot()
        self.queue_tree.delete(*self.queue_tree.get_children())
        for idx, row in enumerate(self._queue_rows, start=1):
            self.queue_tree.insert(
                "", "end", iid=row["id"],
                values=(idx, row["title"], row["priority"], f"{row['seconds']:.0f}",
                        row["source"]),
            )
        snap = self.engine.snapshot()
        self.q_status.set(snap["state"] if snap["running"] else "STOPPED")
        self.q_mode.set(snap["mode"])
        self.q_current.set(snap["current"] or "--")
        self.q_length.set(str(snap["queue"]))
        self.tx_var.set(snap["state"] if snap["running"] else "STOPPED")
        self.tx_button.configure(text="STOP TX" if snap["running"] else "START TX")
        self.state_detail.set(
            f"{snap['state']}  |  mode {snap['mode']}  |  played {snap['played']}  |  "
            f"queue {snap['queue']}"
        )

    def _queue_selected_row(self) -> dict | None:
        selection = self.queue_tree.selection()
        if not selection:
            return None
        target = selection[0]
        return next((row for row in self._queue_rows if row["id"] == target), None)

    def _read_queue_selected(self) -> None:
        row = self._queue_selected_row()
        if not row:
            return
        if row["source"] == "STATIC":
            self.engine.enqueue_static(row["product_id"], front=True)
        elif row["product_id"] == "SPS" and row["source"] == "TEXT":
            item = next(
                (i for i in self.engine._queue if i[2].item_id == row["id"]), None
            )
            if item:
                self.engine.enqueue(item[2], front=True)
        else:
            self.engine.enqueue_product(row["product_id"], front=True)
        self.log(f"READ SELECTED NOW: {row['title']}")
        self._refresh_queue()

    def _loop_queue_selected(self) -> None:
        row = self._queue_selected_row()
        if not row:
            return
        self.engine.loop_product(row["product_id"])
        self.loop_var.set(f"LOOPING: {row['title']}")
        self.log(f"LOOP SELECTED: {row['title']}")

    def _clear_queue(self) -> None:
        self.engine.clear_queue()
        self._refresh_queue()

    # ------------------------------------------------------ alert actions
    def _refresh_alerts(self) -> None:
        self.alert_tree.delete(*self.alert_tree.get_children())
        for alert in self.store.all():
            self.alert_tree.insert(
                "", "end", iid=alert.alert_id,
                values=(alert.alert_id, alert.event, alert.status,
                        f"{alert.expires:%H:%M}Z"),
            )
        self.alert_summary.set(self.store.summary())

    def _selected_alert(self):
        selection = self.alert_tree.selection()
        if not selection:
            return None
        return self.store.by_id(selection[0])

    def _edit_alert(self) -> None:
        alert = self._selected_alert()
        if not alert:
            return
        from alert_editor import edit_alert

        edit_alert(self.root, alert, on_save=lambda _a: self._refresh_alerts())

    def _retone_selected(self) -> None:
        alert = self._selected_alert()
        if alert:
            self.engine.retone(alert)
            self.log(f"SAME retone: {alert.alert_id}")

    def _alert_products(self) -> None:
        alert = self._selected_alert()
        if not alert:
            return
        text = (
            f"{alert.headline}. {alert.description} {alert.instruction}".strip()
        )
        self.engine.enqueue(
            self.engine.script_for_text(f"@Products {alert.alert_id}", text, alert.prod_id, 60),
            front=True,
        )
        self.log(f"@Products queued for {alert.alert_id}")

    # ----------------------------------------------------- product actions
    def _product_selected(self) -> str | None:
        selection = self.product_tree.selection()
        return selection[0] if selection else None

    def _preview_product(self) -> None:
        pid = self._product_selected()
        if not pid:
            return
        item = self.engine.script_for_product(pid)
        text = item.script.text() or "(pre-rendered VoiceText Paul asset)"
        self.product_preview.configure(state="normal")
        self.product_preview.delete("1.0", "end")
        self.product_preview.insert("1.0", text)
        self.product_preview.configure(state="disabled")
        prod = awips.product(pid)
        self.product_info.set(
            f"{prod.awips_id}  |  {prod.name}  |  {prod.category}  |  "
            f"priority {prod.priority}  |  {prod.duration} min  |  "
            f"{item.seconds:.0f} s rendered"
        )

    def _product_read(self) -> None:
        pid = self._product_selected()
        if pid:
            self.engine.read_now(pid)
            self.log(f"READ NOW {pid}")
            self._refresh_queue()

    def _product_queue(self) -> None:
        pid = self._product_selected()
        if pid:
            self.engine.enqueue_product(pid)
            self.log(f"queued {pid}")
            self._refresh_queue()

    def _product_loop(self) -> None:
        pid = self._product_selected()
        if pid:
            self.engine.loop_product(pid)
            self.loop_var.set(f"LOOPING: {awips.product(pid).name}")
            self.log(f"LOOP {pid}")
            self._refresh_queue()

    # -------------------------------------------------------------- events
    def _on_event(self, kind: str, payload: dict) -> None:
        if self._closed:
            return
        try:
            self.root.after(0, lambda: self._handle_event(kind, payload))
        except (RuntimeError, tk.TclError):
            pass

    def _handle_event(self, kind: str, payload: dict) -> None:
        if self._closed:
            return
        try:
            if kind == "status":
                self._refresh_queue()
            elif kind == "queue":
                self._refresh_queue()
            elif kind == "playing":
                self.now_playing.set(payload.get("title", "--"))
            elif kind == "alert":
                self._refresh_alerts()
            elif kind == "log":
                self.status.middle.set(payload.get("message", "")[:120])
        except tk.TclError:
            pass

    def _refresh_all(self) -> None:
        self._refresh_queue()
        self._refresh_alerts()
        self._load_cycle()
        self._update_same_preview()

    def _tick(self) -> None:
        if self._closed:
            return
        now, label = tz.central_now()
        self.clock_var.set(f"{now:%H:%M:%S} {label}  {now:%a %b} {now.day}")
        self.q_current.set(self.engine.snapshot()["current"] or "--")
        self.tx_var.set(
            self.engine.state if self.engine.snapshot()["running"] else "STOPPED"
        )
        # Required Weekly Test window: Wednesday 11 AM - noon
        if self.wednesday_var.get() and now.weekday() == 2 and 11 <= now.hour < 12:
            if self._rwt_day != now.date():
                self._rwt_day = now.date()
                self.engine.send_test("Required Weekly Test")
                self.log("automatic Required Weekly Test transmitted")
        try:
            self._tick_job = self.root.after(1000, self._tick)
        except tk.TclError:
            pass

    def _close(self) -> None:
        self._closed = True
        if self._tick_job:
            try:
                self.root.after_cancel(self._tick_job)
            except Exception:
                pass
        try:
            if self.owns_engine:
                self.engine.shutdown()
            elif self._previous_event_handler is not None:
                self.engine.on_event = self._previous_event_handler
        finally:
            self.root.destroy()


def main() -> None:
    station_id = sys.argv[1] if len(sys.argv) > 1 else "WXJ75"
    StationController(station_id=station_id).root.mainloop()


if __name__ == "__main__":
    main()
