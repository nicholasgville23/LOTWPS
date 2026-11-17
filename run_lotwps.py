"""LOTWPS launcher.

Run with no arguments for the application launcher, or name one of the apps:

    python run_lotwps.py radio     # NWR-1 NOAA Weather Radio console
    python run_lotwps.py bmh       # BMH Network
    python run_lotwps.py station   # WXJ75 station controller
    python run_lotwps.py tw        # KLOT LOTIEM text workstation
    python run_lotwps.py awips     # CAVE-LOT D2D client
    python run_lotwps.py lotiem    # LOTIEM TCP daemon (foreground)
"""

from __future__ import annotations

import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

ROOT = Path(__file__).resolve().parent
APPS = ROOT / "apps"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(APPS))

from lotwps import appkit, tz, ui
from lotwps.config import settings

APP_ENTRIES = {
    "radio": (APPS / "nwr_radio.py", "NWR-1 NOAA Weather Radio", []),
    "bmh": (APPS / "bmh_network.py", "BMH Network", []),
    "station": (APPS / "bmh_station.py", "WXJ75 Station Controller", []),
    "tw": (APPS / "lotwps_tw.py", "KLOT LOTIEM Text Workstation", []),
    "awips": (APPS / "lotwps_awips.py", "CAVE-LOT D2D / AWIPS II", []),
}

DESCRIPTIONS = {
    "radio": "Receiver face, START/STOP TX, EAS details channel, SAME alerts",
    "bmh": "Global network controls, TRANSMIT, active transmitters, dispatch",
    "station": "WXJ75 tabs: weather message, TX control, cycles, queue, alerts",
    "tw": "AWIPS header, segments, WarnGen polygon, sent alerts, LOTIEM send",
    "awips": "Radar display, alert polygons, WarnGen, AWIPS II Text 1-5",
}


def _python() -> str:
    candidate = Path(sys.executable).with_name("pythonw.exe")
    return str(candidate) if candidate.exists() else sys.executable


def launch(key: str, station_id: str | None = None) -> subprocess.Popen | None:
    entry = APP_ENTRIES.get(key)
    if not entry:
        print(f"unknown app: {key}")
        return None
    script, _name, extra = entry
    command = [_python(), str(script), *extra]
    if key == "station" and station_id:
        command.append(station_id)
    creation = 0
    if os.name == "nt":
        creation = 0x00000008  # DETACHED_PROCESS
    return subprocess.Popen(command, cwd=str(ROOT), creationflags=creation)


def launch_lotiem() -> subprocess.Popen:
    if os.name == "nt":
        return subprocess.Popen(
            [str(Path(sys.executable)), "-m", "lotiem.server"],
            cwd=str(ROOT),
            creationflags=0x00000010,  # CREATE_NEW_CONSOLE
        )
    return subprocess.Popen([sys.executable, "-m", "lotiem.server"], cwd=str(ROOT))


