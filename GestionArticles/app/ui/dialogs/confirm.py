"""Dialogues de confirmation avant enregistrement d'un document."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import COLORS, FONT_FAMILY as FONT, TVA_RATE
from app.ui.common import money
from app.utils import compute_totals


def confirm_price_refresh(
    parent: tk.Misc,
    category: str,
    issues: list[tuple[dict, dict | None]],
) -> bool:
    win = tk.Toplevel(parent)
    win.title("Contrôle des prix de la commande")
    win.configure(bg=COLORS["bg"])
    win.geometry("760x460")
    win.transient(parent)
    win.grab_set()
    removed = sum(1 for _, current in issues if current is None)
    ttk.Label(
        win,
        text=(f"{len(issues)} ligne(s) du document ne correspondent plus à la liste active « {category} ».\n"
              "Mettez les prix à jour avant d'enregistrer."),
        background=COLORS["bg"], foreground=COLORS["danger"],
        font=(FONT, 10, "bold"), justify="left",
    ).pack(anchor="w", padx=14, pady=(14, 6))
    tree = ttk.Treeview(win, columns=("code", "designation", "old", "new"), show="headings")
    for c, h, w in (
        ("code", "N°", 80),
        ("designation", "Désignation", 330),
        ("old", "Prix commandé", 130),
        ("new", "Prix liste active", 140),
    ):
        tree.heading(c, text=h)
        tree.column(c, width=w, anchor="center" if c != "designation" else "w")
    tree.pack(fill="both", expand=True, padx=14, pady=(0, 8))
    for item, current in issues:
        tree.insert("", "end", values=(
            item["code"], item["designation"],
            f"{item['unit_price_ht']:.2f}",
            "—" if current is None else f"{current['unit_price_ht']:.2f}",
        ))
    if removed:
        ttk.Label(
            win,
            text=f"{removed} article(s) retiré(s) de la liste active seront supprimés du document.",
            background=COLORS["bg"], foreground=COLORS["muted"], font=(FONT, 9),
        ).pack(anchor="w", padx=14)
    result = {"ok": False}

    def confirm() -> None:
        result["ok"] = True
        win.destroy()

    actions = ttk.Frame(win)
    actions.pack(fill="x", padx=14, pady=14)
    ttk.Button(actions, text="Mettre à jour et continuer", style="Accent.TButton", command=confirm).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)
    return result["ok"]


def confirm_document(
    parent: tk.Misc,
    number: str,
    category: str,
    date_text: str,
    cart: list[dict],
    summary: dict,
) -> bool:
    """Récapitulatif avant enregistrement.

    Si le document atteint ou dépasse le plafond de l'exercice, la fenêtre
    n'offre aucune validation : le blocage est ferme (aucune justification).
    """
    total_ht, tva_amount, total_ttc = compute_totals(cart)
    win = tk.Toplevel(parent)
    win.title("Confirmation avant enregistrement")
    win.configure(bg=COLORS["bg"])
    win.geometry("880x620")
    win.transient(parent)
    win.grab_set()
    ttk.Label(win, text="Récapitulatif du document", style="Section.TLabel").pack(anchor="w", padx=14, pady=(14, 6))
    info = ttk.Frame(win)
    info.pack(fill="x", padx=14)
    ttk.Label(info, text=f"N° : {number}").pack(side="left")
    ttk.Label(info, text=f"Date : {date_text}").pack(side="left", padx=20)
    ttk.Label(info, text=f"Liste : {category}").pack(side="left")

    tree = ttk.Treeview(win, columns=("code", "designation", "unit", "price", "qty", "total"), show="headings")
    for c, h, w in (
        ("code", "N°", 60),
        ("designation", "Désignation", 300),
        ("unit", "Unité", 70),
        ("price", "Prix HT", 100),
        ("qty", "Qté", 60),
        ("total", "Total HT", 110),
    ):
        tree.heading(c, text=h)
        tree.column(c, width=w, anchor="center" if c != "designation" else "w")
    tree.pack(fill="both", expand=True, padx=14, pady=(10, 6))
    for row in cart:
        line = row["quantity"] * row["unit_price_ht"]
        tree.insert("", "end", values=(
            row["code"], row["designation"], row["unit"],
            f"{row['unit_price_ht']:.2f}", f"{row['quantity']:g}", f"{line:.2f}",
        ))

    totals = ttk.Frame(win)
    totals.pack(fill="x", padx=14)
    ttk.Label(totals, text=f"Total TTC : {money(total_ttc)}", style="Section.TLabel").pack(side="right", padx=12)
    ttk.Label(totals, text=f"TVA {TVA_RATE * 100:g}% : {money(tva_amount)}").pack(side="right", padx=12)
    ttk.Label(totals, text=f"Total HT : {money(total_ht)}").pack(side="right", padx=12)

    plafond = summary.get("plafond")
    label = summary.get("label")
    blocked = False
    if plafond is not None:
        projected = round(summary["consumed"] + total_ht, 2)
        remaining = round(plafond - projected, 2)
        # Blocage ferme : atteindre le plafond (égalité incluse) refuse
        # l'enregistrement, sans exception ni justification possible.
        blocked = projected >= round(float(plafond), 2)
        budget = ttk.Frame(win)
        budget.pack(fill="x", padx=14, pady=(10, 0))
        tk.Label(
            budget,
            text=(f"Exercice {label or '—'} — Plafond : {money(plafond)}   |   "
                  f"Consommé : {money(summary['consumed'])}   |   "
                  f"Après ce document : {money(projected)}   |   "
                  f"Reste : {money(remaining)}"),
            bg=COLORS["bg"], fg=COLORS["danger"] if blocked else COLORS["text"], font=(FONT, 9, "bold"),
        ).pack(anchor="w")
        if blocked:
            tk.Label(
                budget,
                text=(f"PLAFOND ATTEINT ({money(projected - plafond)} au-delà ou égalité) — "
                      "enregistrement impossible sur cette convention.\n"
                      "Aucune exception n'est prévue : retirez des lignes ou clôturez l'exercice."),
                bg=COLORS["bg"], fg=COLORS["danger"], font=(FONT, 9),
            ).pack(anchor="w")

    result = {"ok": False}

    def confirm() -> None:
        result["ok"] = True
        win.destroy()

    actions = ttk.Frame(win)
    actions.pack(fill="x", padx=14, pady=14)
    if blocked:
        ttk.Button(actions, text="Fermer", command=win.destroy).pack(side="right")
    else:
        ttk.Button(actions, text="Valider et enregistrer", style="Accent.TButton", command=confirm).pack(side="right")
        ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)
    return result["ok"]
