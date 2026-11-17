"""Tkinter theme and small widgets shared by every LOTWPS window."""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk

# ---------------------------------------------------------------------------
# palette
# ---------------------------------------------------------------------------
BG = "#0a0f16"
PANEL = "#111a24"
PANEL_ALT = "#16222f"
FIELD = "#0d1620"
BORDER = "#26384b"
TEXT = "#dbe7f3"
MUTED = "#8ba3bb"
ACCENT = "#2f81f7"
ACCENT_DARK = "#1f5fbf"
OK = "#39d98a"
WARN = "#f4b23f"
DANGER = "#e5484d"
PURPLE = "#a371f7"
MONO = "Consolas"
UI_FONT = "Segoe UI"

DBZ_COLORS = [
    (5, "#1b4f3a"), (15, "#1f7a4c"), (25, "#37b34a"), (35, "#8fd14f"),
    (45, "#f2e34c"), (55, "#f4a13f"), (65, "#e5484d"), (75, "#c026d3"),
]


def dbz_color(dbz: int) -> str:
    color = DBZ_COLORS[0][1]
    for threshold, hex_color in DBZ_COLORS:
        if dbz >= threshold:
            color = hex_color
    return color


def apply_theme(root: tk.Misc) -> ttk.Style:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass

    root.option_add("*Font", (UI_FONT, 9))
    root.option_add("*TCombobox*Listbox.font", (UI_FONT, 9))
    root.option_add("*TCombobox*Listbox.background", FIELD)
    root.option_add("*TCombobox*Listbox.foreground", TEXT)
    root.option_add("*TCombobox*Listbox.selectBackground", ACCENT)

    style.configure(".", background=BG, foreground=TEXT, fieldbackground=FIELD,
                    bordercolor=BORDER, focuscolor=ACCENT, font=(UI_FONT, 9))
    style.configure("TFrame", background=BG)
    style.configure("Panel.TFrame", background=PANEL)
    style.configure("Alt.TFrame", background=PANEL_ALT)
    style.configure("TLabel", background=BG, foreground=TEXT)
    style.configure("Panel.TLabel", background=PANEL, foreground=TEXT)
    style.configure("Muted.TLabel", background=PANEL, foreground=MUTED)
    style.configure("Header.TLabel", background=PANEL, foreground=TEXT,
                    font=(UI_FONT, 10, "bold"))
    style.configure("Title.TLabel", background=PANEL, foreground=ACCENT,
                    font=(UI_FONT, 12, "bold"))
    style.configure("Status.TLabel", background=PANEL_ALT, foreground=MUTED)
    style.configure("Value.TLabel", background=PANEL, foreground=OK,
                    font=(MONO, 9))
    style.configure("TButton", background=PANEL_ALT, foreground=TEXT,
                    bordercolor=BORDER, padding=(8, 3), relief="flat")
    style.map("TButton",
              background=[("active", "#22354a"), ("pressed", ACCENT_DARK)],
              foreground=[("disabled", "#5b6f83")])
    style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff",
                    padding=(10, 4), font=(UI_FONT, 9, "bold"))
    style.map("Accent.TButton", background=[("active", "#4b93ff")])
    style.configure("Danger.TButton", background="#7d1f22", foreground="#ffe6e6",
                    padding=(10, 4), font=(UI_FONT, 9, "bold"))
    style.map("Danger.TButton", background=[("active", DANGER)])
    style.configure("Toolbar.TButton", background="#1b2836", foreground=TEXT,
                    padding=(6, 2))
    style.configure("TCheckbutton", background=PANEL, foreground=TEXT)
    style.map("TCheckbutton", background=[("active", PANEL)])
    style.configure("TRadiobutton", background=PANEL, foreground=TEXT)
    style.map("TRadiobutton", background=[("active", PANEL)])
    style.configure("TLabelframe", background=PANEL, foreground=MUTED,
                    bordercolor=BORDER, relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=PANEL, foreground=ACCENT,
                    font=(UI_FONT, 9, "bold"))
    style.configure("TNotebook", background=BG, bordercolor=BORDER, tabmargins=(2, 2, 2, 0))
    style.configure("TNotebook.Tab", background=PANEL_ALT, foreground=MUTED,
                    padding=(12, 5), bordercolor=BORDER)
    style.map("TNotebook.Tab",
              background=[("selected", PANEL)],
              foreground=[("selected", TEXT)])
    style.configure("TEntry", fieldbackground=FIELD, foreground=TEXT,
                    insertcolor=TEXT, bordercolor=BORDER, padding=3)
    style.configure("TCombobox", fieldbackground=FIELD, background=PANEL_ALT,
                    foreground=TEXT, arrowcolor=MUTED, bordercolor=BORDER, padding=2)
    style.map("TCombobox", fieldbackground=[("readonly", FIELD)])
    style.configure("TSpinbox", fieldbackground=FIELD, foreground=TEXT,
                    arrowcolor=MUTED, bordercolor=BORDER)
    style.configure("Treeview", background=FIELD, fieldbackground=FIELD,
                    foreground=TEXT, bordercolor=BORDER, rowheight=20)
    style.configure("Treeview.Heading", background=PANEL_ALT, foreground=MUTED,
                    font=(UI_FONT, 8, "bold"), relief="flat")
    style.map("Treeview", background=[("selected", ACCENT_DARK)],
              foreground=[("selected", "#ffffff")])
    style.configure("TScrollbar", background=PANEL_ALT, troughcolor=BG,
                    arrowcolor=MUTED, bordercolor=BG)
    style.configure("TLabelframe", bordercolor=BORDER)
    style.configure("TProgressbar", background=ACCENT, troughcolor=FIELD,
                    bordercolor=BORDER, lightcolor=ACCENT, darkcolor=ACCENT)
    return style


