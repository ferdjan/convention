"""Écran « Conventions » : tableau de toutes les conventions et de leurs exercices.

Affiche toutes les conventions (sans filtre) avec leur statut (actif / clôturé /
expiré) et leur échéance. La sélection d'une convention affiche ses exercices,
que l'on peut ouvrir, modifier ou clôturer.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.database import Database
from app.ui.common import money
from app.ui.dialogs.conventions import (
    ask_open_exercice,
    close_exercice_dialog,
    edit_convention_status,
    edit_exercice,
)

STATUS_LABELS = {
    "active": "Actif",
    "closed": "Clôturé",
    "expiree": "Expiré",
}


class ConventionsView(ttk.Frame):
    """Gestion des conventions et de leurs exercices."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=16)
        self.app = app
        self.db: Database = app.db

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- barre d'outils : import / modèle / suppression de liste
        toolbar = ttk.Frame(self)
        toolbar.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        ttk.Button(
            toolbar, text="Importer une liste Excel...",
            style="Accent.TButton", command=self.app.import_excel,
        ).pack(side="left")
        ttk.Button(
            toolbar, text="Enregistrer un modèle Excel...",
            command=self.app.save_template,
        ).pack(side="left", padx=10)
        ttk.Button(
            toolbar, text="Supprimer une liste...",
            command=self.app.delete_list,
        ).pack(side="left")

        # --- panneau vertical : tableau des conventions + exercices
        body = ttk.Panedwindow(self, orient="vertical")
        body.grid(row=1, column=0, sticky="nsew")

        conv_frame = ttk.LabelFrame(body, text="Conventions", padding=12)
        conv_frame.rowconfigure(0, weight=1)
        conv_frame.columnconfigure(0, weight=1)
        ccols = ("name", "status", "expiry", "exercice", "plafond", "consomme", "reste")
        self.conv_tree = ttk.Treeview(
            conv_frame, columns=ccols, show="headings", selectmode="browse", height=6
        )
        for c, h, w in (
            ("name", "Convention", 180),
            ("status", "Statut", 90),
            ("expiry", "Échéance", 110),
            ("exercice", "Exercice actif", 120),
            ("plafond", "Plafond", 120),
            ("consomme", "Consommé", 120),
            ("reste", "Reste", 120),
        ):
            self.conv_tree.heading(c, text=h)
            self.conv_tree.column(c, width=w, anchor="center" if c != "name" else "w")
        self.conv_tree.grid(row=0, column=0, sticky="nsew")
        cvs = ttk.Scrollbar(conv_frame, orient="vertical", command=self.conv_tree.yview)
        cvs.grid(row=0, column=1, sticky="ns")
        self.conv_tree.configure(yscrollcommand=cvs.set)
        self.conv_tree.bind("<<TreeviewSelect>>", lambda e: self.refresh_exercices())
        body.add(conv_frame, weight=1)

        ex_frame = ttk.LabelFrame(body, text="Exercices de la convention sélectionnée", padding=12)
        ex_frame.rowconfigure(0, weight=1)
        ex_frame.columnconfigure(0, weight=1)
        cols = ("label", "periode", "plafond", "consomme", "reste", "status")
        self.tree = ttk.Treeview(ex_frame, columns=cols, show="headings", selectmode="browse", height=6)
        for c, h, w in (
            ("label", "Exercice", 120),
            ("periode", "Période", 200),
            ("plafond", "Plafond", 130),
            ("consomme", "Consommé", 130),
            ("reste", "Reste", 130),
            ("status", "Statut", 100),
        ):
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, anchor="center" if c != "label" else "w")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(ex_frame, orient="vertical", command=self.tree.yview)
        vs.grid(row=0, column=1, sticky="ns")
        self.tree.configure(yscrollcommand=vs.set)
        self.tree.bind("<Double-1>", lambda e: self.edit_selected())
        body.add(ex_frame, weight=1)

        # --- actions
        actions = ttk.Frame(self)
        actions.grid(row=2, column=0, sticky="ew", pady=(14, 0))
        ttk.Button(
            actions, text="Statut / échéance de la convention...",
            command=self.change_status,
        ).pack(side="right")
        ttk.Button(
            actions, text="Clôturer l'exercice sélectionné",
            command=self.close_selected,
        ).pack(side="right", padx=8)
        ttk.Button(
            actions, text="Modifier l'exercice...", command=self.edit_selected,
        ).pack(side="right", padx=8)
        ttk.Button(
            actions, text="Ouvrir un nouvel exercice...",
            style="Accent.TButton", command=self.new_exercice,
        ).pack(side="right", padx=8)

    # ----------------------------------------------------------------- lecture

    def load(self) -> None:
        self.refresh()

    def select_convention(self, name: str) -> None:
        if name and self.conv_tree.exists(name):
            self.conv_tree.selection_set(name)
            self.conv_tree.focus(name)
        self.refresh_exercices()

    def refresh(self) -> None:
        for item in self.conv_tree.get_children():
            self.conv_tree.delete(item)
        for row in self.db.list_categories():
            name = row["name"]
            status = self.db.effective_status(row["status"], row["expiry_date"])
            exercice = self.db.get_active_exercice(name)
            if exercice:
                summary = self.db.exercice_summary(name, exercice["label"])
                exercice_text = exercice["label"]
                plafond = "illimité" if summary["plafond"] is None else money(summary["plafond"])
                consomme = money(summary["consumed"])
                reste = "—" if summary["remaining"] is None else money(summary["remaining"])
            else:
                exercice_text = "—"
                plafond = "—"
                consomme = "—"
                reste = "—"
            self.conv_tree.insert(
                "", "end", iid=name,
                values=(
                    name,
                    STATUS_LABELS.get(status, status),
                    row["expiry_date"] or "—",
                    exercice_text,
                    plafond,
                    consomme,
                    reste,
                ),
            )
        # Restaurer la sélection si possible.
        self.refresh_exercices()

    def refresh_exercices(self) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        name = self._current()
        if not name:
            return
        for row in self.db.list_exercices(name):
            if row["status"] == "active":
                summary = self.db.exercice_summary(name, row["label"])
                plafond = summary["plafond"]
                consumed = summary["consumed"]
                remaining = summary["remaining"]
                status_text = "Actif"
            else:
                plafond = row["plafond"]
                consumed = row["consumed_at_close"]
                remaining = row["remaining_at_close"]
                status_text = "Clôturé"
            self.tree.insert(
                "", "end", iid=row["label"],
                values=(
                    row["label"],
                    f"{row['start_date']} → {row['end_date']}",
                    "illimité" if plafond is None else money(plafond),
                    money(consumed or 0.0),
                    "—" if remaining is None else money(remaining),
                    status_text,
                ),
            )

    def _current(self) -> str | None:
        sel = self.conv_tree.selection()
        return sel[0] if sel else None

    def _selected(self) -> str | None:
        sel = self.tree.selection()
        return sel[0] if sel else None

    # ----------------------------------------------------------------- actions

    def _after_change(self) -> None:
        self.refresh()
        self.app._after_categories_changed()

    def new_exercice(self) -> None:
        name = self._current()
        if not name:
            messagebox.showwarning("Conventions", "Sélectionnez une convention.", parent=self)
            return
        if self.db.get_active_exercice(name):
            ask_open_exercice(self, self.db, name, self._after_change)
        else:
            edit_exercice(self, self.db, name, None, self._after_change)

    def edit_selected(self) -> None:
        name = self._current()
        label = self._selected()
        if not name or not label:
            messagebox.showwarning("Conventions", "Sélectionnez un exercice.", parent=self)
            return
        row = self.db.get_exercice(name, label)
        edit_exercice(
            self, self.db, name,
            {
                "label": row["label"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "plafond": row["plafond"],
            },
            self._after_change,
        )

    def close_selected(self) -> None:
        name = self._current()
        label = self._selected()
        if not name or not label:
            messagebox.showwarning("Conventions", "Sélectionnez un exercice.", parent=self)
            return
        row = self.db.get_exercice(name, label)
        if row["status"] != "active":
            messagebox.showinfo("Conventions", "Cet exercice est déjà clôturé.", parent=self)
            return
        close_exercice_dialog(self, self.db, name, label, self._after_change)

    def change_status(self) -> None:
        name = self._current()
        if not name:
            messagebox.showwarning("Conventions", "Sélectionnez une convention.", parent=self)
            return
        edit_convention_status(self, self.db, name, self._after_change)
