"""KLOT LOTIEM TEXT WORKSTATION.

The forecaster's text desk for WFO LOT: AWIPS header block, segment editor
(right-click segment tools), WarnGen / WatchGen polygon tools, hazard segment
builder, unified active-alert board, sent-alert editor, and dispatch to BMH,
Email, IEMBOT and Websites & Outlets through LOTIEM.
"""

from __future__ import annotations

import sys
import textwrap
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
    same,
    tz,
    ui,
    zones,
)

CATEGORY_WMO = {
    "Weather": "WWUS83",
    "EAS": "WWUS53",
    "Hydrology": "WGUS53",
    "Marine": "FZUS53",
    "Climate": "CLIUS53",
    "Aviation": "FXUS63",
}

ROUTE_LABELS = {
    "BMH": "BMH",
    "EMAIL": "Email",
    "IEMBOT": "IEMBOT",
    "WEBSITES": "Websites & Outlets",
}


# ---------------------------------------------------------------------------
# segment dialogs
# ---------------------------------------------------------------------------

class SegmentDialog(tk.Toplevel):
    KINDS = ["Headline", "Discussion", "Hazard", "Precautionary", "Location", "Custom"]

    def __init__(self, parent, on_apply, title="Add Segment", kind="Custom", text="") -> None:
        super().__init__(parent)
        self.on_apply = on_apply
        self.title(title)
        self.configure(background=ui.BG)
        ui.center(self, 680, 460, parent)
        self._build(kind, text)
        self.transient(parent)
        self.grab_set()

    def _build(self, kind: str, text: str) -> None:
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)

        ttk.Label(body, text="SEGMENT KIND", style="Muted.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.kind = tk.StringVar(value=kind)
        ttk.Combobox(body, textvariable=self.kind, state="readonly", values=self.KINDS).grid(
            row=0, column=1, sticky="ew", padx=(6, 0)
        )
        ttk.Label(body, text="SEGMENT TEXT", style="Muted.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", pady=(8, 2)
        )
        holder = ttk.Frame(body)
        holder.grid(row=2, column=0, columnspan=2, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.text = ui.text_widget(holder, height=12)
        self.text.frame.grid(row=0, column=0, sticky="nsew")
        self.text.insert("1.0", text or "$$")

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="APPLY", style="Accent.TButton", command=self._apply).pack(
            side="left"
        )
        ttk.Button(buttons, text="CANCEL", command=self.destroy).pack(side="right")

    def _apply(self) -> None:
        text = self.text.get("1.0", "end").strip()
        if text:
            self.on_apply(text, self.kind.get())
        self.destroy()


class HazardSegmentBuilder(tk.Toplevel):
    """Build a HAZARD / SOURCE / IMPACT / ACTIONS block."""

    def __init__(self, parent, on_insert) -> None:
        super().__init__(parent)
        self.on_insert = on_insert
        self.title("Add Hazard Segment  |  KLOT")
        self.configure(background=ui.BG)
        ui.center(self, 800, 700, parent)
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(6, weight=1)

        self.hazard = tk.StringVar(value="Severe Thunderstorm Warning")
        ttk.Label(body, text="HAZARD", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        box = ttk.Combobox(
            body, textvariable=self.hazard, state="readonly",
            values=[name for name in same.EVENT_CODES],
        )
        box.grid(row=0, column=1, sticky="ew", padx=(6, 0), pady=2)
        box.bind("<<ComboboxSelected>>", lambda _e: self._prefill())

        self.source = tk.StringVar(value="Radar indicated.")
        ttk.Label(body, text="SOURCE", style="Muted.TLabel").grid(row=1, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.source).grid(
            row=1, column=1, sticky="ew", padx=(6, 0), pady=2
        )

        self.locations = tk.StringVar(value="Valparaiso, Portage, and Chesterton")
        ttk.Label(body, text="LOCATIONS", style="Muted.TLabel").grid(row=2, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.locations).grid(
            row=2, column=1, sticky="ew", padx=(6, 0), pady=2
        )

        self.target = tk.StringVar(value="new")
        ttk.Label(body, text="INSERT AS", style="Muted.TLabel").grid(row=3, column=0, sticky="w")
        target_row = ttk.Frame(body)
        target_row.grid(row=3, column=1, sticky="w", padx=(6, 0))
        ttk.Radiobutton(target_row, text="New hazard segment", value="new",
                        variable=self.target, command=self._refresh).pack(side="left")
        ttk.Radiobutton(target_row, text="Add hazard to existing", value="existing",
                        variable=self.target, command=self._refresh).pack(side="left", padx=10)

        ttk.Label(body, text="DETAILS (IMPACT)", style="Muted.TLabel").grid(
            row=4, column=0, sticky="nw", pady=(6, 2)
        )
        self.impact = tk.Text(
            body, height=4, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 9), padx=8, pady=6,
        )
        self.impact.grid(row=5, column=0, columnspan=2, sticky="nsew")
        self.impact.insert(
            "1.0",
            "Hail damage to vehicles is expected. Expect wind damage to roofs, siding, "
            "and trees.",
        )

        ttk.Label(body, text="CALL TO ACTION", style="Muted.TLabel").grid(
            row=6, column=0, sticky="nw", pady=(6, 2)
        )
        self.actions = tk.Text(
            body, height=4, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 9), padx=8, pady=6,
        )
        self.actions.grid(row=7, column=0, columnspan=2, sticky="nsew")
        self.actions.insert(
            "1.0",
            "For your protection move to an interior room on the lowest floor of a "
            "building. Prepare for possible power outages.",
        )
        body.rowconfigure(7, weight=1)

        ttk.Label(body, text="PREVIEW", style="Muted.TLabel").grid(
            row=8, column=0, columnspan=2, sticky="w", pady=(8, 2)
        )
        self.preview = tk.Text(
            body, height=7, wrap="word", background="#050c11", foreground=ui.TEXT,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 8), padx=6, pady=4, state="disabled",
        )
        self.preview.grid(row=9, column=0, columnspan=2, sticky="nsew")
        body.rowconfigure(9, weight=1)

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        buttons.pack(fill="x")
        ttk.Button(buttons, text="INSERT INTO MESSAGE", style="Accent.TButton",
                   command=self._insert).pack(side="left")
        ttk.Button(buttons, text="REFRESH PREVIEW", command=self._refresh).pack(
            side="left", padx=6
        )
        ttk.Button(buttons, text="CANCEL", command=self.destroy).pack(side="right")

        for widget in (self.impact, self.actions):
            widget.bind("<KeyRelease>", lambda _e: self._refresh())
        self._refresh()

    def _prefill(self) -> None:
        name = self.hazard.get()
        code = same.EVENT_CODES.get(name, "")
        details = awips.WARNING_DETAILS.get(code)
        if details:
            self.impact.delete("1.0", "end")
            self.impact.insert("1.0", details["impact"])
            self.actions.delete("1.0", "end")
            self.actions.insert("1.0", details["actions"])
            self.source.set(details["source"])
        self._refresh()

    def build_text(self) -> str:
        name = self.hazard.get()
        parts = [
            f"{name.upper()}",
            "",
            f"HAZARD...{name.replace(' Warning', '').replace(' Watch', '')}.",
            f"SOURCE...{self.source.get().strip() or 'Radar indicated.'}",
            f"IMPACT...{self.impact.get('1.0', 'end').strip()}",
            "",
            "* Locations impacted include...",
            f"  {self.locations.get().strip()}.",
            "",
            "PRECAUTIONARY/PREPAREDNESS ACTIONS...",
            "",
            self.actions.get("1.0", "end").strip(),
        ]
        return "\n".join(parts).strip()

    def _refresh(self) -> None:
        self.preview.configure(state="normal")
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", self.build_text())
        self.preview.configure(state="disabled")

    def _insert(self) -> None:
        self.on_insert(self.build_text(), self.target.get())
        self.destroy()


