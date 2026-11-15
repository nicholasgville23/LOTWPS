"""Tkinter shell for the KLOT LOTIEM Text Workstation."""
from __future__ import annotations
import json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from .engine import BroadcastQueue
from .models import AlertPriority, Station, WeatherProduct

ROOT = Path(__file__).resolve().parents[2]
CONFIG = ROOT / "config" / "stations.json"

def load_stations() -> tuple[dict, list[Station]]:
    data = json.loads(CONFIG.read_text(encoding="utf-8"))
    return data.get("application", {}), [Station(**item) for item in data.get("stations", [])]

class TextWorkstation(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.application, self.stations = load_stations()
        self.queue = BroadcastQueue(playback=self._preview_product)
        self.title(self.application.get("name", "LOTWPS Text Workstation"))
        self.geometry("1180x760")
        self.minsize(900, 600)
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._build_ui()

    def _build_ui(self) -> None:
        top = ttk.Frame(self, padding=8); top.pack(fill="x")
        ttk.Label(top, text="KLOT  |  LOTWPS / LOTIEM / BMH", font=("Segoe UI", 16, "bold")).pack(side="left")
        ttk.Label(top, text="LOCAL TEST MODE", foreground="#a05a00").pack(side="right")
        body = ttk.Panedwindow(self, orient="horizontal"); body.pack(fill="both", expand=True, padx=8, pady=4)
        left = ttk.Labelframe(body, text="Active Transmitters / Stations", padding=8)
        right = ttk.Frame(body, padding=4); body.add(left, weight=1); body.add(right, weight=4)
        self.station_list = tk.Listbox(left, height=18, exportselection=False); self.station_list.pack(fill="both", expand=True)
        for station in self.stations: self.station_list.insert("end", f"{station.station_id} — {station.display_name}")
        if self.stations: self.station_list.selection_set(0)
        compose = ttk.Labelframe(right, text="New Text Message / Weather Product", padding=8); compose.pack(fill="x")
        ttk.Label(compose, text="Product ID").grid(row=0, column=0, sticky="w")
        self.product_id = tk.StringVar(value="TEST-SPSLOT")
        ttk.Entry(compose, textvariable=self.product_id, width=24).grid(row=0, column=1, sticky="ew", padx=6)
        ttk.Label(compose, text="Priority").grid(row=0, column=2, sticky="w")
        self.priority = tk.StringVar(value="Statement")
        ttk.Combobox(compose, textvariable=self.priority, state="readonly", values=[p.name.title() for p in AlertPriority], width=18).grid(row=0, column=3, sticky="ew", padx=6)
        ttk.Label(compose, text="Message Text").grid(row=1, column=0, sticky="nw", pady=(8, 0))
        self.message_text = tk.Text(compose, height=7, wrap="word"); self.message_text.grid(row=1, column=1, columnspan=3, sticky="nsew", padx=6, pady=(8, 0))
        compose.columnconfigure(1, weight=1); compose.columnconfigure(3, weight=1)
        ttk.Button(compose, text="Add to Local Test Queue", command=self._enqueue).grid(row=2, column=1, sticky="w", pady=8)
        controls = ttk.Frame(right); controls.pack(fill="x", pady=8)
        ttk.Button(controls, text="START TEST LOOP", command=self._start).pack(side="left", padx=(0, 6))
        ttk.Button(controls, text="STOP LOOP", command=self.queue.stop).pack(side="left", padx=6)
        ttk.Button(controls, text="Refresh Queue", command=self._refresh).pack(side="left", padx=6)
        frame = ttk.Labelframe(right, text="Broadcast Queue (local preview only)", padding=6); frame.pack(fill="both", expand=True)
        self.queue_view = ttk.Treeview(frame, columns=("priority", "id", "title"), show="headings")
        for col, label, width in (("priority", "Priority", 110), ("id", "Product ID", 150), ("title", "Message", 420)):
            self.queue_view.heading(col, text=label); self.queue_view.column(col, width=width)
        self.queue_view.pack(fill="both", expand=True)
        self.status = tk.StringVar(value="Ready — no RF or public alert transmission is available")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=5).pack(fill="x", side="bottom")

    def _enqueue(self) -> None:
        try:
            text = self.message_text.get("1.0", "end").strip()
            priority = AlertPriority[self.priority.get().upper()]
            product = WeatherProduct(self.product_id.get().strip(), self.priority.get(), text, priority=priority,
                                     station_ids=tuple(s.station_id for s in self.stations if s.enabled), test_only=True)
            self.queue.enqueue(product)
        except (KeyError, ValueError) as exc:
            messagebox.showerror("Cannot queue product", str(exc)); return
        self._refresh(); self.status.set("Product queued for local test preview")

    def _preview_product(self, product: WeatherProduct) -> None:
        self.after(0, lambda: self.status.set(f"LOCAL PREVIEW: {product.product_id} — {product.title}"))

    def _start(self) -> None:
        self.queue.start(); self.status.set("Local test queue running — no transmitter connected")

    def _refresh(self) -> None:
        for item in self.queue_view.get_children(): self.queue_view.delete(item)
        for product in self.queue.snapshot():
            self.queue_view.insert("", "end", values=(product.priority.name, product.product_id, product.title))

    def _close(self) -> None:
        self.queue.stop(); self.destroy()

def main() -> None:
    TextWorkstation().mainloop()

if __name__ == "__main__":
    main()
