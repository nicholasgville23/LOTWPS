"""Shared bootstrap for the Tkinter applications."""

from __future__ import annotations

import ctypes
import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox, ttk

from . import ui

APP_DIR = Path(__file__).resolve().parent.parent


def enable_dpi() -> None:
    if os.name != "nt":
        return
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def boot(title: str, size: tuple[int, int], minsize: tuple[int, int] | None = None) -> tk.Tk:
    enable_dpi()
    root = tk.Tk()
    root.title(title)
    root.configure(background=ui.BG)
    ui.apply_theme(root)
    ui.center(root, *size)
    root.minsize(*(minsize or (820, 520)))
    root.option_add("*tearOff", False)
    return root


def icon_text(root: tk.Tk, text: str = "NWR") -> None:
    """No .ico in the repo - draw a tiny label instead of failing."""
    root.iconname(text)


def report_error(parent: tk.Misc, title: str, exc: BaseException) -> None:
    messagebox.showerror(title, f"{type(exc).__name__}: {exc}", parent=parent)


def tooltip(widget: tk.Misc, text: str) -> None:
    """Lightweight hover tooltip."""
    tip = {"win": None}

    def enter(_event):
        if tip["win"]:
            return
        x = widget.winfo_rootx() + 12
        y = widget.winfo_rooty() + widget.winfo_height() + 6
        win = tk.Toplevel(widget)
        win.wm_overrideredirect(True)
        win.wm_geometry(f"+{x}+{y}")
        tk.Label(
            win, text=text, justify="left", background="#1b2a3a",
            foreground=ui.TEXT, relief="solid", borderwidth=1,
            font=(ui.UI_FONT, 8), padx=6, pady=3,
        ).pack()
        tip["win"] = win

    def leave(_event):
        if tip["win"]:
            tip["win"].destroy()
            tip["win"] = None

    widget.bind("<Enter>", enter, add="+")
    widget.bind("<Leave>", leave, add="+")


def labeled_entry(parent: tk.Misc, label: str, variable: tk.StringVar, width: int = 18) -> ttk.Entry:
    frame = ttk.Frame(parent, style="Panel.TFrame")
    ttk.Label(frame, text=label, style="Muted.TLabel").pack(side="left", padx=(0, 6))
    entry = ttk.Entry(frame, textvariable=variable, width=width)
    entry.pack(side="left")
    return entry


def hline(parent: tk.Misc) -> None:
    tk.Frame(parent, height=1, background=ui.BORDER).pack(fill="x", pady=6)


def log_writer(text_widget: tk.Text):
    def write(message: str, tag: str = "") -> None:
        stamp = __import__("lotwps.tz", fromlist=["central_now"]).central_now()[0].strftime("%H:%M:%S")
        text_widget.configure(state="normal")
        text_widget.insert("end", f"{stamp}  {message}\n", tag)
        text_widget.see("end")
        text_widget.configure(state="disabled")

    return write


def confirm(parent: tk.Misc, title: str, message: str) -> bool:
    return bool(messagebox.askyesno(title, message, parent=parent))


def app_main(cls) -> None:
    app = cls()
    app.mainloop()


def ensure_path() -> None:
    root = str(APP_DIR)
    if root not in sys.path:
        sys.path.insert(0, root)
