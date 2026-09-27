"""Dialogue de choix de la feuille Excel et du nom de la liste à importer."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.config import COLORS


def ask_import_target(parent: tk.Misc, sheets: list[str]) -> dict[str, str] | None:
    win = tk.Toplevel(parent)
    win.title("Importer une feuille Excel")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    ttk.Label(win, text="Feuille Excel :").grid(row=0, column=0, sticky="w", padx=14, pady=(14, 4))
    sheet_var = tk.StringVar(value=sheets[0])
    sheet_combo = ttk.Combobox(win, textvariable=sheet_var, state="readonly", values=sheets, width=32)
    sheet_combo.grid(row=0, column=1, sticky="w", padx=(0, 14), pady=(14, 4))

    ttk.Label(win, text="Nom de la liste :").grid(row=1, column=0, sticky="w", padx=14, pady=4)
    name_var = tk.StringVar(value=sheets[0])
    name_entry = ttk.Entry(win, textvariable=name_var, width=34)
    name_entry.grid(row=1, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(
        win,
        text="La liste est créée si elle n'existe pas.\n"
             "Si elle existe, ses articles sont remplacés après confirmation.",
        style="Muted.TLabel",
    ).grid(row=2, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 0))
    ttk.Label(
        win,
        text="Format : N° | Désignation | Unité de mesure | Prix unitaire HT",
        style="Muted.TLabel",
    ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(2, 0))

    edited = {"value": False}
    name_entry.bind("<KeyRelease>", lambda e: edited.__setitem__("value", True))

    def on_sheet_change(event=None):
        if not edited["value"]:
            name_var.set(sheet_var.get())

    sheet_combo.bind("<<ComboboxSelected>>", on_sheet_change)

    result: dict[str, str] = {}

    def validate() -> None:
        name = name_var.get().strip()
        if not name:
            messagebox.showwarning("Import", "Saisissez un nom de liste.", parent=win)
            return
        result["sheet"] = sheet_var.get()
        result["name"] = name
        win.destroy()

    actions = ttk.Frame(win)
    actions.grid(row=4, column=0, columnspan=2, sticky="e", padx=14, pady=14)
    ttk.Button(actions, text="Importer", style="Accent.TButton", command=validate).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)

    parent.wait_window(win)
    return result or None