def section(parent: tk.Misc, title: str, padding: int = 8) -> ttk.LabelFrame:
    frame = ttk.LabelFrame(parent, text=f" {title} ", padding=padding)
    return frame


def text_widget(parent: tk.Misc, height: int = 10, wrap: str = "word",
                mono: bool = True, editable: bool = True) -> tk.Text:
    frame = ttk.Frame(parent)
    text = tk.Text(
        frame, height=height, wrap=wrap, undo=True, maxundo=-1,
        background=FIELD, foreground=TEXT, insertbackground=TEXT,
        selectbackground=ACCENT_DARK, selectforeground="#ffffff",
        relief="flat", highlightthickness=1, highlightbackground=BORDER,
        highlightcolor=ACCENT, font=(MONO, 10) if mono else (UI_FONT, 9),
        padx=8, pady=6, spacing1=1, spacing3=1,
    )
    scroll = ttk.Scrollbar(frame, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    text.grid(row=0, column=0, sticky="nsew")
    scroll.grid(row=0, column=1, sticky="ns")
    frame.rowconfigure(0, weight=1)
    frame.columnconfigure(0, weight=1)
    text.frame = frame  # type: ignore[attr-defined]
    if not editable:
        text.configure(state="disabled")
    return text


def scrolled_text(parent: tk.Misc, height: int = 10, mono: bool = True) -> tk.Text:
    """Plain Text packed into the caller (no internal frame)."""
    text = tk.Text(
        parent, height=height, wrap="word", undo=True,
        background=FIELD, foreground=TEXT, insertbackground=TEXT,
        selectbackground=ACCENT_DARK, selectforeground="#ffffff",
        relief="flat", highlightthickness=1, highlightbackground=BORDER,
        highlightcolor=ACCENT, font=(MONO, 10) if mono else (UI_FONT, 9),
        padx=8, pady=6,
    )
    scroll = ttk.Scrollbar(parent, orient="vertical", command=text.yview)
    text.configure(yscrollcommand=scroll.set)
    text.pack(side="left", fill="both", expand=True)
    scroll.pack(side="right", fill="y")
    return text


def tree(parent: tk.Misc, columns: list[tuple[str, str, int]], height: int = 8,
         show: str = "headings") -> ttk.Treeview:
    ids = [c[0] for c in columns]
    view = ttk.Treeview(parent, columns=ids, show=show, height=height,
                        selectmode="browse")
    for key, heading, width in columns:
        view.heading(key, text=heading)
        view.column(key, width=width, anchor="w", stretch=True)
    return view


def center(win: tk.Misc, width: int, height: int, parent: tk.Misc | None = None) -> None:
    win.update_idletasks()
    if parent is not None:
        try:
            px, py = parent.winfo_rootx(), parent.winfo_rooty()
            pw, ph = parent.winfo_width(), parent.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
        except tk.TclError:
            x, y = 80, 60
    else:
        sw, sh = win.winfo_screenwidth(), win.winfo_screenheight()
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 2 - 20)
    win.geometry(f"{width}x{height}+{x}+{y}")