# ---------------------------------------------------------------------------
# sent alerts
# ---------------------------------------------------------------------------

class SentAlertsWindow(tk.Toplevel):
    def __init__(self, parent, store, on_change=None) -> None:
        super().__init__(parent)
        self.store = store
        self.on_change = on_change
        self.title("View / Edit Sent Alerts  |  KLOT LOTIEM")
        self.configure(background=ui.BG)
        ui.center(self, 1080, 660, parent)
        self._build()
        self.transient(parent)

    def _build(self) -> None:
        head = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        head.pack(fill="x")
        ttk.Label(head, text="SENT ALERTS", style="Title.TLabel").pack(side="left")
        ttk.Label(head, text="  KLOT / LOTWPS", style="Muted.TLabel").pack(side="left")

        body = ttk.Frame(self, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=3)
        body.columnconfigure(1, weight=2)
        body.rowconfigure(0, weight=1)

        tree_frame = ttk.Frame(body)
        tree_frame.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        tree_frame.rowconfigure(0, weight=1)
        tree_frame.columnconfigure(0, weight=1)
        self.tree = ui.tree(
            tree_frame,
            [("id", "Alert ID", 180), ("event", "Event", 200), ("status", "Act", 50),
             ("issued", "Issued", 80), ("expires", "Expires", 80)],
            height=16,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        self.tree.bind("<<TreeviewSelect>>", lambda _e: self._show())

        detail = ttk.Frame(body)
        detail.grid(row=0, column=1, sticky="nsew")
        detail.rowconfigure(1, weight=1)
        detail.columnconfigure(0, weight=1)
        self.detail_title = tk.StringVar(value="Select an alert")
        ttk.Label(detail, textvariable=self.detail_title, style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        holder = ttk.Frame(detail)
        holder.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.detail = ui.scrolled_text(holder, height=18)
        self.detail.configure(state="disabled")

        buttons = ttk.Frame(detail)
        buttons.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(buttons, text="EDIT", style="Accent.TButton",
                   command=self._edit).pack(side="left")
        ttk.Button(buttons, text="RETONE", command=self._retone).pack(side="left", padx=4)
        ttk.Button(buttons, text="CANCEL ALERT", command=self._cancel).pack(side="left")
        ttk.Button(buttons, text="REFRESH", command=self._refresh).pack(side="right")

        foot = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        foot.pack(fill="x")
        ttk.Button(foot, text="CLOSE", command=self.destroy).pack(side="right")
        self.summary = tk.StringVar(value="")
        ttk.Label(foot, textvariable=self.summary, style="Muted.TLabel").pack(side="left")

        self._refresh()

    def _refresh(self) -> None:
        self.tree.delete(*self.tree.get_children())
        for alert in self.store.all():
            self.tree.insert(
                "", "end", iid=alert.alert_id,
                values=(alert.alert_id, alert.event, alert.status,
                        f"{alert.issued:%m/%d %H:%M}Z", f"{alert.expires:%m/%d %H:%M}Z"),
            )
        self.summary.set(self.store.summary())

    def _selected(self):
        selection = self.tree.selection()
        return self.store.by_id(selection[0]) if selection else None

    def _show(self) -> None:
        alert = self._selected()
        if not alert:
            return
        self.detail_title.set(f"{alert.event}  |  {alert.status}  |  {alert.alert_id}")
        text = (
            f"HEADLINE\n{alert.headline}\n\n"
            f"AREA\n{alert.area}\n\n"
            f"ISSUED\n{alert.issued:%Y-%m-%d %H:%M}Z  ({alert.tier})\n\n"
            f"EXPIRES\n{alert.expires:%Y-%m-%d %H:%M}Z  ({alert.minutes_left} min)\n\n"
            f"SAME\n{alert.same_header or alert.ensure_header()}\n\n"
            f"DESCRIPTION\n{alert.description}\n\n"
            f"INSTRUCTION\n{alert.instruction}\n"
        )
        self.detail.configure(state="normal")
        self.detail.delete("1.0", "end")
        self.detail.insert("1.0", text)
        self.detail.configure(state="disabled")

    def _edit(self) -> None:
        alert = self._selected()
        if not alert:
            return
        from alert_editor import edit_alert

        edit_alert(self, alert, on_save=lambda _a: (self._refresh(), self._show(),
                                                   self.on_change and self.on_change()))

    def _retone(self) -> None:
        alert = self._selected()
        if alert:
            self.store.retone(alert.alert_id)
            self._refresh()
            self._show()

    def _cancel(self) -> None:
        alert = self._selected()
        if alert and messagebox.askyesno("Cancel Alert", f"Cancel {alert.alert_id}?",
                                         parent=self):
            self.store.cancel(alert.alert_id)
            self._refresh()
            self._show()
            if self.on_change:
                self.on_change()


# ---------------------------------------------------------------------------
# main workstation
# ---------------------------------------------------------------------------

class TextWorkstation:
    def __init__(self) -> None:
        self.root = appkit.boot(
            "KLOT LOTIEM TEXT WORKSTATION", (1400, 900), (1180, 760)
        )
        self.settings = __import__("lotwps.config", fromlist=["settings"]).settings()
        self.store = alert_mod.store()
        self.bus = bus_mod.Bus("LOTWPS")
        self.editor_mode = False
        self.last_polygon: list[tuple[float, float]] = []
        self.last_alert_id = ""
        self._bus_messages: list[dict] = []

        self._build()
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self._closed = False
        self._tick_job = None
        self._bus_job = None
        self._poll_bus()
        self._tick()
        self.log("KLOT LOTIEM text workstation online - WFO LOT / Chicago")

    # ------------------------------------------------------------------ UI
    def _build(self) -> None:
        self._build_menu()
        root = self.root

        header = ttk.Frame(root, style="Panel.TFrame", padding=(10, 8))
        header.pack(fill="x")
        ttk.Button(
            header, text="WFO LOT", style="Accent.TButton", command=self._wfo_lot
        ).pack(side="left")
        title = ttk.Frame(header, style="Panel.TFrame")
        title.pack(side="left", padx=12)
        ttk.Label(title, text=self.settings.get("text_workstation.title",
                                                "KLOT LOTIEM TEXT WORKSTATION"),
                  style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            title,
            text="Chicago/Romeoville, IL  |  AWIPS II text workstation  |  "
                 "LOTIEM 192.168.10.144:6000",
            style="Muted.TLabel",
        ).pack(anchor="w")
        self.clock_var = tk.StringVar(value="")
        ttk.Label(header, textvariable=self.clock_var, style="Header.TLabel").pack(side="right")
        ttk.Button(header, text="RESTORE UI", command=self._restore_ui).pack(
            side="right", padx=8
        )
        self.editor_button = ttk.Button(
            header, text="ENTER EDITOR MODE", command=self._toggle_editor_mode
        )
        self.editor_button.pack(side="right", padx=4)

        toolbar = ttk.Frame(root, padding=(10, 6, 10, 2))
        toolbar.pack(fill="x")
        ttk.Button(
            toolbar, text="NEW TEXT MESSAGE", style="Accent.TButton",
            command=self._new_message,
        ).pack(side="left", padx=(0, 8))
        for route in ("BMH", "EMAIL", "IEMBOT", "WEBSITES"):
            ttk.Button(
                toolbar, text=f"SEND TO {ROUTE_LABELS[route].upper()}",
                command=lambda r=route: self._dispatch(r),
            ).pack(side="left", padx=2)
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Label(toolbar, text="WRAP", style="Muted.TLabel").pack(side="left")
        self.wrap_var = tk.IntVar(value=int(self.settings.get("text_workstation.wrap", 69)))
        ttk.Spinbox(toolbar, from_=30, to=120, textvariable=self.wrap_var, width=5).pack(
            side="left", padx=3
        )
        ttk.Button(toolbar, text="REWRAP EDITS", command=self._rewrap).pack(side="left")
        ttk.Separator(toolbar, orient="vertical").pack(side="left", fill="y", padx=8)
        ttk.Button(toolbar, text="WARNGEN", command=self._warngen).pack(side="left")
        ttk.Button(toolbar, text="WATCHGEN", command=self._watchgen).pack(side="left", padx=3)
        ttk.Button(toolbar, text="SENT ALERTS", command=self._sent_alerts).pack(side="left")
        ttk.Button(
            toolbar, text="ENTER", style="Accent.TButton", command=self._enter
        ).pack(side="right")

        body = ttk.Frame(root, padding=8)
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=2)
        body.columnconfigure(1, weight=4)
        body.columnconfigure(2, weight=3)
        body.rowconfigure(0, weight=1)

        self._build_header_block(body)
        self._build_editor(body)
        self._build_right(body)

        self.status = ui.StatusBar(root)
        self.status.pack(fill="x", side="bottom")
        self.status.left.set("KLOT  |  LOTIEM  |  text workstation ready")
        self.status.middle.set("WFO LOT  |  Chicago/Romeoville, Illinois")
        self.status.right.set(
            f"{self.settings.get('text_workstation.ip')}:"
            f"{self.settings.get('text_workstation.port')}  |  LOTIEM"
        )

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        message_menu = tk.Menu(menubar, tearoff=False)
        message_menu.add_command(label="New Text Message", command=self._new_message)
        message_menu.add_command(label="Send to BMH", command=lambda: self._dispatch("BMH"))
        message_menu.add_command(label="Email", command=lambda: self._dispatch("EMAIL"))
        message_menu.add_command(label="IEMBOT", command=lambda: self._dispatch("IEMBOT"))
        message_menu.add_command(label="Websites & Outlets",
                                 command=lambda: self._dispatch("WEBSITES"))
        message_menu.add_separator()
        message_menu.add_command(label="Enter / Issue", command=self._enter)
        menubar.add_cascade(label="Message", menu=message_menu)

        tools = tk.Menu(menubar, tearoff=False)
        tools.add_command(label="WarnGen", command=self._warngen)
        tools.add_command(label="WatchGen", command=self._watchgen)
        tools.add_command(label="Add Hazard Segment", command=self._add_hazard_segment)
        tools.add_command(label="View / Edit Sent Alerts", command=self._sent_alerts)
        tools.add_command(label="Restore UI", command=self._restore_ui)
        menubar.add_cascade(label="Tools", menu=tools)

        help_menu = tk.Menu(menubar, tearoff=False)
        help_menu.add_command(label="About LOTWPS", command=self._about)
        menubar.add_cascade(label="Help", menu=help_menu)
        self.root.configure(menu=menubar)

    def _build_header_block(self, parent: ttk.Frame) -> None:
        left = ttk.Frame(parent)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        form = ui.section(left, "AWIPS Header Block")
        form.grid(row=0, column=0, sticky="new", pady=(0, 8))
        form.columnconfigure(1, weight=1)

        self.ttaa_var = tk.StringVar(value="WWUS83")
        self.cccc_var = tk.StringVar(value="KLOT")
        self.bbb_var = tk.StringVar(value="NOR")
        self.bbbver_var = tk.IntVar(value=1)
        self.wsfo_var = tk.StringVar(value="CHI")
        self.category_var = tk.StringVar(value="Weather")
        self.designator_var = tk.StringVar(value="LOT")
        self.addressee_var = tk.StringVar(value="ALL")
        self.product_var = tk.StringVar(value="Special Weather Statement")

        rows = [
            ("TTAAii", ttk.Entry(form, textvariable=self.ttaa_var, width=12)),
            ("CCCC", ttk.Entry(form, textvariable=self.cccc_var, width=12)),
            ("BBB (NOR/A/B)", ttk.Combobox(
                form, textvariable=self.bbb_var, state="readonly", width=8,
                values=awips.BBB_OPTIONS,
            )),
            ("BBB VERSION", ttk.Spinbox(
                form, from_=1, to=9, textvariable=self.bbbver_var, width=6,
            )),
            ("WSFO ID", ttk.Entry(form, textvariable=self.wsfo_var, width=12)),
            ("PRODUCT CATEGORY", ttk.Combobox(
                form, textvariable=self.category_var, state="readonly", width=14,
                values=list(CATEGORY_WMO),
            )),
            ("DESIGNATOR", ttk.Entry(form, textvariable=self.designator_var, width=12)),
            ("ADDRESSEE", ttk.Entry(form, textvariable=self.addressee_var, width=12)),
            ("PRODUCT", ttk.Combobox(
                form, textvariable=self.product_var, state="readonly",
                values=[awips.product(p).name for p in awips.PRODUCT_ORDER],
            )),
        ]
        for idx, (label, widget) in enumerate(rows):
            ttk.Label(form, text=label, style="Muted.TLabel").grid(
                row=idx, column=0, sticky="w", pady=1
            )
            widget.grid(row=idx, column=1, sticky="ew", padx=(6, 0), pady=1)
        self.category_var.trace_add("write", lambda *_a: self._category_changed())

        self.header_preview = tk.Text(
            form, height=8, wrap="none", background="#050c11", foreground=ui.OK,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 8), padx=6, pady=4, state="disabled",
        )
        self.header_preview.grid(row=len(rows), column=0, columnspan=2, sticky="nsew",
                                 pady=(6, 4))
        form.rowconfigure(len(rows), weight=1)
        ttk.Button(
            form, text="ENTER HEADER BLOCK", style="Accent.TButton", command=self._enter_header
        ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="ew")

        polygon = ui.section(left, "KLOT Polygon Tool")
        polygon.grid(row=1, column=0, sticky="nsew")
        polygon.rowconfigure(0, weight=1)
        polygon.columnconfigure(0, weight=1)
        from lotwps import mapview

        self.map = mapview.MapCanvas(
            polygon, height=300, interactive=True, title="KLOT / LOT  POLYGON TOOL",
            on_polygon=self._polygon_done,
        )
        self.map.grid(row=0, column=0, sticky="nsew")
        self.latlon_var = tk.StringVar(value="LAT...LON  --")
        ttk.Label(polygon, textvariable=self.latlon_var, style="Value.TLabel",
                  wraplength=360, justify="left").grid(row=1, column=0, sticky="w",
                                                      pady=(4, 0))
        row = ttk.Frame(polygon)
        row.grid(row=2, column=0, sticky="ew", pady=(4, 0))
        ttk.Button(row, text="USE POLYGON", command=self._use_polygon).pack(side="left")
        ttk.Button(row, text="CLEAR", command=self._clear_polygon).pack(side="left", padx=4)
        ttk.Button(row, text="WARNGEN", command=self._warngen).pack(side="left")

        self._enter_header()

    def _build_editor(self, parent: ttk.Frame) -> None:
        frame = ui.section(parent, "Message Editor")
        frame.grid(row=0, column=1, sticky="nsew", padx=6)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        holder = ttk.Frame(frame)
        holder.grid(row=0, column=0, sticky="nsew")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        self.editor = ui.text_widget(holder, height=26)
        self.editor.frame.grid(row=0, column=0, sticky="nsew")
        self.editor.insert(
            "1.0",
            "The National Weather Service in Chicago has issued a Special Weather "
            "Statement for northwest Indiana.\n\n"
            "At 3:52 PM CDT, a strong thunderstorm was located near Valparaiso, moving "
            "northeast at 30 miles per hour. Wind gusts to 45 miles per hour and small "
            "hail are possible.\n\n"
            "Locations impacted include Valparaiso, Portage, Chesterton, and Hebron.\n\n"
            "PRECAUTIONARY/PREPAREDNESS ACTIONS...\n\n"
            "If outdoors, consider seeking shelter inside a building. Stay tuned to NOAA "
            "Weather Radio for the latest information.",
        )
        self.editor.bind("<Button-3>", self._editor_menu)
        self.editor.bind("<KeyRelease>", lambda _e: self._update_counts())
        self.editor.bind("<Control-a>", self._select_all)

        bottom = ttk.Frame(frame)
        bottom.grid(row=1, column=0, sticky="ew", pady=(6, 0))
        self.count_var = tk.StringVar(value="")
        ttk.Label(bottom, textvariable=self.count_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(bottom, text="CLEAR", command=self._clear_editor).pack(side="right")
        ttk.Button(bottom, text="ENTER", style="Accent.TButton",
                   command=self._enter).pack(side="right", padx=4)
        self._update_counts()

        self.editor_menu = tk.Menu(self.editor, tearoff=False)
        self.editor_menu.add_command(label="Add Segment", command=self._add_segment)
        self.editor_menu.add_command(label="Edit Segment", command=self._edit_segment)
        self.editor_menu.add_command(label="Remove Segment", command=self._remove_segment)
        self.editor_menu.add_command(label="Combine Segment", command=self._combine_segment)
        self.editor_menu.add_separator()
        self.editor_menu.add_command(label="Add Hazard Segment", command=self._add_hazard_segment)
        self.editor_menu.add_command(label="Add Hazard to Existing",
                                     command=self._add_hazard_existing)

    def _build_right(self, parent: ttk.Frame) -> None:
        notebook = ttk.Notebook(parent)
        notebook.grid(row=0, column=2, sticky="nsew", padx=(6, 0))

        warn = ttk.Frame(notebook, padding=8)
        notebook.add(warn, text="WarnGen")
        warn.columnconfigure(0, weight=1)
        ttk.Label(warn, text="WARNGEN TOOLS", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        ttk.Button(
            warn, text="SINGLE STORM POLYGON", style="Accent.TButton",
            command=lambda: self._warngen("Single Storm"),
        ).grid(row=1, column=0, sticky="ew", pady=3)
        ttk.Button(
            warn, text="LINE OF STORMS POLYGON",
            command=lambda: self._warngen("Line of Storms"),
        ).grid(row=2, column=0, sticky="ew", pady=3)
        ttk.Button(warn, text="TORNADO WARNING", command=lambda: self._quick_warn("TOR")).grid(
            row=3, column=0, sticky="ew", pady=3
        )
        ttk.Button(
            warn, text="SEVERE THUNDERSTORM WARNING",
            command=lambda: self._quick_warn("SVR"),
        ).grid(row=4, column=0, sticky="ew", pady=3)
        ttk.Button(warn, text="FLASH FLOOD WARNING", command=lambda: self._quick_warn("FFW")).grid(
            row=5, column=0, sticky="ew", pady=3
        )
        ttk.Button(warn, text="WATCHGEN", command=self._watchgen).grid(
            row=6, column=0, sticky="ew", pady=(8, 3)
        )
        ttk.Label(warn, text="LAST ISSUED POLYGON", style="Muted.TLabel").grid(
            row=7, column=0, sticky="w", pady=(10, 2)
        )
        self.last_poly = tk.Text(
            warn, height=6, wrap="word", background="#050c11", foreground=ui.TEXT,
            relief="flat", highlightthickness=1, highlightbackground=ui.BORDER,
            font=(ui.MONO, 8), padx=6, pady=4, state="disabled",
        )
        self.last_poly.grid(row=8, column=0, sticky="ew")
        ttk.Button(warn, text="OPEN FULL WARNGEN", command=self._warngen).grid(
            row=9, column=0, sticky="ew", pady=(8, 0)
        )

        alerts = ttk.Frame(notebook, padding=8)
        notebook.add(alerts, text="Active Alerts - Unified")
        alerts.rowconfigure(1, weight=1)
        alerts.columnconfigure(0, weight=1)
        ttk.Label(alerts, text="AWIPS ACTIVE ALERTS - UNIFIED", style="Header.TLabel").grid(
            row=0, column=0, sticky="w"
        )
        self.alert_tree = ui.tree(
            alerts,
            [("event", "Event", 160), ("area", "Area", 140),
             ("status", "Act", 44), ("expires", "Expires", 64)],
            height=14,
        )
        self.alert_tree.grid(row=1, column=0, sticky="nsew", pady=(4, 0))
        self.alert_tree.bind("<Double-1>", lambda _e: self._sent_alerts())
        row = ttk.Frame(alerts)
        row.grid(row=2, column=0, sticky="ew", pady=(6, 0))
        ttk.Button(row, text="REFRESH", command=self._refresh_alerts).pack(side="left")
        ttk.Button(row, text="VIEW / EDIT SENT", command=self._sent_alerts).pack(
            side="left", padx=4
        )
        self.alert_summary = tk.StringVar(value="No active alerts.")
        ttk.Label(alerts, textvariable=self.alert_summary, style="Muted.TLabel",
                  wraplength=340, justify="left").grid(row=3, column=0, sticky="w",
                                                      pady=(6, 0))

        traffic = ttk.Frame(notebook, padding=8)
        notebook.add(traffic, text="LOTIEM")
        traffic.rowconfigure(0, weight=1)
        traffic.columnconfigure(0, weight=1)
        holder = ttk.Frame(traffic)
        holder.grid(row=0, column=0, sticky="nsew")
        self.traffic = ui.scrolled_text(holder, height=16)
        self.traffic.configure(state="disabled")

        self._refresh_alerts()

    # -------------------------------------------------------------- helpers
    def log(self, message: str, tag: str = "") -> None:
        if hasattr(self, "status"):
            self.status.middle.set(message[:120])

    def _select_all(self, _event=None) -> str:
        self.editor.tag_add("sel", "1.0", "end-1c")
        return "break"

    def _update_counts(self) -> None:
        content = self.editor.get("1.0", "end-1c")
        paras = len([p for p in content.split("\n\n") if p.strip()])
        line = self.editor.index("insert")
        self.count_var.set(
            f"{len(content)} chars  |  {content.count(chr(10)) + 1} lines  |  "
            f"{paras} segments  |  cursor {line}"
        )

    def _product(self) -> awips.Product:
        for pid in awips.PRODUCT_ORDER:
            prod = awips.product(pid)
            if prod.name == self.product_var.get():
                return prod
        return awips.product("SPS")

    def _ugc(self) -> list[str]:
        return list(self._product().ugc) or ["INZ001", "INZ002"]

    def _header_stamp(self) -> str:
        return tz.awips_timestamp(tz.utc_now())

    def _compose_header_text(self) -> str:
        prod = self._product()
        bbb = self.bbb_var.get().strip().upper()
        lines = [
            f"{self.ttaa_var.get().strip() or prod.wmo} "
            f"{self.cccc_var.get().strip() or 'KLOT'} {self._header_stamp()}"
            + (f" {bbb}" if bbb and bbb not in ("NOR", "NONE", "-") else ""),
            f"{prod.pil}{self.designator_var.get().strip() or 'LOT'}",
            f"WSFO ID... {self.wsfo_var.get().strip() or 'CHI'}",
            f"PRODUCT CATEGORY... {self.category_var.get()}",
            f"DESIGNATOR... {self.designator_var.get().strip() or 'LOT'}",
            f"ADDRESSEE... {self.addressee_var.get().strip() or 'ALL'}",
            f"BBB... {bbb}  version {self.bbbver_var.get()}",
        ]
        return "\n".join(lines)

    def _enter_header(self) -> None:
        text = self._compose_header_text()
        self.header_preview.configure(state="normal")
        self.header_preview.delete("1.0", "end")
        self.header_preview.insert("1.0", text)
        self.header_preview.configure(state="disabled")
        self.log("AWIPS header block confirmed")
        if not self.ttaa_var.get().strip()[:2].isalpha():
            messagebox.showwarning("AWIPS Header", "TTAAii should start with two letters.",
                                   parent=self.root)

    def _category_changed(self) -> None:
        wmo = CATEGORY_WMO.get(self.category_var.get())
        if wmo:
            self.ttaa_var.set(wmo)

    def _wfo_lot(self) -> None:
        self.ttaa_var.set("WWUS83")
        self.cccc_var.set("KLOT")
        self.bbb_var.set("NOR")
        self.bbbver_var.set(1)
        self.wsfo_var.set("CHI")
        self.category_var.set("Weather")
        self.designator_var.set("LOT")
        self.addressee_var.set("ALL")
        self._enter_header()
        messagebox.showinfo(
            "WFO LOT",
            "WFO LOT defaults restored.\n\n"
            "Chicago/Romeoville, Illinois\n"
            "LOTIEM: 192.168.10.144:6000\n"
            "Designator LOT  |  Addressee ALL",
            parent=self.root,
        )

    def _restore_ui(self) -> None:
        ui.center(self.root, 1400, 900)
        self.editor_mode = False
        self.editor.configure(wrap="word")
        self.editor_button.configure(text="ENTER EDITOR MODE")
        self.map.frame_index = 6
        self.map.clear_polygon()
        self.last_polygon = []
        self.latlon_var.set("LAT...LON  --")
        self.wrap_var.set(int(self.settings.get("text_workstation.wrap", 69)))
        self._enter_header()
        self.log("RESTORE UI - layout, editor and polygon tool reset")

    def _toggle_editor_mode(self) -> None:
        self.editor_mode = not self.editor_mode
        if self.editor_mode:
            self.editor.configure(wrap="none")
            self.editor_button.configure(text="EXIT EDITOR MODE")
            self.editor.focus_set()
            self.log("EDITOR MODE ON - free-form editing, right-click for segment tools")
        else:
            self.editor.configure(wrap="word")
            self.editor_button.configure(text="ENTER EDITOR MODE")
            self.log("EDITOR MODE OFF - word wrap restored")

    def _new_message(self) -> None:
        if not messagebox.askyesno(
            "New Text Message", "Clear the editor and start a new message?", parent=self.root
        ):
            return
        self.editor.delete("1.0", "end")
        self.product_var.set("Special Weather Statement")
        self.category_var.set("Weather")
        self._enter_header()
        self.editor.insert("1.0", "$$")
        self.editor.mark_set("insert", "1.0")
        self.log("new text message started")

    def _clear_editor(self) -> None:
        self.editor.delete("1.0", "end")
        self._update_counts()

    # ------------------------------------------------------ segment tools
    def _block(self) -> tuple[int, int, str]:
        content = self.editor.get("1.0", "end-1c")
        lines = content.split("\n")
        cursor_line = int(self.editor.index("insert").split(".")[0]) - 1
        cursor_line = max(0, min(cursor_line, len(lines) - 1))
        if not lines or not content.strip():
            return 0, 0, ""
        start = cursor_line
        while start > 0 and lines[start - 1].strip():
            start -= 1
        end = cursor_line
        while end < len(lines) - 1 and lines[end + 1].strip():
            end += 1
        return start, end, "\n".join(lines[start:end + 1])

    def _block_indices(self) -> tuple[str, str]:
        start, end, _text = self._block()
        return f"{start + 1}.0", f"{end + 1}.end"

    def _editor_menu(self, event) -> None:
        try:
            self.editor.mark_set("insert", f"@{event.x},{event.y}")
            self.editor_menu.tk_popup(event.x_root, event.y_root)
        finally:
            self.editor_menu.grab_release()

    def _add_segment(self) -> None:
        def apply(text: str, kind: str) -> None:
            self.editor.insert("insert", f"\n\n{text}\n")
            self._update_counts()

        SegmentDialog(self.root, apply, title="Add Segment")

    def _edit_segment(self) -> None:
        start, end, text = self._block()
        if not text.strip():
            messagebox.showinfo("Edit Segment", "Place the cursor inside a segment first.",
                                parent=self.root)
            return

        def apply(new_text: str, _kind: str) -> None:
            self.editor.delete(f"{start + 1}.0", f"{end + 1}.end")
            self.editor.insert(f"{start + 1}.0", new_text)
            self._update_counts()

        SegmentDialog(self.root, apply, title="Edit Segment", text=text)

    def _remove_segment(self) -> None:
        start, end, text = self._block()
        if not text.strip():
            return
        if len(text) > 80 and not messagebox.askyesno(
            "Remove Segment", "Remove this segment?\n\n" + text[:120] + "...",
            parent=self.root,
        ):
            return
        self.editor.delete(f"{start + 1}.0", f"{end + 1}.end")
        self._update_counts()

    def _combine_segment(self) -> None:
        start, end, _text = self._block()
        content = self.editor.get("1.0", "end-1c")
        lines = content.split("\n")
        nxt = end + 1
        while nxt < len(lines) and not lines[nxt].strip():
            nxt += 1
        if nxt >= len(lines):
            messagebox.showinfo("Combine Segment", "There is no following segment to combine.",
                                parent=self.root)
            return
        # remove the blank line(s) between the two blocks
        self.editor.delete(f"{end + 1}.end", f"{nxt + 1}.0")
        self.editor.insert(f"{end + 1}.end", " ")
        self._update_counts()

    def _add_hazard_segment(self) -> None:
        HazardSegmentBuilder(
            self.root,
            on_insert=lambda text, target: self._insert_hazard(
                text, existing=(target == "existing")
            ),
        )

    def _add_hazard_existing(self) -> None:
        HazardSegmentBuilder(
            self.root, on_insert=lambda text, _target: self._insert_hazard(text, existing=True)
        )

    def _insert_hazard(self, text: str, existing: bool = False) -> None:
        start, end, block = self._block()
        if existing and block.strip():
            self.editor.insert(f"{end + 1}.end", "\n\n" + text)
        else:
            self.editor.insert("insert", f"\n\n{text}\n")
        self._update_counts()
        self.log("hazard segment added")

    # -------------------------------------------------------- wrap actions
    def _rewrap(self) -> None:
        width = int(self.wrap_var.get())
        body = self.editor.get("1.0", "end-1c")
        if not body.strip():
            return
        paragraphs = [p.strip() for p in body.split("\n\n") if p.strip()]
        wrapped = "\n\n".join(textwrap.fill(p, width) for p in paragraphs)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", wrapped)
        self._update_counts()
        self.log(f"text rewrapped at {width} columns")

    # ------------------------------------------------------ compose + send
    def compose(self) -> str:
        prod = self._product()
        body = self.editor.get("1.0", "end-1c").strip()
        if body in ("$$", ""):
            body = "(no message text)"
        ugc = self._ugc()
        stamp = self._header_stamp()
        header_lines = self._compose_header_text().split("\n")
        lines = [
            header_lines[0],
            header_lines[1],
            f"ADDRESSEE... {self.addressee_var.get().strip() or 'ALL'}",
            zones.ugc_block(ugc, stamp),
            "",
            body,
            "",
            "$$",
        ]
        return "\n".join(lines)

    def _dispatch(self, route: str) -> None:
        text = self.compose()
        prod = self._product()
        ugc = self._ugc()
        subject = f"{self.category_var.get()} {prod.name} for {zones.describe_area(ugc)}"
        subscriber = self.settings.get(f"lotiem.subscribers.{route}", route)
        payload = {
            "product": {"pil": prod.awips_id, "name": prod.name, "code": prod.pil},
            "ugc": ugc,
            "text": text,
            "subject": subject,
            "routes": [route],
            "subscribers": {route: subscriber},
            "header": {
                "ttaa": self.ttaa_var.get(), "cccc": self.cccc_var.get(),
                "bbb": self.bbb_var.get(), "designator": self.designator_var.get(),
                "wsfo": self.wsfo_var.get(), "addressee": self.addressee_var.get(),
                "category": self.category_var.get(),
            },
        }
        message = self.bus.publish("product", payload, target="ALL")
        self._append_traffic(
            f"DISPATCH -> {ROUTE_LABELS.get(route, route)}  [{subscriber}]  "
            f"{prod.pil}  seq {message['seq']}"
        )
        self.log(f"sent {ROUTE_LABELS.get(route, route)}: {prod.name}")
        self.status.left.set(f"dispatched to {ROUTE_LABELS.get(route, route)}  |  {subscriber}")
        if route == "BMH":
            messagebox.showinfo(
                "Send to BMH",
                f"{prod.name} dispatched to BMH.\n\n{subject}",
                parent=self.root,
            )

    def _enter(self) -> None:
        self._enter_header()
        self._dispatch("BMH")

    # ----------------------------------------------------------- alerts
    def _refresh_alerts(self) -> None:
        self.alert_tree.delete(*self.alert_tree.get_children())
        for alert in self.store.active():
            self.alert_tree.insert(
                "", "end", iid=alert.alert_id,
                values=(alert.event, alert.area, alert.status,
                        f"{alert.expires:%H:%M}Z"),
            )
        self.alert_summary.set(self.store.summary())

    def _sent_alerts(self) -> None:
        SentAlertsWindow(self.root, self.store, on_change=self._refresh_alerts)

    # ------------------------------------------------------------ polygons
    def _polygon_done(self, points: list[tuple[float, float]]) -> None:
        self.last_polygon = points
        self.latlon_var.set(awips.latlon_block(points))
        self._show_last_polygon(points)

    def _show_last_polygon(self, points: list[tuple[float, float]]) -> None:
        if not points:
            text = "no polygon"
        else:
            lat, lon = awips.polygon_centroid(points)
            text = (
                f"{len(points)} vertices  centroid {lat:.4f} / {lon:.4f}\n"
                f"{awips.latlon_block(points)}\n"
                f"ZONES: {' '.join(zones.zones_for_polygon(points)[:8])}"
            )
        self.last_poly.configure(state="normal")
        self.last_poly.delete("1.0", "end")
        self.last_poly.insert("1.0", text)
        self.last_poly.configure(state="disabled")

    def _use_polygon(self) -> None:
        if not self.last_polygon:
            messagebox.showinfo("Polygon Tool", "Draw a polygon on the map first.",
                                parent=self.root)
            return
        text = (
            "\n\n"
            + awips.latlon_block(self.last_polygon)
            + "\n"
            + f"LAT...LON polygon for {', '.join(zones.zones_for_polygon(self.last_polygon)[:6])}"
        )
        self.editor.insert("insert", text)
        self._update_counts()
        self.log("polygon LAT...LON inserted into the message")

    def _clear_polygon(self) -> None:
        self.last_polygon = []
        self.map.clear_polygon()
        self.latlon_var.set("LAT...LON  --")
        self._show_last_polygon([])

    def _warngen(self, mode: str | None = None) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, default_ugc=self._ugc(), title="WarnGen  |  KLOT LOTIEM",
            on_issue=self._warngen_issued,
        )
        if mode:
            dialog.mode_var.set(mode)
            dialog._update_preview()

    def _watchgen(self) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, default_ugc=self._ugc(), title="WatchGen  |  KLOT LOTIEM",
            on_issue=self._warngen_issued,
        )
        dialog.product_var.set("Tornado Watch")
        dialog._update_preview()

    def _quick_warn(self, code: str) -> None:
        from warngen_dialog import WarnGenDialog

        dialog = WarnGenDialog(
            self.root, default_ugc=self._ugc(),
            title=f"WarnGen  |  {awips.product(code).name}",
            on_issue=self._warngen_issued,
        )
        dialog.product_var.set(awips.product(code).name)
        dialog._update_preview()

    def _warngen_issued(self, text, prod, ugc, cell, points) -> None:
        self.last_polygon = list(points)
        self.latlon_var.set(awips.latlon_block(points))
        self._show_last_polygon(points)
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", text)
        self._refresh_alerts()
        self.log(f"WarnGen {prod.name} issued for {zones.describe_area(ugc)}")

    # ---------------------------------------------------------- lotiem bus
    def _poll_bus(self) -> None:
        if self._closed:
            return
        try:
            for message in self.bus.poll():
                if message.get("from") == "LOTWPS":
                    continue
                self._bus_messages.append(message)
                del self._bus_messages[:-80]
                topic = message.get("topic")
                payload = message.get("payload", {})
                summary = payload.get("subject") or payload.get("action") or topic
                self._append_traffic(f"{message.get('from')} -> {topic}: {summary}")
                if topic == "alert":
                    self._refresh_alerts()
        except Exception as exc:
            self._append_traffic(f"bus error: {exc}")
        try:
            self._bus_job = self.root.after(2000, self._poll_bus)
        except tk.TclError:
            self._bus_job = None

    def _append_traffic(self, line: str) -> None:
        if not hasattr(self, "traffic"):
            return
        stamp = tz.central_now()[0].strftime("%H:%M:%S")
        self.traffic.configure(state="normal")
        self.traffic.insert("end", f"{stamp}  {line}\n")
        self.traffic.see("end")
        self.traffic.configure(state="disabled")

    # -------------------------------------------------------------- timers
    def _tick(self) -> None:
        if self._closed:
            return
        now, label = tz.central_now()
        self.clock_var.set(f"{now:%H:%M:%S} {label}  {now:%a %b} {now.day}")
        try:
            self._tick_job = self.root.after(1000, self._tick)
        except tk.TclError:
            pass

    def _about(self) -> None:
        messagebox.showinfo(
            "About LOTWPS",
            "KLOT LOTIEM TEXT WORKSTATION\n"
            "LOT Weather Processing System 3.1.0\n\n"
            "WFO LOT  |  Chicago/Romeoville, IL\n"
            "LOTIEM  |  192.168.10.144:6000\n"
            "Products: AWIPS II text, WarnGen, WatchGen, SAME alerts, "
            "Zone Forecast, AFD, HWO, RWR, CLI, MFM\n"
            "Voices: VoiceText Paul, Microsoft David, Microsoft Zira",
            parent=self.root,
        )

    def _close(self) -> None:
        self._closed = True
        for job in (self._bus_job, self._tick_job):
            if job:
                try:
                    self.root.after_cancel(job)
                except Exception:
                    pass
        self.root.destroy()

    def mainloop(self) -> None:
        self.root.mainloop()


def main() -> None:
    TextWorkstation().mainloop()


if __name__ == "__main__":
    main()
