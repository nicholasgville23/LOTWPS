"""CAVE-LOT D2D client and AWIPS II text workstation windows.

The big-screen display: radar mosaic, alert polygons, layer control, animation
and WarnGen launch. The Text 1-5 windows are the AWIPS II text editors that
compose and dispatch products to LOTIEM / BMH.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent))

from lotwps import (
    alerts as alert_mod,
    appkit,
    awips,
    bus as bus_mod,
    mapview,
    tz,
    ui,
    zones,
)

TIER_COLORS = {
    "Emergency": "#ff3b30",
    "Warning": "#ff9f0a",
    "Watch": "#ffd60a",
    "Advisory": "#64d2ff",
    "Statement": "#bf5af2",
    "Routine": "#8ba3bb",
}

PRODUCT_LAYERS = [
    ("Base Reflectivity", "NEXRAD BASE REFLECTIVITY  DBZ"),
    ("Storm Relative Velocity", "STORM RELATIVE VELOCITY  KT"),
    ("Echo Tops", "ECHO TOPS  KFT"),
    ("Precipitation Type", "PRECIPITATION TYPE"),
    ("Flash Flood Guidance", "FLASH FLOOD GUIDANCE"),
]


class AwipsTextWindow(tk.Toplevel):
    """AWIPS II text workstation popup (Text 1-5)."""

    def __init__(self, parent, number: int, settings, store, bus, on_send=None) -> None:
        super().__init__(parent)
        self.number = number
        self.settings = settings
        self.store = store
        self.bus = bus
        self.on_send = on_send
        self.title(f"AWIPS II Text {number}  |  KLOT LOTIEM")
        self.configure(background=ui.BG)
        ui.center(self, 900, 700, parent)
        self.minsize(780, 600)
        self._build()
        self._enter()

    def _build(self) -> None:
        head = ttk.Frame(self, style="Panel.TFrame", padding=(10, 6))
        head.pack(fill="x")
        ttk.Label(head, text=f"AWIPS II TEXT {self.number}", style="Title.TLabel").pack(
            side="left"
        )
        ttk.Label(head, text="  KLOT  |  Chicago/Romeoville", style="Muted.TLabel").pack(
            side="left"
        )
        self.clock = tk.StringVar(value="")
        ttk.Label(head, textvariable=self.clock, style="Muted.TLabel").pack(side="right")

        form = ttk.Frame(self, padding=(8, 4))
        form.pack(fill="x")
        for col in range(6):
            form.columnconfigure(col, weight=1)

        self.product = tk.StringVar(value="Special Weather Statement")
        self.ttaa = tk.StringVar(value="WWUS83")
        self.cccc = tk.StringVar(value="KLOT")
        self.bbb = tk.StringVar(value="NOR")
        self.wsfo = tk.StringVar(value="CHI")
        self.addressee = tk.StringVar(value="ALL")
        self.ugc = tk.StringVar(value="INZ001 INZ002")

        fields = [
            ("PRODUCT", ttk.Combobox(
                form, textvariable=self.product, state="readonly",
                values=[awips.product(p).name for p in awips.PRODUCT_ORDER],
            )),
            ("TTAAii", ttk.Entry(form, textvariable=self.ttaa, width=10)),
            ("CCCC", ttk.Entry(form, textvariable=self.cccc, width=8)),
            ("BBB", ttk.Combobox(form, textvariable=self.bbb, state="readonly", width=6,
                                 values=awips.BBB_OPTIONS)),
            ("WSFO", ttk.Entry(form, textvariable=self.wsfo, width=6)),
            ("ADDRESSEE", ttk.Entry(form, textvariable=self.addressee, width=8)),
        ]
        for idx, (label, widget) in enumerate(fields):
            ttk.Label(form, text=label, style="Muted.TLabel").grid(
                row=0, column=idx * 2, sticky="w", padx=(4, 2)
            )
            widget.grid(row=0, column=idx * 2 + 1, sticky="ew", padx=(0, 6), pady=2)
        ttk.Label(form, text="UGC", style="Muted.TLabel").grid(row=1, column=0, sticky="w",
                                                              padx=(4, 2))
        ttk.Entry(form, textvariable=self.ugc).grid(
            row=1, column=1, columnspan=5, sticky="ew", padx=(0, 6), pady=2
        )
        ttk.Button(form, text="ENTER", command=self._enter).grid(row=1, column=6, padx=2)
        ttk.Button(form, text="PRODUCT TEXT", command=self._load_product).grid(
            row=1, column=7, padx=2
        )

        self.header = tk.Text(
            self, height=4, wrap="none", background="#050c11", foreground=ui.OK,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 8), padx=6, pady=4, state="disabled",
        )
        self.header.pack(fill="x", padx=8)

        holder = ttk.Frame(self, padding=(8, 6))
        holder.pack(fill="both", expand=True)
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.body = ui.text_widget(holder, height=20)
        self.body.frame.grid(row=0, column=0, sticky="nsew")
        self.body.insert(
            "1.0",
            "The National Weather Service in Chicago has issued a Special Weather "
            "Statement for northwest Indiana.\n\n"
            "At 3:52 PM CDT, a strong thunderstorm was located near Valparaiso, moving "
            "northeast at 30 miles per hour.\n\n"
            "Locations impacted include Valparaiso, Portage, Chesterton, and Hebron.\n\n"
            "PRECAUTIONARY/PREPAREDNESS ACTIONS...\n\n"
            "If outdoors, consider seeking shelter inside a building.\n\n$$",
        )

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(8, 6))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="SEND / QUEUE TO BMH", style="Accent.TButton",
                   command=self._send).pack(side="left")
        ttk.Button(buttons, text="COPY", command=self._copy).pack(side="left", padx=4)
        ttk.Button(buttons, text="REWRAP", command=self._rewrap).pack(side="left")
        ttk.Button(buttons, text="CLOSE", command=self.destroy).pack(side="right")
        self.status = tk.StringVar(value=f"Text {self.number} ready")
        ttk.Label(buttons, textvariable=self.status, style="Muted.TLabel").pack(
            side="left", padx=12
        )
        self._tick()

    def _tick(self) -> None:
        if getattr(self, "_closed", False):
            return
        now, label = tz.central_now()
        self.clock.set(f"{now:%H:%M:%S} {label}")
        try:
            self._tick_job = self.after(1000, self._tick)
        except tk.TclError:
            pass

    def destroy(self) -> None:
        self._closed = True
        if getattr(self, "_tick_job", None):
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
        super().destroy()

    def _product(self) -> awips.Product:
        return next(
            (awips.product(p) for p in awips.PRODUCT_ORDER
             if awips.product(p).name == self.product.get()),
            awips.product("SPS"),
        )

    def _ugc(self) -> list[str]:
        return zones.parse_ugc(self.ugc.get()) or list(self._product().ugc) or ["INZ001"]

    def _header_text(self) -> str:
        prod = self._product()
        bbb = self.bbb.get()
        return "\n".join(
            [
                f"{self.ttaa.get() or prod.wmo} {self.cccc.get() or 'KLOT'} "
                f"{tz.awips_timestamp(tz.utc_now())}"
                + (f" {bbb}" if bbb not in ("NOR", "NONE", "-") else ""),
                f"{prod.pil}{self.settings.get('text_workstation.product_designator', 'LOT')}",
                f"WSFO ID... {self.wsfo.get()}",
                f"ADDRESSEE... {self.addressee.get()}",
            ]
        )

    def _enter(self) -> None:
        self.header.configure(state="normal")
        self.header.delete("1.0", "end")
        self.header.insert("1.0", self._header_text())
        self.header.configure(state="disabled")
        self.status.set(f"header entered for {self.product.get()}")

    def _load_product(self) -> None:
        from lotwps.weather import WeatherModel

        model = WeatherModel(start=tz.central_now()[0].date())
        prod = self._product()
        text = ""
        if prod.pil == "ZFPLOT":
            text = model.radio_forecast("Valparaiso", self.settings.station("WXJ75"), 7)
        elif prod.pil == "HWOLOT":
            text = model.hazardous_outlook()
        elif prod.pil == "AFDLOT":
            text = model.discussion_script()
        elif prod.pil == "CLILOT":
            text = model.climate_summary_script()
        elif prod.pil == "MFMLOT":
            text = model.marine_script()
        else:
            text = model.key_messages()
        self.body.delete("1.0", "end")
        self.body.insert("1.0", text + "\n\n$$")
        self.status.set(f"product text loaded: {prod.name}")

    def _rewrap(self) -> None:
        import textwrap

        raw = self.body.get("1.0", "end-1c")
        paras = [p.strip() for p in raw.split("\n\n") if p.strip()]
        self.body.delete("1.0", "end")
        self.body.insert("1.0", "\n\n".join(textwrap.fill(p, 69) for p in paras))

    def _compose(self) -> str:
        prod = self._product()
        ugc = self._ugc()
        body = self.body.get("1.0", "end-1c").strip()
        return "\n".join(
            [
                self._header_text(),
                zones.ugc_block(ugc, tz.awips_timestamp(tz.utc_now())),
                "",
                body,
                "",
                "$$",
            ]
        )

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self._compose())
        self.status.set("product copied to clipboard")

    def _send(self) -> None:
        prod = self._product()
        ugc = self._ugc()
        text = self._compose()
        self.bus.publish(
            "product",
            {
                "product": {"pil": prod.awips_id, "name": prod.name, "code": prod.pil},
                "ugc": ugc,
                "text": text,
                "subject": f"{prod.name} for {zones.describe_area(ugc)}",
                "routes": ["BMH"],
                "text_workstation": self.number,
            },
            target="ALL",
        )
        self.status.set(f"sent {prod.name} to BMH / LOTIEM")
        if self.on_send:
            self.on_send(prod, text)
        self.after(300, self.destroy)


class CaveLot:
    def __init__(self) -> None:
        self.root = appkit.boot(
            "CAVE-LOT  |  AWIPS II  |  KLOT Chicago/Romeoville",
            (1420, 920), (1160, 760),
        )
        self.settings = __import__("lotwps.config", fromlist=["settings"]).settings()
        self.store = alert_mod.store()
        self.bus = bus_mod.Bus("LOTWPS")
        self.text_windows: list[AwipsTextWindow] = []
        self.layer_var = tk.StringVar(value=PRODUCT_LAYERS[0][0])
        self.animate = False

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._closed = False
        self._tick_job = None
        self._refresh_alerts()
        self._tick()
        self.log("CAVE-LOT D2D online - KLOT CWA")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self._build_menu()
        root = self.root

        header = ttk.Frame(root, style="Panel.TFrame", padding=(10, 6))
        header.pack(fill="x")
        ttk.Label(header, text="CAVE-LOT", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header, text="  AWIPS II  |  KLOT  |  Chicago/Romeoville, Illinois",
            style="Muted.TLabel",
        ).pack(side="left")
        self.clock = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock, style="Header.TLabel").pack(side="right")
        ttk.Button(header, text="RESTORE D2D", command=self._restore).pack(
            side="right", padx=8
        )

        body = ttk.Frame(root, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        self._build_left(body)
        self._build_map(body)
        self._build_right(body)

        self.status = ui.StatusBar(root)
        self.status.pack(fill="x", side="bottom")
        self.status.left.set("Base Reflectivity  |  NEXRAD  |  LOT CWA")
        self.status.middle.set("WFO LOT  |  Chicago/Romeoville")
        self.status.right.set(
            f"LOTIEM {self.settings.get('text_workstation.ip')}:"
            f"{self.settings.get('text_workstation.port')}"
        )

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        session = tk.Menu(menubar, tearoff=False)
        session.add_command(label="Restore D2D", command=self._restore)
        session.add_command(label="Exit", command=self._close)
        menubar.add_cascade(label="Session", menu=session)

        text_menu = tk.Menu(menubar, tearoff=False)
        for number in range(1, 6):
            text_menu.add_command(
                label=f"AWIPS II Text {number}",
                command=lambda n=number: self._open_text(n),
            )
        menubar.add_cascade(label="Text Workstations", menu=text_menu)

        warngen = tk.Menu(menubar, tearoff=False)
        warngen.add_command(
            label="WarnGen - Single Storm", command=lambda: self._warngen("Single Storm")
        )
        warngen.add_command(
            label="WarnGen - Line of Storms", command=lambda: self._warngen("Line of Storms")
        )
        warngen.add_command(label="WatchGen", command=self._watchgen)
        menubar.add_cascade(label="WarnGen", menu=warngen)

        products = tk.Menu(menubar, tearoff=False)
        for name, _label in PRODUCT_LAYERS:
            products.add_command(label=name, command=lambda n=name: self._set_layer(n))
        menubar.add_cascade(label="Products", menu=products)
        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About CAVE-LOT", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)

    def _build_left(self, parent: ttk.Frame) -> None:
        dock = ttk.Frame(parent)
        dock.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        dock.rowconfigure(1, weight=1)
        dock.columnconfigure(0, weight=1)

        layers = ui.section(dock, "Layers")
        layers.grid(row=0, column=0, sticky="new", pady=(0, 8))
        self.radar_var = tk.BooleanVar(value=True)
        self.cities_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(layers, text="Radar", variable=self.radar_var,
                        command=self._toggle_layers).pack(anchor="w")
        ttk.Checkbutton(layers, text="Cities", variable=self.cities_var,
                        command=self._toggle_layers).pack(anchor="w")
        ttk.Label(layers, text="PRODUCT", style="Muted.TLabel").pack(anchor="w", pady=(6, 0))
        box = ttk.Combobox(
            layers, textvariable=self.layer_var, state="readonly",
            values=[name for name, _ in PRODUCT_LAYERS],
        )
        box.pack(fill="x", pady=2)
        box.bind("<<ComboboxSelected>>", lambda _e: self._set_layer(self.layer_var.get()))

        anim = ui.section(dock, "Animation")
        anim.grid(row=1, column=0, sticky="nsew")
        self.anim_label = tk.StringVar(value="frame 6 / 12")
        self.frame_scale = tk.Scale(
            anim, from_=1, to=12, orient="horizontal", background=ui.PANEL,
            foreground=ui.TEXT, troughcolor=ui.FIELD, highlightthickness=0,
            command=self._on_frame,
        )
        self.frame_scale.set(6)
        self.frame_scale.pack(fill="x")
        ttk.Label(anim, textvariable=self.anim_label, style="Muted.TLabel").pack(anchor="w")
        ttk.Button(anim, text="START ANIMATION", command=self._start_animation).pack(
            fill="x", pady=(6, 2)
        )
        ttk.Button(anim, text="STOP ANIMATION", command=self._stop_animation).pack(fill="x")
        ttk.Button(anim, text="CURRENT FRAME", command=self._single_frame).pack(
            fill="x", pady=(6, 0)
        )

        alert = ui.section(dock, "Active Alerts")
        alert.grid(row=2, column=0, sticky="new", pady=(8, 0))
        self.mini_alerts = tk.Listbox(
            alert, height=6, background=ui.FIELD, foreground=ui.TEXT,
            selectbackground=ui.ACCENT_DARK, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 8),
        )
        self.mini_alerts.pack(fill="both", expand=True)
        ttk.Button(alert, text="REFRESH", command=self._refresh_alerts).pack(
            fill="x", pady=(4, 0)
        )

    def _build_map(self, parent: ttk.Frame) -> None:
        frame = ttk.Frame(parent)
        frame.grid(row=0, column=1, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        self.map = mapview.MapCanvas(
            frame, height=640, title="KLOT / LOT  D2D  BASE REFLECTIVITY",
        )
        self.map.grid(row=0, column=0, sticky="nsew")
        self.map.canvas.bind("<Motion>", self._on_motion)
        self.map.canvas.bind("<Button-1>", self._on_click)

        bar = ttk.Frame(frame, padding=(0, 4))
        bar.grid(row=1, column=0, sticky="ew")
        ttk.Button(
            bar, text="WARNGEN - SINGLE STORM",
            command=lambda: self._warngen("Single Storm"),
        ).pack(side="left")
        ttk.Button(
            bar, text="WARNGEN - LINE OF STORMS",
            command=lambda: self._warngen("Line of Storms"),
        ).pack(side="left", padx=4)
        ttk.Button(bar, text="WATCHGEN", command=self._watchgen).pack(side="left")
        ttk.Button(bar, text="TEXT 1", command=lambda: self._open_text(1)).pack(
            side="right"
        )
        for number in (5, 4, 3, 2):
            ttk.Button(bar, text=f"TEXT {number}",
                       command=lambda n=number: self._open_text(n)).pack(
                side="right", padx=(0, 3)
            )

    def _build_right(self, parent: ttk.Frame) -> None:
        dock = ttk.Frame(parent, width=300)
        dock.grid(row=0, column=2, sticky="nsew", padx=(6, 0))
        dock.columnconfigure(0, weight=1)
        dock.rowconfigure(1, weight=1)

        tools = ui.section(dock, "WarnGen Tools")
        tools.grid(row=0, column=0, sticky="new", pady=(0, 8))
        for label, command in [
            ("SINGLE STORM POLYGON", lambda: self._warngen("Single Storm")),
            ("LINE OF STORMS POLYGON", lambda: self._warngen("Line of Storms")),
            ("TORNADO WARNING", lambda: self._quick("TOR")),
            ("SEVERE THUNDERSTORM WARNING", lambda: self._quick("SVR")),
            ("FLASH FLOOD WARNING", lambda: self._quick("FFW")),
            ("WATCHGEN", self._watchgen),
        ]:
            ttk.Button(tools, text=label, command=command).pack(fill="x", pady=2)

        ws = ui.section(dock, "AWIPS II Text Workstations")
        ws.grid(row=1, column=0, sticky="nsew")
        ttk.Label(
            ws,
            text="Open a text editor, compose the product, and send it to BMH "
                 "through LOTIEM.",
            style="Muted.TLabel", wraplength=260, justify="left",
        ).pack(anchor="w")
        for number in range(1, 6):
            ttk.Button(
                ws, text=f"TEXT {number}", command=lambda n=number: self._open_text(n)
            ).pack(fill="x", pady=2)

        traffic = ui.section(dock, "LOTIEM Traffic")
        traffic.grid(row=2, column=0, sticky="nsew", pady=(8, 0))
        holder = ttk.Frame(traffic)
        holder.pack(fill="both", expand=True)
        self.traffic = ui.tagged_log(holder, height=8)
        self.traffic.configure(state="disabled")

    # ------------------------------------------------------------- actions
    def log(self, message: str, tag: str = "") -> None:
        stamp = tz.central_now()[0].strftime("%H:%M:%S")
        self.traffic.configure(state="normal")
        self.traffic.insert("end", f"{stamp}  {message}\n", tag)
        self.traffic.see("end")
        self.traffic.configure(state="disabled")
        self.status.left.set(message[:110])

    def _set_layer(self, name: str) -> None:
        self.layer_var.set(name)
        label = next((label for n, label in PRODUCT_LAYERS if n == name), name)
        self.map.title = f"KLOT / LOT  D2D  {label}"
        self.map.draw()
        self.status.left.set(f"{name}  |  LOT CWA")

    def _toggle_layers(self) -> None:
        self.map.radar_on = bool(self.radar_var.get())
        self.map.cities_on = bool(self.cities_var.get())
        self.map.draw()

    def _on_frame(self, value) -> None:
        if not hasattr(self, "map"):
            return
        self.map.set_frame(int(float(value)))
        self.anim_label.set(f"frame {int(float(value))} / 12")

    def _single_frame(self) -> None:
        self.frame_scale.set(self.map.frame_index)
        self.map.set_frame(self.map.frame_index)
        self.anim_label.set(f"frame {self.map.frame_index} / 12")

    def _start_animation(self) -> None:
        self.map.start_animation()
        self.animate = True
        self.log("radar animation started")

    def _stop_animation(self) -> None:
        self.map.stop_animation()
        self.animate = False
        self.log("radar animation stopped")

    def _on_motion(self, event) -> None:
        lat, lon = self.map.projection.to_latlon(event.x, event.y)
        nearest = awips.cities_near(lat, lon, 1)
        self.status.middle.set(
            f"{lat:.3f} / {lon:.3f}  |  near {nearest[0] if nearest else 'LOT CWA'}"
        )

    def _on_click(self, event) -> None:
        lat, lon = self.map.projection.to_latlon(event.x, event.y)
        ugc = zones.zones_near(lat, lon, 0.4)
        self.log(f"map cursor {lat:.3f} / {lon:.3f}  zones {' '.join(ugc[:6])}")

    def _open_text(self, number: int) -> None:
        window = AwipsTextWindow(
            self.root, number, self.settings, self.store, self.bus,
            on_send=self._text_sent,
        )
        self.text_windows.append(window)
        self.log(f"AWIPS II Text {number} opened")

    def _text_sent(self, prod, _text) -> None:
        self.log(f"Text workstation sent {prod.name} to BMH", "ok")

    def _warngen(self, mode: str) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, title=f"WarnGen  |  CAVE-LOT  ({mode})",
            on_issue=self._warngen_issued,
        )
        dialog.mode_var.set(mode)
        dialog._update_preview()

    def _watchgen(self) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, title="WatchGen  |  CAVE-LOT", on_issue=self._warngen_issued
        )
        dialog.product_var.set("Tornado Watch")
        dialog._update_preview()

    def _quick(self, code: str) -> None:
        from warngen_dialog import WarnGenDialog

        prod = awips.product(code)
        dialog = WarnGenDialog(
            self.root, title=f"WarnGen  |  {prod.name}", on_issue=self._warngen_issued
        )
        dialog.product_var.set(prod.name)
        dialog._update_preview()

    def _warngen_issued(self, _text, prod, ugc, _cell, _points) -> None:
        self._refresh_alerts()
        self.log(f"WarnGen issued {prod.name} for {zones.describe_area(ugc)}", "warn")

    def _refresh_alerts(self) -> None:
        self.mini_alerts.delete(0, "end")
        active = self.store.active()
        overlays = []
        for alert in active:
            self.mini_alerts.insert(
                "end", f"{alert.status} {alert.event} - {alert.area}"
            )
            if alert.polygon:
                overlays.append(
                    {
                        "polygon": alert.polygon,
                        "color": TIER_COLORS.get(alert.tier, ui.WARN),
                        "label": alert.event,
                    }
                )
        self.map.set_alerts(overlays)
        self.status.right.set(
            f"{len(active)} active alerts  |  LOTIEM "
            f"{self.settings.get('text_workstation.ip')}:"
            f"{self.settings.get('text_workstation.port')}"
        )

    def _restore(self) -> None:
        self.map.set_bounds(mapview.DEFAULT_BOUNDS)
        self.map.radar_on = True
        self.map.cities_on = True
        self.radar_var.set(True)
        self.cities_var.set(True)
        self.frame_scale.set(6)
        self.map.set_frame(6)
        self.layer_var.set(PRODUCT_LAYERS[0][0])
        self._set_layer(PRODUCT_LAYERS[0][0])
        ui.center(self.root, 1420, 920)
        self.log("RESTORE D2D - map, layers and layout reset")

    def _about(self) -> None:
        messagebox.showinfo(
            "About CAVE-LOT",
            "CAVE-LOT D2D  |  AWIPS II client\n"
            "KLOT  |  Chicago/Romeoville, Illinois\n\n"
            "Radar, alert polygons, WarnGen / WatchGen, and AWIPS II Text 1-5.\n"
            "LOTIEM: 192.168.10.144:6000",
            parent=self.root,
        )

    def _tick(self) -> None:
        if getattr(self, "_closed", False):
            return
        now, label = tz.central_now()
        self.clock.set(f"{now:%H:%M:%S} {label}  {now:%a %b} {now.day}")
        if self.animate:
            self.frame_scale.set(self.map.frame_index)
            self.anim_label.set(f"frame {self.map.frame_index} / 12")
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
            self._tick_job = None
        for window in list(self.text_windows):
            try:
                window.destroy()
            except Exception:
                pass
        self.root.destroy()

    def mainloop(self) -> None:
        self.root.mainloop()


def main() -> None:
    CaveLot().mainloop()


if __name__ == "__main__":
    main()
