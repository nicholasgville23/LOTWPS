"""Latitude/longitude map canvas used by the AWIPS client, WarnGen and BMH.

Draws a stylised LOT county map with Lake Michigan, deterministic radar echoes,
city labels, transmitter sites, warning polygons and click-to-draw storm
polygons returning ``(lat, lon)`` vertices.
"""

from __future__ import annotations

import math
import random
import tkinter as tk
from tkinter import ttk

from . import ui, zones

DEFAULT_BOUNDS = (40.55, 42.75, -90.05, -86.10)


class GeoProjection:
    def __init__(self, bounds: tuple[float, float, float, float], width: int, height: int):
        self.lat_min, self.lat_max, self.lon_min, self.lon_max = bounds
        self.width = max(1, width)
        self.height = max(1, height)
        lon_span = self.lon_max - self.lon_min
        lat_span = self.lat_max - self.lat_min
        # scale degrees of longitude by cos(latitude) so shapes look right
        self.lon_scale = 0.74
        self.scale = min(
            self.width / max(0.001, lon_span * self.lon_scale),
            self.height / max(0.001, lat_span),
        )
        used_w = lon_span * self.lon_scale * self.scale
        used_h = lat_span * self.scale
        self.ox = (self.width - used_w) / 2.0
        self.oy = (self.height - used_h) / 2.0

    def to_xy(self, lat: float, lon: float) -> tuple[float, float]:
        x = self.ox + (lon - self.lon_min) * self.lon_scale * self.scale
        y = self.oy + (self.lat_max - lat) * self.scale
        return x, y

    def to_latlon(self, x: float, y: float) -> tuple[float, float]:
        lon = self.lon_min + (x - self.ox) / (self.lon_scale * self.scale)
        lat = self.lat_max - (y - self.oy) / self.scale
        return round(lat, 4), round(lon, 4)

    def poly(self, points: list[tuple[float, float]]) -> list[float]:
        flat: list[float] = []
        for lat, lon in points:
            x, y = self.to_xy(lat, lon)
            flat.extend((x, y))
        return flat


class RadarCell:
    def __init__(self, lat: float, lon: float, dbz: int, radius: float):
        self.lat = lat
        self.lon = lon
        self.dbz = dbz
        self.radius = radius


def _radar_cells(seed: int, count: int = 26) -> list[RadarCell]:
    rng = random.Random(seed)
    cells: list[RadarCell] = []
    for _ in range(count):
        lat = rng.uniform(40.9, 42.4)
        lon = rng.uniform(-89.4, -86.8)
        heading = rng.uniform(0, math.tau)
        length = rng.uniform(0.15, 0.75)
        for step in range(rng.randint(2, 6)):
            plat = lat + math.cos(heading) * length * step * 0.35
            plon = lon + math.sin(heading) * length * step * 0.35
            dbz = rng.choice([8, 14, 22, 30, 38, 46, 54, 62])
            cells.append(RadarCell(plat, plon, dbz, rng.uniform(0.03, 0.11)))
    return cells


