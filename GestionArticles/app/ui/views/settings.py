"""Écran « Paramètres » : thème, taux de TVA et à propos."""
from __future__ import annotations

import tkinter as tk
from tkinter import messagebox, ttk

from app.config import (
    APP_NAME,
    TVA_RATE,
)
from app.ui.theme import theme_label, theme_names


class SettingsView(ttk.Frame):
    """Réglages de l'application (thème principalement)."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=24)
        self.app = app
        self.theme_var = tk.StringVar()

    def build(self) -> None:
        self.columnconfigure(0, weight=1)

        # --- thème
        ttk.Label(self, text="Apparence", style="Section.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )
        box = ttk.Frame(self, style="Card.TFrame", padding=16)
        box.grid(row=1, column=0, sticky="ew")
        box.columnconfigure(0, weight=1)
        self.theme_var.set(self.app.current_theme_name())
        for name in theme_names():
            ttk.Radiobutton(
                box,
                text=theme_label(name),
                value=name,
                variable=self.theme_var,
                command=lambda choice=name: self.app.set_theme(choice),
            ).grid(sticky="w", pady=3)
        ttk.Label(
            box,
            text="Le thème s'applique immédiatement. Le mode sombre est accessible\n"
                 "en un clic depuis la barre latérale.",
            style="Muted.TLabel",
        ).grid(sticky="w", pady=(10, 0))

        # --- TVA
        ttk.Label(self, text="Fiscalité", style="Section.TLabel").grid(
            row=2, column=0, sticky="w", pady=(20, 8)
        )
        tva_box = ttk.Frame(self, style="Card.TFrame", padding=16)
        tva_box.grid(row=3, column=0, sticky="ew")
        ttk.Label(tva_box, text=f"Taux de TVA appliqué : {TVA_RATE * 100:g} %").pack(
            anchor="w"
        )
        ttk.Label(
            tva_box,
            text="Ce taux s'applique à toutes les conventions. Il se modifie dans "
                 "le code (app/config.py, constante TVA_RATE).",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(4, 0))

        # --- à propos
        ttk.Label(self, text="À propos", style="Section.TLabel").grid(
            row=4, column=0, sticky="w", pady=(20, 8)
        )
        about_box = ttk.Frame(self, style="Card.TFrame", padding=16)
        about_box.grid(row=5, column=0, sticky="ew")
        ttk.Label(about_box, text=APP_NAME).pack(anchor="w")
        ttk.Label(
            about_box,
            text="Gestion hors ligne des conventions, de leurs exercices et de "
                 "leurs commandes d'articles.",
            style="Muted.TLabel",
        ).pack(anchor="w", pady=(2, 0))
        ttk.Button(
            about_box,
            text="À propos",
            command=lambda: messagebox.showinfo(
                APP_NAME,
                "Gestion des conventions et de leurs commandes d'articles.\n"
                "Application hors ligne — aucune connexion Internet requise.",
                parent=self,
            ),
        ).pack(anchor="w", pady=(10, 0))