class StatusBar(ttk.Frame):
    """Bottom status strip with left/centre/right slots."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent, style="Alt.TFrame")
        self.left = tk.StringVar(value="Ready")
        self.middle = tk.StringVar(value="")
        self.right = tk.StringVar(value="")
        ttk.Label(self, textvariable=self.left, style="Status.TLabel").pack(
            side="left", padx=8, pady=3
        )
        ttk.Label(self, textvariable=self.right, style="Status.TLabel").pack(
            side="right", padx=8, pady=3
        )
        ttk.Label(self, textvariable=self.middle, style="Status.TLabel").pack(
            side="right", padx=8, pady=3
        )


class Led(tk.Canvas):
    def __init__(self, parent: tk.Misc, color: str = OK, size: int = 12, text: str = ""):
        super().__init__(parent, width=size, height=size, highlightthickness=0,
                         background=PANEL)
        self._dot = self.create_oval(2, 2, size - 1, size - 1, fill=color, outline="")
        self._label = None
        if text:
            self._label = self.create_text(size + 6, size / 2, text=text, anchor="w",
                                           fill=TEXT, font=(UI_FONT, 9))

    def set_color(self, color: str, text: str | None = None) -> None:
        self.itemconfigure(self._dot, fill=color)
        if text is not None and self._label:
            self.itemconfigure(self._label, text=text)


class Ticker(tk.Canvas):
    """Scrolling NWR style text ticker."""

    def __init__(self, parent: tk.Misc, height: int = 26, speed: int = 2):
        super().__init__(parent, height=height, background="#05090d",
                         highlightthickness=1, highlightbackground=BORDER)
        self.speed = speed
        self._text = ""
        self._x = 0.0
        self._job = None
        self._item = self.create_text(0, height // 2, anchor="w", text="",
                                      fill=WARN, font=(MONO, 11, "bold"))
        self.bind("<Configure>", lambda _e: self._restart())

    def set_text(self, text: str) -> None:
        self._text = text.upper()
        self._restart()

    def _restart(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None
        self.itemconfigure(self._item, text=self._text)
        self._x = float(self.winfo_width() or 600)
        self.coords(self._item, self._x, (self.winfo_height() or 26) // 2)
        self._tick()

    def _tick(self) -> None:
        width = self.winfo_width() or 600
        self._x -= self.speed
        try:
            bbox = self.bbox(self._item)
        except tk.TclError:
            bbox = None
        if bbox and bbox[2] < 0:
            self._x = width
        self.coords(self._item, self._x, (self.winfo_height() or 26) // 2)
        self._job = self.after(45, self._tick)

    def stop(self) -> None:
        if self._job:
            self.after_cancel(self._job)
            self._job = None


class ScrollableFrame(ttk.Frame):
    def __init__(self, parent: tk.Misc, **kwargs):
        super().__init__(parent, **kwargs)
        canvas = tk.Canvas(self, background=BG, highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        self.inner = ttk.Frame(canvas)
        self.inner.bind(
            "<Configure>", lambda _e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        window = canvas.create_window((0, 0), window=self.inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(window, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self._canvas = canvas

    def bind_wheel(self) -> None:
        self._canvas.bind_all(
            "<MouseWheel>",
            lambda e: self._canvas.yview_scroll(int(-e.delta / 120), "units"),
        )


def kv_row(parent: tk.Misc, row: int, label: str, value: str, style: str = "Panel.TLabel") -> ttk.Label:
    ttk.Label(parent, text=label, style="Muted.TLabel").grid(
        row=row, column=0, sticky="w", padx=(0, 10), pady=2
    )
    val = ttk.Label(parent, text=value, style=style)
    val.grid(row=row, column=1, sticky="w", pady=2)
    return val


def tagged_log(parent: tk.Misc, height: int = 8) -> tk.Text:
    widget = scrolled_text(parent, height=height)
    widget.tag_configure("ok", foreground=OK)
    widget.tag_configure("warn", foreground=WARN)
    widget.tag_configure("err", foreground=DANGER)
    widget.tag_configure("accent", foreground=ACCENT)
    widget.tag_configure("muted", foreground=MUTED)
    return widget