class MapCanvas(ttk.Frame):
    def __init__(
        self,
        parent: tk.Misc,
        bounds: tuple[float, float, float, float] = DEFAULT_BOUNDS,
        height: int = 420,
        legend: bool = True,
        interactive: bool = False,
        on_polygon=None,
        title: str = "KLOT / LOT  D2D",
    ):
        super().__init__(parent)
        self.bounds = bounds
        self.legend = legend
        self.title = title
        self.radar_on = True
        self.cities_on = True
        self.alerts: list[dict] = []
        self.markers: list[tuple[float, float, str, str]] = []
        self.interactive = interactive
        self.on_polygon = on_polygon
        self.points: list[tuple[float, float]] = []
        self.frame_index = 6
        self.frames = 12
        self.animate = False
        self._animate_job = None
        self._proj = GeoProjection(bounds, 800, height)
        self.canvas = tk.Canvas(
            self, height=height, background="#04070b", highlightthickness=1,
            highlightbackground=ui.BORDER, cursor="crosshair" if interactive else "",
        )
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<Configure>", self._on_resize)
        if interactive:
            self.canvas.bind("<Button-1>", self._on_click)
            self.canvas.bind("<Double-Button-1>", self._on_finish)
            self.canvas.bind("<Button-3>", lambda _e: self.clear_polygon())
        self.draw()

    # -- geometry --------------------------------------------------------
    @property
    def projection(self) -> GeoProjection:
        return self._proj

    def _on_resize(self, event) -> None:
        self._proj = GeoProjection(self.bounds, event.width, event.height)
        self.draw()

    def set_bounds(self, bounds: tuple[float, float, float, float]) -> None:
        self.bounds = bounds
        self._proj = GeoProjection(bounds, self.canvas.winfo_width(), self.canvas.winfo_height())
        self.draw()

    # -- public API ------------------------------------------------------
    def set_alerts(self, alerts: list[dict]) -> None:
        self.alerts = alerts
        self.draw()

    def set_markers(self, markers: list[tuple[float, float, str, str]]) -> None:
        self.markers = markers
        self.draw()

    def set_frame(self, index: int) -> None:
        self.frame_index = index
        self.draw_radar_only()

    def start_animation(self, interval_ms: int = 420) -> None:
        self.animate = True
        self._animate()

    def stop_animation(self) -> None:
        self.animate = False
        if self._animate_job:
            self.after_cancel(self._animate_job)
            self._animate_job = None

    def _animate(self) -> None:
        if not self.animate:
            return
        self.frame_index = self.frame_index % self.frames + 1
        self.draw_radar_only()
        self._animate_job = self.after(420, self._animate)

    def toggle_radar(self) -> None:
        self.radar_on = not self.radar_on
        self.draw()

    def toggle_cities(self) -> None:
        self.cities_on = not self.cities_on
        self.draw()

    def clear_polygon(self) -> None:
        self.points.clear()
        self.draw_polygon_only()

    def finish_polygon(self) -> list[tuple[float, float]]:
        points = list(self.points)
        if len(points) >= 3 and self.on_polygon:
            self.on_polygon(points)
        return points

    # -- drawing ---------------------------------------------------------
    def draw(self) -> None:
        c = self.canvas
        c.delete("all")
        width = c.winfo_width() or 800
        height = c.winfo_height() or 420
        self._proj = GeoProjection(self.bounds, width, height)

        c.create_rectangle(0, 0, width, height, fill="#04070b", outline="")
        self._draw_water()
        self._draw_counties()
        c.delete("radar")
        self._draw_radar()
        self._draw_alerts()
        if self.cities_on:
            self._draw_cities()
        self._draw_transmitters()
        self._draw_hud(width, height)
        self._draw_title()
        if self.legend:
            self._draw_legend()
        self.draw_polygon_only()

    # ocean / lake
    def _draw_water(self) -> None:
        flat = self._proj.poly(zones.WATER_POLYGON)
        if len(flat) >= 6:
            self.canvas.create_polygon(
                flat, fill="#0a1f2e", outline="#2e6a8f", width=1, tags="water"
            )

    def _draw_counties(self) -> None:
        for zone in zones.LAND_ZONES:
            half_lat = 0.145
            half_lon = 0.19
            corners = [
                (zone.lat + half_lat, zone.lon - half_lon),
                (zone.lat + half_lat, zone.lon + half_lon),
                (zone.lat - half_lat, zone.lon + half_lon),
                (zone.lat - half_lat, zone.lon - half_lon),
            ]
            flat = self._proj.poly(corners)
            self.canvas.create_polygon(
                flat, fill="#0b141c", outline="#2a4257", width=1, tags="county"
            )
            zone_color = "#4d7ea8" if zone.state == "IL" else "#6f8d5e"
            self.canvas.create_text(
                flat[0] + 4, flat[1] + 6, anchor="nw", text=zone.ugc,
                fill=zone_color, font=(ui.MONO, 6), tags="county",
            )

    def _draw_radar(self) -> None:
        if not self.radar_on:
            return
        c = self.canvas
        seed = 20261116 + self.frame_index * 7
        cells = _radar_cells(seed)
        # speckle layer
        rng = random.Random(seed + 3)
        for _ in range(240):
            lat = rng.uniform(self.bounds[0], self.bounds[1])
            lon = rng.uniform(self.bounds[2], self.bounds[3])
            x, y = self._proj.to_xy(lat, lon)
            c.create_rectangle(
                x, y, x + 2, y + 2, fill="#123349", outline="", tags="radar"
            )
        for cell in cells:
            x, y = self._proj.to_xy(cell.lat, cell.lon)
            r = max(2.0, cell.radius * self._proj.scale)
            c.create_oval(
                x - r, y - r, x + r, y + r,
                fill=ui.dbz_color(cell.dbz), outline="", tags="radar",
            )
            if cell.dbz >= 54:
                core = r * 0.45
                c.create_oval(
                    x - core, y - core, x + core, y + core,
                    fill="#f9f871", outline="", tags="radar",
                )
        # one rotation marker
        cell = cells[len(cells) // 3]
        x, y = self._proj.to_xy(cell.lat, cell.lon)
        c.create_polygon(
            x, y - 12, x - 6, y - 22, x + 6, y - 22,
            fill="#ff4dd2", outline="#ffd6f5", tags="radar",
        )

    def draw_radar_only(self) -> None:
        self.canvas.delete("radar")
        self._draw_radar()

    def _draw_alerts(self) -> None:
        for alert in self.alerts:
            points = alert.get("polygon") or []
            if not points:
                continue
            flat = self._proj.poly(points)
            if len(flat) < 6:
                continue
            color = alert.get("color", ui.WARN)
            self.canvas.create_polygon(
                flat, outline=color, width=2, fill="", dash=(4, 2), tags="alert"
            )
            label = alert.get("label", "")
            if label:
                self.canvas.create_text(
                    flat[0], flat[1] - 8, text=label, fill=color, anchor="w",
                    font=(ui.MONO, 7, "bold"), tags="alert",
                )

    def _draw_cities(self) -> None:
        major = {"Chicago", "Rockford", "Valparaiso", "Gary", "Joliet", "Aurora",
                 "Waukegan", "South Bend", "Michigan City", "Ottawa", "Kankakee"}
        for name, (lat, lon) in zones.CITY_COORDS.items():
            if not (self.bounds[0] <= lat <= self.bounds[1]):
                continue
            if not (self.bounds[2] <= lon <= self.bounds[3]):
                continue
            x, y = self._proj.to_xy(lat, lon)
            is_major = name in major
            if is_major:
                self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill="#cfe3f5", outline="")
            self.canvas.create_text(
                x + 5, y + 1, text=name, anchor="w",
                fill="#d7e6f5" if is_major else "#7f9ab0",
                font=(ui.MONO, 7 if is_major else 6, "bold" if is_major else "normal"),
                tags="city",
            )

    def _draw_transmitters(self) -> None:
        for station_id, (lat, lon) in zones.TRANSMITTERS.items():
            if not (self.bounds[0] <= lat <= self.bounds[1]):
                continue
            x, y = self._proj.to_xy(lat, lon)
            color = ui.OK if station_id != "KLOT" else ui.ACCENT
            self.canvas.create_oval(
                x - 5, y - 5, x + 5, y + 5, outline=color, width=1, tags="tx"
            )
            self.canvas.create_oval(
                x - 1, y - 1, x + 1, y + 1, fill=color, outline="", tags="tx"
            )
            self.canvas.create_text(
                x + 8, y + 9, text=station_id, anchor="w", fill=color,
                font=(ui.MONO, 7, "bold"), tags="tx",
            )

    def _draw_hud(self, width: int, height: int) -> None:
        self.canvas.create_rectangle(
            0, 0, width, 20, fill="#0b1420", outline=""
        )
        self.canvas.create_text(
            8, 10, anchor="w", text=self.title, fill=ui.MUTED, font=(ui.MONO, 8)
        )
        self.canvas.create_text(
            width - 8, 10, anchor="e",
            text=f"FRAMES: {self.frame_index:02d}/{self.frames}   KLOT  "
                 f"{_clock_text()}",
            fill=ui.MUTED, font=(ui.MONO, 8),
        )
        self.canvas.create_rectangle(
            0, height - 18, width, height, fill="#0b1420", outline=""
        )
        self.canvas.create_text(
            8, height - 9, anchor="w",
            text="NEXRAD BASE REFLECTIVITY  DBZ  -20 .. 75   |   LOT CWA",
            fill=ui.MUTED, font=(ui.MONO, 7),
        )

    def _draw_title(self) -> None:
        if not self.interactive:
            return
        self.canvas.create_text(
            12, 28, anchor="nw",
            text="POLYGON TOOL: click vertices, double-click to finish, right-click to clear",
            fill=ui.WARN, font=(ui.MONO, 8, "bold"),
        )

    def _draw_legend(self) -> None:
        x0, y0 = 12, 30
        width = 190
        self.canvas.create_rectangle(
            x0, y0, x0 + width, y0 + 46, fill="#0a121b", outline=ui.BORDER
        )
        labels = ["-20", "0", "10", "20", "30", "40", "50", "60", "70"]
        swatch = width / len(labels)
        for i, label in enumerate(labels):
            dbz = -20 + i * 10
            self.canvas.create_rectangle(
                x0 + 6 + i * swatch, y0 + 6, x0 + 6 + (i + 1) * swatch, y0 + 18,
                fill=ui.dbz_color(dbz) if dbz > 0 else "#243447", outline="",
            )
            self.canvas.create_text(
                x0 + 6 + i * swatch + swatch / 2, y0 + 24, text=label,
                fill=ui.MUTED, font=(ui.MONO, 6),
            )
        self.canvas.create_text(
            x0 + 6, y0 + 36, anchor="w", text="Storm relative velocity",
            fill=ui.MUTED, font=(ui.MONO, 7),
        )

    # -- interactive polygon --------------------------------------------
    def _on_click(self, event) -> None:
        lat, lon = self._proj.to_latlon(event.x, event.y)
        self.points.append((lat, lon))
        self.draw_polygon_only()

    def _on_finish(self, event) -> None:
        if len(self.points) >= 3:
            self.finish_polygon()

    def draw_polygon_only(self) -> None:
        self.canvas.delete("userpoly")
        if not self.points:
            return
        flat = self._proj.poly(self.points)
        if len(flat) >= 6:
            self.canvas.create_polygon(
                flat, outline="#ffd166", width=2, fill="", dash=(6, 3),
                tags="userpoly",
            )
        for lat, lon in self.points:
            x, y = self._proj.to_xy(lat, lon)
            self.canvas.create_rectangle(
                x - 3, y - 3, x + 3, y + 3, outline="#ffd166", fill="#1a1205",
                tags="userpoly",
            )
        x, y = self._proj.to_xy(*self.points[0])
        self.canvas.create_text(
            x + 8, y - 8, anchor="w",
            text=f"{int(self.points[0][0] * 100):04d} {int(abs(self.points[0][1]) * 100):04d}",
            fill="#ffd166", font=(ui.MONO, 7), tags="userpoly",
        )


def _clock_text() -> str:
    from . import tz

    now, label = tz.central_now()
    return f"{now:%H:%M:%S} {label}"


class RadarLegend(ttk.Frame):
    """Standalone horizontal legend for compact panels."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, style="Panel.TFrame")
        canvas = tk.Canvas(self, height=18, background=ui.PANEL, highlightthickness=0)
        canvas.pack(fill="x", expand=True)
        labels = ["10", "20", "30", "40", "50", "60", "70", "75"]
        width = 190
        for i, label in enumerate(labels):
            canvas.create_rectangle(
                i * (width / len(labels)), 2, (i + 1) * (width / len(labels)), 12,
                fill=ui.dbz_color(int(label)), outline="",
            )
            canvas.create_text(
                i * (width / len(labels)) + 6, 15, text=label, anchor="n",
                fill=ui.MUTED, font=(ui.MONO, 6),
            )
