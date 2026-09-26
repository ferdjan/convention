"""Dialogue de consultation du détail des lignes d'un document."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import COLORS, TVA_RATE
from app.database import Database
from app.ui.common import money


def show_document_items(parent: tk.Misc, db: Database, document_id: int) -> None:
    rows = db.document_items(document_id)
    doc = db.get_document(document_id)
    win = tk.Toplevel(parent)
    win.title("Détail du document")
    win.configure(bg=COLORS["bg"])
    win.geometry("900x480")
    tree = ttk.Treeview(win, columns=("code", "designation", "unit", "price", "qty", "total"), show="headings")
    for c, h, w in [
        ("code", "N°", 80), ("designation", "Désignation", 420), ("unit", "Unité", 100),
        ("price", "Prix HT", 100), ("qty", "Quantité", 90), ("total", "Total HT", 120),
    ]:
        tree.heading(c, text=h)
        tree.column(c, width=w)
    tree.pack(fill="both", expand=True, padx=10, pady=(10, 4))
    for r in rows:
        tree.insert(
            "", "end",
            values=(
                r["code"], r["designation"], r["unit"],
                f"{r['unit_price_ht']:.2f}", f"{r['quantity']:g}", f"{r['total_ht']:.2f}",
            ),
        )
    if doc:
        rate = TVA_RATE if doc["tva_rate"] is None else doc["tva_rate"]
        summary = ttk.Frame(win)
        summary.pack(fill="x", padx=10, pady=(0, 10))
        ttk.Label(summary, text=f"TOTAL HT : {money(doc['total_ht'])}").pack(side="right", padx=(12, 0))
        ttk.Label(summary, text=f"TVA {rate * 100:g}% : {money(doc['tva_amount'] or 0)}").pack(side="right", padx=(12, 0))
        ttk.Label(
            summary, text=f"TOTAL TTC : {money(doc['total_ttc'] or 0)}", style="Section.TLabel",
        ).pack(side="right", padx=(12, 0))
