"""Edit an existing alert (headline, text, expiry, status) in any LOTWPS window."""

from __future__ import annotations

import sys
import tkinter as tk
from datetime import timedelta
from pathlib import Path
from tkinter import ttk

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lotwps import alerts as alert_mod, tz, ui


class AlertEditor(tk.Toplevel):
    def __init__(self, parent: tk.Misc, alert, on_save=None) -> None:
        super().__init__(parent)
        self.alert = alert
        self.on_save = on_save
        self.store = alert_mod.store()
        self.title(f"Edit Alert  |  {alert.alert_id}")
        self.configure(background=ui.BG)
        ui.center(self, 760, 620, parent)
        self.minsize(680, 520)
        self._build()
        self.transient(parent)
        self.grab_set()

    def _build(self) -> None:
        a = self.alert
        head = ttk.Frame(self, style="Panel.TFrame", padding=(12, 8))
        head.pack(fill="x")
        ttk.Label(head, text=a.alert_id, style="Title.TLabel").pack(side="left")
        ttk.Label(
            head, text=f"  {a.event}  |  {a.tier}  |  {a.area}", style="Muted.TLabel"
        ).pack(side="left")
        self.status_var = tk.StringVar(value=a.status)
        ttk.Label(head, textvariable=self.status_var, style="Header.TLabel").pack(side="right")

        body = ttk.Frame(self, padding=10)
        body.pack(fill="both", expand=True)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(2, weight=1)
        body.rowconfigure(4, weight=1)

        self.headline_var = tk.StringVar(value=a.headline)
        ttk.Label(body, text="HEADLINE", style="Muted.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Entry(body, textvariable=self.headline_var).grid(
            row=0, column=1, columnspan=3, sticky="ew", pady=2
        )

        info = ttk.Frame(body)
        info.grid(row=1, column=0, columnspan=4, sticky="w", pady=(6, 2))
        self.expires_var = tk.IntVar(value=max(1, a.minutes_left))
        self.status_box = tk.StringVar(value=a.status)
        self.same_var = tk.StringVar(value=a.same_header)
        ttk.Label(info, text="EXPIRES IN (MIN)", style="Muted.TLabel").pack(side="left")
        ttk.Spinbox(info, from_=1, to=1440, textvariable=self.expires_var, width=6).pack(
            side="left", padx=(4, 12)
        )
        ttk.Label(info, text="STATUS", style="Muted.TLabel").pack(side="left")
        ttk.Combobox(
            info, textvariable=self.status_box, width=6, state="readonly",
            values=["NEW", "CON", "CAN", "EXP"],
        ).pack(side="left", padx=4)
        ttk.Button(info, text="RETONE", command=self._retone).pack(side="left", padx=10)

        ttk.Label(body, text="DESCRIPTION / CALL TO ACTION", style="Muted.TLabel").grid(
            row=2, column=0, columnspan=4, sticky="w"
        )
        text_frame = ttk.Frame(body)
        text_frame.grid(row=3, column=0, columnspan=4, sticky="nsew")
        text_frame.rowconfigure(0, weight=1)
        text_frame.columnconfigure(0, weight=1)
        self.description = tk.Text(
            text_frame, height=8, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 9), padx=8, pady=6,
        )
        self.description.grid(row=0, column=0, sticky="nsew")
        self.description.insert("1.0", a.description)

        ttk.Label(body, text="INSTRUCTION", style="Muted.TLabel").grid(
            row=4, column=0, columnspan=4, sticky="w", pady=(6, 2)
        )
        self.instruction = tk.Text(
            body, height=4, wrap="word", background=ui.FIELD, foreground=ui.TEXT,
            insertbackground=ui.TEXT, relief="flat", highlightthickness=1,
            highlightbackground=ui.BORDER, font=(ui.MONO, 9), padx=8, pady=6,
        )
        self.instruction.grid(row=5, column=0, columnspan=4, sticky="nsew")
        self.instruction.insert("1.0", a.instruction)

        same_row = ttk.Frame(body)
        same_row.grid(row=6, column=0, columnspan=4, sticky="ew", pady=(8, 0))
        ttk.Label(same_row, text="SAME", style="Muted.TLabel").pack(side="left")
        ttk.Entry(same_row, textvariable=self.same_var, state="readonly").pack(
            side="left", fill="x", expand=True, padx=6
        )
        ttk.Button(same_row, text="COPY", command=self._copy_same).pack(side="left")

        buttons = ttk.Frame(self, style="Panel.TFrame", padding=(10, 8))
        buttons.pack(fill="x")
        ttk.Button(
            buttons, text="SAVE CHANGES", style="Accent.TButton", command=self._save
        ).pack(side="left")
        ttk.Button(buttons, text="CANCEL ALERT", style="Danger.TButton",
                   command=self._cancel).pack(side="left", padx=6)
        ttk.Button(buttons, text="CLOSE", command=self.destroy).pack(side="right")

        ttk.Label(
            buttons, text=f"issued {a.issued:%m/%d %H:%M}Z   expires {a.expires:%m/%d %H:%M}Z",
            style="Muted.TLabel",
        ).pack(side="right", padx=10)

    # -- actions ---------------------------------------------------------
    def _retone(self) -> None:
        updated = self.store.retone(self.alert.alert_id)
        if updated:
            self.alert = updated
            self.same_var.set(updated.same_header)
            self.status_var.set(updated.status)

    def _copy_same(self) -> None:
        self.clipboard_clear()
        self.clipboard_append(self.same_var.get())

    def _cancel(self) -> None:
        updated = self.store.cancel(self.alert.alert_id)
        if updated:
            self.alert = updated
            self.status_var.set(updated.status)

    def _save(self) -> None:
        a = self.alert
        a.headline = self.headline_var.get().strip()
        a.description = self.description.get("1.0", "end").strip()
        a.instruction = self.instruction.get("1.0", "end").strip()
        a.status = self.status_box.get()
        a.expires = tz.utc_now() + timedelta(minutes=int(self.expires_var.get()))
        self.store.update(a)
        if self.on_save:
            self.on_save(a)
        self.destroy()


def edit_alert(parent, alert, on_save=None) -> AlertEditor:
    return AlertEditor(parent, alert, on_save=on_save)
