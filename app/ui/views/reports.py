"""Écran « Rapport de consommation » : export Excel par exercice."""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from app.config import CURRENT_USER
from app.database import Database
from app.reports.annual import build_exercice_report


class ReportsView(ttk.Frame):
    """Choix d'un exercice puis export du rapport Excel de consommation."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=24)
        self.app = app
        self.db: Database = app.db

    def build(self) -> None:
        self.columnconfigure(0, weight=1)
        ttk.Label(
            self,
            text="Rapport de consommation par exercice",
            style="Section.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))
        ttk.Label(
            self,
            text="Le rapport Excel contient une feuille « Synthèse » (plafond, "
                 "consommé, reste, taux par convention) et une feuille "
                 "« Documents » (détail des commandes de l'exercice).",
            style="Muted.TLabel",
            wraplength=720,
        ).grid(row=1, column=0, sticky="w", pady=(0, 12))

        box = ttk.Frame(self, style="Card.TFrame", padding=16)
        box.grid(row=2, column=0, sticky="ew")
        ttk.Label(box, text="Exercice :").pack(side="left")
        self.exercices: list[str] = []
        # Correspondance « libellé affiché (label + période) » -> libellé d'exercice.
        self._display_to_label: dict[str, str] = {}
        self.exercice_var = tk.StringVar()
        self.exercice_combo = ttk.Combobox(
            box, textvariable=self.exercice_var, state="readonly", width=34
        )
        self.exercice_combo.pack(side="left", padx=8)
        ttk.Button(
            box, text="Générer le rapport Excel...",
            style="Accent.TButton", command=self.export_report,
        ).pack(side="left", padx=16)

    def refresh(self) -> None:
        labels: list[str] = []
        periods: dict[str, str] = {}
        for row in self.db.list_all_exercices():
            label = row["label"]
            if label in periods:
                continue
            periods[label] = f"{row['start_date']} → {row['end_date']}"
            labels.append(label)
        self.exercices = labels
        self._display_to_label = {
            f"{label} ({periods[label]})": label for label in labels
        }
        self.exercice_combo.configure(values=list(self._display_to_label))
        if labels and self.exercice_var.get() not in self._display_to_label:
            self.exercice_var.set(next(iter(self._display_to_label)))

    def _selected_label(self) -> str | None:
        """Libellé d'exercice réel (sans la période affichée)."""
        value = self.exercice_var.get().strip()
        if value in self._display_to_label:
            return self._display_to_label[value]
        # Tolérance : "label (période)" ou "label" seul.
        return value.split(" (")[0].strip() or None

    def export_report(self) -> None:
        label = self._selected_label()
        if not label:
            messagebox.showinfo(
                "Rapport de consommation",
                "Aucun exercice n'existe encore. Ouvrez-en un depuis l'écran "
                "« Conventions ».",
                parent=self,
            )
            return
        dest = filedialog.asksaveasfilename(
            title="Enregistrer le rapport de consommation",
            defaultextension=".xlsx",
            initialfile=f"consommation_{label}.xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not dest:
            return
        try:
            summary = self.db.exercice_consumption_report(label)
            documents = self.db.exercice_documents(label)
            build_exercice_report(dest, label, summary, documents, generated_by=CURRENT_USER)
        except Exception as exc:
            messagebox.showerror(
                "Rapport de consommation",
                f"Impossible de générer le rapport.\n\n{exc}",
                parent=self,
            )
            return
        messagebox.showinfo(
            "Rapport de consommation",
            f"Rapport de l'exercice {label} généré :\n{dest}",
            parent=self,
        )
