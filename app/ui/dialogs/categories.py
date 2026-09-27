"""Dialogue de suppression d'une liste d'articles."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.config import COLORS
from app.database import Database


def delete_list(parent: tk.Misc, db: Database, on_done=None) -> None:
    names = db.category_names()
    if len(names) <= 1:
        messagebox.showwarning("Liste", "Au moins une liste doit être conservée.")
        return
    win = tk.Toplevel(parent)
    win.title("Supprimer une liste")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    ttk.Label(win, text="Liste à supprimer :").pack(anchor="w", padx=14, pady=(14, 6))
    var = tk.StringVar(value=names[0])
    ttk.Combobox(win, textvariable=var, state="readonly", values=names, width=30).pack(padx=14)
    ttk.Label(
        win,
        text="Les articles de cette liste seront supprimés.\n"
             "Les documents déjà enregistrés dans l'historique sont conservés.",
        foreground="#555",
    ).pack(anchor="w", padx=14, pady=(10, 0))

    def confirm() -> None:
        name = var.get()
        if not messagebox.askyesno(
            "Supprimer",
            f"Supprimer la liste « {name} » et tous ses articles ?",
            parent=win,
        ):
            return
        db.delete_category(name)
        win.destroy()
        if on_done:
            on_done()
        messagebox.showinfo("Liste", f"La liste « {name} » a été supprimée.")

    actions = ttk.Frame(win)
    actions.pack(fill="x", padx=14, pady=14)
    ttk.Button(actions, text="Supprimer", style="Accent.TButton", command=confirm).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