class Launcher:
    def __init__(self) -> None:
        self.root = appkit.boot(
            "LOTWPS  |  KLOT Weather Processing System", (1080, 720), (940, 640)
        )
        self.settings = settings()
        self.lotiem_proc: subprocess.Popen | None = None
        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self.root.destroy)
        self._tick()

    def _build(self) -> None:
        header = ttk.Frame(self.root, style="Panel.TFrame", padding=(14, 10))
        header.pack(fill="x")
        ttk.Label(header, text="LOTWPS", style="Title.TLabel").pack(side="left")
        ttk.Label(
            header,
            text="  LOT Weather Processing System  |  KLOT  |  Chicago/Romeoville",
            style="Muted.TLabel",
        ).pack(side="left")
        self.clock = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock, style="Header.TLabel").pack(side="right")

        banner = tk.Frame(self.root, background="#05090d", highlightthickness=1,
                          highlightbackground=ui.BORDER)
        banner.pack(fill="x", padx=10, pady=(8, 0))
        tk.Label(
            banner,
            text="BMH-NOAA-Weather-Radio-LOTIEM-and-LOTWPS",
            background="#05090d", foreground=ui.ACCENT,
            font=(ui.MONO, 12, "bold"), anchor="w",
        ).pack(fill="x", padx=12, pady=(8, 0))
        tk.Label(
            banner,
            text="NOAA Weather Radio WXJ75 162.400  |  KBB58 162.425  |  "
                 "LOTIEM 192.168.10.144:6000  |  VoiceText Paul + David + Zira",
            background="#05090d", foreground=ui.MUTED,
            font=(ui.MONO, 8), anchor="w",
        ).pack(fill="x", padx=12, pady=(0, 8))

        body = ttk.Frame(self.root, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.columnconfigure(2, weight=1)

        entries = [
            ("radio", "NOAA WEATHER RADIO", ui.ACCENT),
            ("bmh", "BMH NETWORK", ui.OK),
            ("station", "WXJ75 STATION CONTROLLER", ui.WARN),
            ("tw", "KLOT LOTIEM TEXT WORKSTATION", ui.PURPLE),
            ("awips", "CAVE-LOT D2D  /  AWIPS II", "#64d2ff"),
            ("lotiem", "LOTIEM DISTRIBUTION HUB", "#ffd60a"),
        ]
        for idx, (key, title, color) in enumerate(entries):
            frame = ttk.LabelFrame(body, text=f" {title} ", padding=8)
            frame.grid(row=idx // 3, column=idx % 3, sticky="nsew", padx=4, pady=4)
            frame.columnconfigure(0, weight=1)
            tk.Label(
                frame, text=title.split()[0], background=ui.PANEL,
                foreground=color, font=(ui.MONO, 16, "bold"),
            ).grid(row=0, column=0, sticky="w")
            ttk.Label(
                frame,
                text=DESCRIPTIONS.get(key, "Start the TCP daemon and route products"),
                style="Muted.TLabel", wraplength=280, justify="left",
            ).grid(row=1, column=0, sticky="w", pady=(2, 8))
            if key == "lotiem":
                ttk.Button(
                    frame, text="START LOTIEM DAEMON", style="Accent.TButton",
                    command=self._start_lotiem,
                ).grid(row=2, column=0, sticky="ew")
            else:
                ttk.Button(
                    frame, text="LAUNCH", style="Accent.TButton",
                    command=lambda k=key: self._launch(k),
                ).grid(row=2, column=0, sticky="ew")

        footer = ttk.Frame(self.root, style="Panel.TFrame", padding=(10, 8))
        footer.pack(fill="x")
        ttk.Button(footer, text="LAUNCH EVERYTHING", command=self._launch_all).pack(
            side="left"
        )
        ttk.Button(footer, text="OPEN CONFIG", command=self._open_config).pack(
            side="left", padx=4
        )
        ttk.Button(footer, text="VOICE REPORT", command=self._voice_report).pack(
            side="left", padx=4
        )
        ttk.Button(footer, text="QUIT", style="Danger.TButton",
                   command=self.root.destroy).pack(side="right")

        self.status = ui.StatusBar(self.root)
        self.status.pack(fill="x", side="bottom")
        self.status.left.set("Select an application")
        self.status.middle.set("Python 3.12  |  Tk 8.6")
        self.status.right.set(
            f"{self.settings.get('app.build')}  |  {self.settings.get('app.version')}"
        )

    # ------------------------------------------------------------- actions
    def _launch(self, key: str, station_id: str | None = None) -> None:
        try:
            launch(key, station_id=station_id)
            self.status.left.set(f"launched {APP_ENTRIES[key][1]}")
        except Exception as exc:
            messagebox.showerror("LOTWPS", f"Cannot launch {key}: {exc}", parent=self.root)

    def _launch_all(self) -> None:
        for key in ("radio", "bmh", "station", "tw", "awips"):
            self._launch(key)
        self.status.left.set("launched the full LOTWPS suite")

    def _start_lotiem(self) -> None:
        try:
            if self.lotiem_proc and self.lotiem_proc.poll() is None:
                self.status.left.set("LOTIEM daemon already running")
                return
            self.lotiem_proc = launch_lotiem()
            self.status.left.set("LOTIEM daemon starting on 127.0.0.1:6000")
        except Exception as exc:
            messagebox.showerror("LOTIEM", f"Cannot start daemon: {exc}", parent=self.root)

    def _open_config(self) -> None:
        path = ROOT / "config" / "settings.json"
        try:
            os.startfile(str(path))
        except Exception as exc:
            messagebox.showerror("LOTWPS", f"Cannot open settings: {exc}", parent=self.root)

    def _voice_report(self) -> None:
        from lotwps.voices import VoiceEngine, available_voices_report

        engine = VoiceEngine(self.settings)
        lines = [available_voices_report(), "", "Configured engines:"]
        for key, text in engine.describe().items():
            lines.append(f"  {key}: {text}")
        paul = engine.get("paul")
        if hasattr(paul, "asset_path"):
            asset = paul.asset_path("STATION_ID")
            lines.append("")
            lines.append(f"VoiceText Paul static ID asset: {asset}")
        messagebox.showinfo("Voice Report", "\n".join(lines), parent=self.root)

    # -------------------------------------------------------------- timers
    def _tick(self) -> None:
        now, label = tz.central_now()
        self.clock.set(f"{now:%H:%M:%S} {label}  {now:%a %b} {now.day}")
        if self.lotiem_proc is not None:
            state = "running" if self.lotiem_proc.poll() is None else "stopped"
            self.status.middle.set(f"LOTIEM daemon {state}  |  Python 3.12  |  Tk 8.6")
        self.root.after(1000, self._tick)


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if args:
        key = args[0].lower()
        if key == "lotiem":
            from lotiem.server import LOTIEMServer

            LOTIEMServer().serve_forever()
            return
        if key == "all":
            for name in ("radio", "bmh", "station", "tw", "awips"):
                launch(name)
            return
        station_id = args[1] if len(args) > 1 else None
        if key not in APP_ENTRIES:
            print(__doc__)
            return
        launch(key, station_id=station_id)
        return
    Launcher().root.mainloop()


if __name__ == "__main__":
    main()
