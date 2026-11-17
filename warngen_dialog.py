"""WarnGen / WatchGen storm-polygon dialog shared by BMH and the text workstation.

Pick a hazard, draw a storm polygon on the KLOT radar map (or auto-generate
one), and the dialog composes the full AWIPS warning/watch product with the
``LAT...LON`` and ``TIME...MOT...LOC`` blocks. Issuing it optionally publishes
the product on the LOTIEM bus and raises a SAME alert in the shared store.
"""

from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lotwps import alerts as alert_mod, awips, bus as bus_mod, mapview, tz, ui, zones
from lotwps.weather import display_name, spell_callsign

CHOICES = [
    ("TOR", "Tornado Warning"),
    ("SVR", "Severe Thunderstorm Warning"),
    ("FFW", "Flash Flood Warning"),
    ("EWW", "Extreme Wind Warning"),
    ("TOA", "Tornado Watch"),
    ("SVA", "Severe Thunderstorm Watch"),
]

WARNING_CODES = {"TOR", "SVR", "FFW", "EWW"}
WATCH_CODES = {"TOA", "SVA"}


class WarnGenDialog(tk.Toplevel):
    def __init__(
        self,
        parent: tk.Misc,
        on_issue=None,
        engine=None,
        default_ugc: list[str] | None = None,
        title: str = "WarnGen  |  KLOT Storm Polygon",
    ) -> None:
        super().__init__(parent)
        self.title(title)
        self.configure(background=ui.BG)
        self.on_issue = on_issue
        self.engine = engine
        self.bus = bus_mod.Bus("LOTWPS")
        self.points: list[tuple[float, float]] = []
        self.last_text = ""
        self._tick_job = None

        ui.center(self, 1180, 780, parent)
        self.minsize(1020, 680)

        self._build(default_ugc or ["INZ001", "INZ002"])
        self.transient(parent)
        self.grab_set()

    # ------------------------------------------------------------------ UI
    def _build(self, default_ugc: list[str]) -> None:
        header = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        header.pack(fill="x")
        ttk.Label(
            header, text="WARNGEN", style="Title.TLabel"
        ).pack(side="left")
        ttk.Label(
            header,
            text="  draw the polygon on the KLOT radar mosaic, then preview and issue",
            style="Muted.TLabel",
        ).pack(side="left")
        self.clock_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock_var, style="Header.TLabel").pack(side="right")

        body = ttk.Frame(self, padding=(10, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        map_frame = ui.section(body, "KLOT Polygon Tool")
        map_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 8))
        self.map = mapview.MapCanvas(
            map_frame, interactive=True, on_polygon=self._polygon_done,
            height=520, title="KLOT / LOT  D2D   WARNGEN",
        )
        self.map.pack(fill="both", expand=True)

        map_row = ttk.Frame(map_frame)
        map_row.pack(fill="x", pady=(6, 0))
        ttk.Button(map_row, text="CLEAR POLYGON", command=self._clear_polygon).pack(side="left")
        ttk.Button(map_row, text="AUTO POLYGON", command=self._auto_polygon).pack(
            side="left", padx=4
        )
        ttk.Label(
            map_row, text="click vertices  |  double-click to finish  |  right-click clears",
            style="Muted.TLabel",
        ).pack(side="left", padx=8)

        right = ttk.Frame(body)
        right.grid(row=0, column=1, sticky="nsew")
        right.rowconfigure(2, weight=1)
        right.columnconfigure(0, weight=1)

        form = ui.section(right, "Hazard")
        form.grid(row=0, column=0, sticky="ew", pady=(0, 8))
        form.columnconfigure(1, weight=1)

        self.product_var = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Label(form, text="PRODUCT", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=2
        )
        product = ttk.Combobox(
            form, textvariable=self.product_var, state="readonly",
            values=[label for _code, label in CHOICES],
        )
        product.grid(row=0, column=1, columnspan=3, sticky="ew", pady=2)
        product.bind("<<ComboboxSelected>>", lambda _e: self._update_preview())

        self.mode_var = tk.StringVar(value="Single Storm")
        mode_row = ttk.Frame(form)
        mode_row.grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 2))
        ttk.Label(mode_row, text="MODE", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Radiobutton(
            mode_row, text="Single Storm", value="Single Storm", variable=self.mode_var,
            command=self._update_preview,
        ).pack(side="left", padx=2)
        ttk.Radiobutton(
            mode_row, text="Line of Storms", value="Line of Storms", variable=self.mode_var,
            command=self._update_preview,
        ).pack(side="left", padx=2)

        self.cell_name = tk.StringVar(value="Valparaiso")
        self.lat_var = tk.StringVar(value="41.47")
        self.lon_var = tk.StringVar(value="-87.06")
        self.motion_var = tk.IntVar(value=45)
        self.speed_var = tk.IntVar(value=35)
        self.lead_var = tk.IntVar(value=30)
        self.duration_var = tk.IntVar(value=45)

        fields = [
            ("STORM / CELL", self.cell_name, None),
            ("LATITUDE", self.lat_var, None),
            ("LONGITUDE", self.lon_var, None),
            ("MOTION (DEG)", self.motion_var, (0, 359)),
            ("SPEED (KT)", self.speed_var, (0, 120)),
            ("LEAD TIME (MIN)", self.lead_var, (1, 180)),
            ("SAME DURATION (MIN)", self.duration_var, (1, 180)),
        ]
        for idx, (label, var, bounds) in enumerate(fields, start=2):
            ttk.Label(form, text=label, style="Muted.TLabel").grid(
                row=idx, column=0, sticky="w", pady=1
            )
            if bounds:
                ttk.Spinbox(
                    form, from_=bounds[0], to=bounds[1], textvariable=var, width=7,
                ).grid(row=idx, column=1, sticky="w", pady=1)
            else:
                ttk.Entry(form, textvariable=var, width=24).grid(
                    row=idx, column=1, columnspan=3, sticky="ew", pady=1
                )

        self.ugc_var = tk.StringVar(value=" ".join(default_ugc))
        ttk.Label(form, text="UGC", style="Muted.TLabel").grid(
            row=9, column=0, sticky="w", pady=2
        )
        ttk.Entry(form, textvariable=self.ugc_var, width=24).grid(
            row=9, column=1, columnspan=2, sticky="ew", pady=2
        )
        ttk.Button(form, text="FROM POLYGON", command=self._resolve_ugc).grid(
            row=9, column=3, padx=(4, 0)
        )

        options = ttk.Frame(form)
        options.grid(row=10, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self.same_var = tk.BooleanVar(value=True)
        self.bus_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(options, text="SAME alert", variable=self.same_var).pack(side="left")
        ttk.Checkbutton(options, text="publish to LOTIEM", variable=self.bus_var).pack(
            side="left", padx=10
        )

        preview_frame = ui.section(right, "Product Preview")
        preview_frame.grid(row=2, column=0, sticky="nsew")
        preview_frame.rowconfigure(0, weight=1)
        preview_frame.columnconfigure(0, weight=1)
        holder = ttk.Frame(preview_frame)
        holder.grid(row=0, column=0, sticky="nsew")
        self.preview = ui.scrolled_text(holder, height=18)
        self.preview.configure(wrap="none")

        buttons = ttk.Frame(right, style="Panel.TFrame")
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        ttk.Button(buttons, text="PREVIEW", command=self._update_preview).pack(side="left")
        ttk.Button(
            buttons, text="ISSUE PRODUCT", style="Accent.TButton", command=self._issue
        ).pack(side="left", padx=6)
        ttk.Button(buttons, text="COPY TEXT", command=self._copy).pack(side="left")
        ttk.Button(buttons, text="CLOSE", command=self.destroy).pack(side="right")

        self._tick()
        self._update_preview()

    # ------------------------------------------------------------- helpers
    def _tick(self) -> None:
        now, label = tz.central_now()
        self.clock_var.set(f"{now:%H:%M:%S} {label}")
        try:
            self._tick_job = self.after(1000, self._tick)
        except tk.TclError:
            pass

    def destroy(self) -> None:
        if self._tick_job:
            try:
                self.after_cancel(self._tick_job)
            except Exception:
                pass
            self._tick_job = None
        super().destroy()

    def _product(self):
        label = self.product_var.get()
        code = next((c for c, name in CHOICES if name == label), "SVR")
        return awips.product(code)

    def _ugc(self) -> list[str]:
        found = zones.parse_ugc(self.ugc_var.get())
        return found or ["INZ001", "INZ002"]

    def _cell(self) -> awips.StormCell:
        try:
            lat = float(self.lat_var.get())
            lon = float(self.lon_var.get())
        except ValueError:
            lat, lon = 41.47, -87.06
        return awips.StormCell(
            lat=lat,
            lon=lon,
            motion_deg=int(self.motion_var.get()),
            speed_kt=int(self.speed_var.get()),
            rotation=self.product_var.get().startswith("Tornado"),
            name=self.cell_name.get().strip(),
            wind_mph=60,
            hail_in=1.0,
        )

    # --------------------------------------------------------- map actions
    def _polygon_done(self, points: list[tuple[float, float]]) -> None:
        self.points = points
        self._sync_from_polygon()

    def _sync_from_polygon(self) -> None:
        if not self.points:
            return
        lat, lon = awips.polygon_centroid(self.points)
        self.lat_var.set(f"{lat:.4f}")
        self.lon_var.set(f"{lon:.4f}")
        if not self.cell_name.get().strip():
            self.cell_name.set(display_name(awips.cities_near(lat, lon, 1)[0]))
        self._resolve_ugc()
        self._update_preview()

    def _resolve_ugc(self) -> None:
        ugc = zones.zones_for_polygon(self.points)
        if ugc:
            self.ugc_var.set(" ".join(ugc[:12]))
        self._update_preview()

    def _clear_polygon(self) -> None:
        self.points = []
        self.map.clear_polygon()
        self._update_preview()

    def _auto_polygon(self) -> None:
        cell = self._cell()
        if self.mode_var.get() == "Line of Storms":
            half_lat, half_lon = 0.22, 0.55
            points = [
                (cell.lat + half_lat, cell.lon - half_lon),
                (cell.lat + half_lat, cell.lon + half_lon),
                (cell.lat - half_lat, cell.lon + half_lon),
                (cell.lat - half_lat, cell.lon - half_lon),
            ]
        else:
            half = 0.09
            points = [
                (cell.lat + half, cell.lon - half),
                (cell.lat + half * 1.3, cell.lon + half),
                (cell.lat - half, cell.lon + half * 0.8),
                (cell.lat - half * 0.7, cell.lon - half * 1.1),
            ]
        self.points = [(round(a, 4), round(b, 4)) for a, b in points]
        self.map.points = list(self.points)
        self.map.draw_polygon_only()
        self._sync_from_polygon()

    # ------------------------------------------------------------ compose
    def compose(self) -> str:
        prod = self._product()
        ugc = self._ugc()
        cell = self._cell()
        if prod.pil in WATCH_CODES:
            text = awips.watch_product(
                prod, ugc, hours=4,
                discussion=(
                    "A line of thunderstorms will move across the region this evening."
                    if self.mode_var.get() == "Line of Storms"
                    else "Scattered thunderstorms are expected to develop this afternoon."
                ),
            )
        else:
            text = awips.warning_product(
                prod,
                ugc,
                cell,
                self.points or self._auto_points(cell),
                lead_minutes=int(self.lead_var.get()),
                line_of_storms=self.mode_var.get() == "Line of Storms",
            )
        return text

    def _auto_points(self, cell: awips.StormCell) -> list[tuple[float, float]]:
        half = 0.09
        return [
            (cell.lat + half, cell.lon - half),
            (cell.lat + half, cell.lon + half),
            (cell.lat - half, cell.lon + half),
            (cell.lat - half, cell.lon - half),
        ]

    def _update_preview(self) -> None:
        try:
            text = self.compose()
        except Exception as exc:
            text = f"(cannot compose: {exc})"
        self.last_text = text
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", text)
        self.preview.configure(state="disabled")

    def _copy(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.last_text)
        self.bus.publish("status", {"action": "copied warngen product"}, target="ALL")
        messagebox.showinfo("WarnGen", "Product text copied to the clipboard.", parent=self)

    # ------------------------------------------------------------- issue
    def _issue(self) -> None:
        prod = self._product()
        text = self.compose()
        ugc = self._ugc()
        cell = self._cell()
        polygon = self.points or self._auto_points(cell)
        label = self.product_var.get()

        if self.bus_var.get():
            self.bus.publish_product(
                text,
                {"pil": prod.awips_id, "name": prod.name, "code": prod.pil},
                ugc,
                {"polygon": polygon, "warngen": True, "mode": self.mode_var.get()},
            )

        alerted = False
        if self.same_var.get() and prod.kind in ("warning", "watch"):
            if self.engine is not None:
                self.engine.send_same_alert(
                    label,
                    ugc,
                    message=(
                        f"A {label} has been issued for {zones.describe_area(ugc)}. "
                        f"A storm was located near {cell.name}, moving northeast at "
                        f"{cell.speed_kt} miles per hour."
                    ),
                    duration_min=int(self.duration_var.get()),
                )
                alerted = True
            else:
                store = alert_mod.store()
                store.issue(
                    label,
                    ugc,
                    headline=f"{label} for {zones.describe_area(ugc)}",
                    description=(
                        f"A storm was located near {cell.name}, moving northeast at "
                        f"{cell.speed_kt} miles per hour."
                    ),
                    duration_min=int(self.duration_var.get()),
                    polygon=polygon,
                )
                alerted = True

        if self.on_issue:
            try:
                self.on_issue(text, prod, ugc, cell, polygon)
            except Exception:
                pass

        note = "SAME alert raised. " if alerted else ""
        messagebox.showinfo(
            "WarnGen",
            f"{prod.name} issued for {zones.describe_area(ugc)}.\n\n"
            f"{note}Product published to LOTIEM (192.168.10.144:6000).",
            parent=self,
        )
        self.destroy()


def open_warngen(parent, **kwargs) -> WarnGenDialog:
    return WarnGenDialog(parent, **kwargs)
