"""Écran « Tableau de bord » : synthèse des conventions et de leurs exercices.

Une carte par convention active : exercice courant (libellé + période), jauge
colorée, chiffres plafond/consommé/reste et état d'alerte. Un bouton ouvre
directement un nouveau document pour la convention.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import BUDGET_COLORS, COLORS, FONT_FAMILY as FONT
from app.database import Database
from app.ui.common import money


class DashboardView(ttk.Frame):
    """Synthèse des conventions et de leurs exercices actifs."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=16)
        self.app = app
        self.db: Database = app.db
        self._cards: dict[str, dict] = {}

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(0, weight=1)
        self.canvas = tk.Canvas(self, bg=COLORS["bg"], highlightthickness=0)
        self.canvas.grid(row=0, column=0, sticky="nsew")
        self.scroll = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.scroll.grid(row=0, column=1, sticky="ns")
        self.canvas.configure(yscrollcommand=self.scroll.set)
        self.inner = ttk.Frame(self.canvas)
        self._window = self.canvas.create_window((0, 0), window=self.inner, anchor="nw")
        self.inner.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.canvas.bind(
            "<Configure>",
            lambda e: self.canvas.itemconfigure(self._window, width=e.width),
        )

    def refresh(self) -> None:
        for child in self.inner.winfo_children():
            child.destroy()
        self._cards.clear()
        names = self.db.active_category_names()
        if not names:
            self._empty_state()
            return
        # Grille fluide : 2 colonnes, passage à 1 sur fenêtre étroite.
        for index, name in enumerate(names):
            card = self._make_card(name)
            card.grid(
                row=index // 2, column=index % 2,
                sticky="nsew", padx=(0 if index % 2 == 0 else 10, 0), pady=(0, 12),
            )
            self.inner.columnconfigure(index % 2, weight=1)

    def _empty_state(self) -> None:
        box = ttk.Frame(self.inner, style="Card.TFrame", padding=32)
        box.pack(expand=True)
        ttk.Label(
            box,
            text="Aucune convention active",
            style="Section.TLabel",
        ).pack(pady=(0, 6))
        ttk.Label(
            box,
            text="Ouvrez une convention et un exercice depuis l'écran « Conventions »\n"
                 "pour démarrer la saisie des commandes.",
            style="Muted.TLabel",
            justify="center",
        ).pack()

    def _make_card(self, name: str) -> ttk.Frame:
        exercice = self.db.get_active_exercice(name)
        card = ttk.Frame(self.inner, style="Card.TFrame", padding=(16, 14))
        card.configure(borderwidth=1, relief="solid")

        title = ttk.Label(card, text=name, style="Section.TLabel", font=(FONT, 13, "bold"))
        title.grid(row=0, column=0, sticky="w", columnspan=2)

        if exercice is None:
            sub = ttk.Label(
                card,
                text="Aucun exercice actif — ouvrez-en un.",
                style="Muted.TLabel",
            )
            sub.grid(row=1, column=0, sticky="w", columnspan=2, pady=(4, 12))
            btn = ttk.Button(
                card, text="Gérer les exercices",
                command=lambda n=name: self._go_conventions(n),
            )
            btn.grid(row=2, column=0, sticky="w")
        else:
            label = exercice["label"]
            period = f"{exercice['start_date']} → {exercice['end_date']}"
            sub = ttk.Label(card, text=f"Exercice {label}", style="Muted.TLabel")
            sub.grid(row=1, column=0, sticky="w")
            period_lbl = ttk.Label(card, text=period, style="Muted.TLabel")
            period_lbl.grid(row=1, column=1, sticky="e", padx=(8, 0))

            summary = self.db.exercice_summary(name, label)
            gauge = ttk.Progressbar(
                card, maximum=100.0, style="BudgetOk.Horizontal.TProgressbar",
            )
            gauge.grid(row=2, column=0, columnspan=2, sticky="ew", pady=(12, 6))
            self._apply_gauge(gauge, summary)

            plafond = summary["plafond"]
            if plafond is None:
                line1 = "Plafond : illimité"
                line2 = f"Consommé : {money(summary['consumed'])}"
                line3 = ""
            else:
                line1 = f"Plafond : {money(plafond)}"
                line2 = f"Consommé : {money(summary['consumed'])}"
                line3 = f"Reste : {money(summary['remaining'])}"
            numbers = tk.Frame(card, bg=COLORS["card"])
            numbers.grid(row=3, column=0, columnspan=2, sticky="w", pady=(2, 0))
            ttk.Label(numbers, text=line1, style="Muted.TLabel").pack(anchor="w")
            ttk.Label(numbers, text=line2, style="Muted.TLabel").pack(anchor="w")
            if line3:
                ttk.Label(numbers, text=line3, style="Muted.TLabel").pack(anchor="w")

            state_text, state_color = self._state_label(summary)
            badge = tk.Label(
                card, text=state_text, bg=COLORS["card"], fg=state_color,
                font=(FONT, 9, "bold"),
            )
            badge.grid(row=4, column=0, sticky="w", pady=(10, 0))
            btn = ttk.Button(
                card, text="Nouveau document",
                style="Accent.TButton",
                command=lambda n=name: self._new_document(n),
            )
            btn.grid(row=4, column=1, sticky="e", pady=(10, 0))

            self._cards[name] = {"gauge": gauge, "summary": summary, "badge": badge}

        return card

    @staticmethod
    def _state_label(summary: dict) -> tuple[str, str]:
        state = summary.get("state", "none")
        if state == "over":
            return "Plafond atteint", BUDGET_COLORS["over"]
        if state == "critical":
            return "≥ 90 % consommé", BUDGET_COLORS["critical"]
        if state == "warn":
            return "≥ 80 % consommé", BUDGET_COLORS["warn"]
        if state == "ok":
            return "Sous contrôle", BUDGET_COLORS["ok"]
        return "Sans plafond", BUDGET_COLORS["none"]

    @staticmethod
    def _apply_gauge(gauge: ttk.Progressbar, summary: dict) -> None:
        plafond = summary["plafond"]
        if plafond is None:
            gauge.configure(value=0.0, style="BudgetOk.Horizontal.TProgressbar")
            return
        rate = summary["rate"] or 0.0
        percent = max(0.0, min(100.0, rate * 100))
        level = {
            "over": "BudgetOver",
            "critical": "BudgetCritical",
            "warn": "BudgetWarn",
        }.get(summary.get("state", "ok"), "BudgetOk")
        gauge.configure(value=percent, style=f"{level}.Horizontal.TProgressbar")

    # -------------------------------------------------------------- navigation

    def _new_document(self, name: str) -> None:
        self.app.open_document_for(name)

    def _go_conventions(self, name: str) -> None:
        self.app.show_screen("conventions")
        self.app.conventions.select_convention(name)
