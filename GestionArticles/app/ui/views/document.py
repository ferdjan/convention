"""Onglet « Nouveau document » : sélection d'articles, panier et exercice.

Cette vue possède son propre état (variables Tk, panier, articles visibles) et
n'accède à la base que via l'objet ``app`` qui l'a créée. Le budget annuel est
remplacé par le suivi de l'exercice courant de la convention (période +
plafond). Le blocage à 100 % est ferme : le bouton d'enregistrement se
désactive quand « consommé + ce document » atteint le plafond.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk
from uuid import uuid4

from app.config import (
    BUDGET_COLORS,
    BUDGET_CRITICAL,
    BUDGET_WARN,
    COLORS,
    EXPORT_DIR,
    FONT_FAMILY as FONT,
    TVA_RATE,
)
from app.database import Database
from app.reports.excel import build_excel
from app.reports.pdf import build_pdf
from app.ui.common import money
from app.ui.dialogs import (
    confirm_document,
    confirm_price_refresh,
)
from app.utils import compute_totals, parse_quantity


class DocumentView(ttk.Frame):
    """Saisie d'un document : recherche, panier, exercice et enregistrement."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=(16, 14, 16, 6))
        self.app = app
        self.db: Database = app.db
        self.cart: list[dict] = []
        self.cart_category: str | None = None
        self.current_exercice: dict | None = None

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        """Trois bandes : identité + exercice, deux arbres, puis synthèse et actions."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)
        self.cart_count_var = tk.StringVar(value="Aucune ligne")

        # --- bandeau supérieur : identité du document et exercice, côte à côte
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(0, weight=3, minsize=430)
        top.columnconfigure(1, weight=4)

        meta = ttk.LabelFrame(top, text="Document", padding=10)
        meta.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        meta.columnconfigure(1, weight=1)
        meta.columnconfigure(3, weight=1)
        ttk.Label(meta, text="N°").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.number_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.number_var, state="readonly").grid(row=0, column=1, sticky="ew")
        ttk.Label(meta, text="Date").grid(row=0, column=2, sticky="w", padx=(20, 8))
        self.date_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.date_var, state="readonly").grid(row=0, column=3, sticky="ew")
        ttk.Label(meta, text="Liste").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=(12, 0))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(meta, textvariable=self.category_var, state="readonly")
        self.category_combo.grid(row=1, column=1, columnspan=3, sticky="ew", pady=(12, 0))
        self.category_combo.bind("<<ComboboxSelected>>", self.on_category_change)
        self.category_status_var = tk.StringVar(value="")
        self.category_status_label = tk.Label(
            meta, textvariable=self.category_status_var,
            bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT, 9, "bold"),
        )
        self.category_status_label.grid(row=1, column=4, sticky="w", padx=(20, 0), pady=(12, 0))
        meta.columnconfigure(4, weight=0)

        # --- jauge de l'exercice courant
        budget = ttk.LabelFrame(top, text="Exercice et plafond", padding=10)
        budget.grid(row=0, column=1, sticky="nsew")
        self.exercice_info_var = tk.StringVar(value="—")
        self.budget_plafond_var = tk.StringVar(value="—")
        self.budget_consomme_var = tk.StringVar(value="—")
        self.budget_encours_var = tk.StringVar(value="—")
        self.budget_reste_var = tk.StringVar(value="—")
        self.budget_rate_var = tk.DoubleVar(value=0.0)
        self.budget_bar = ttk.Progressbar(
            budget, variable=self.budget_rate_var, maximum=100.0,
            style="BudgetOk.Horizontal.TProgressbar",
        )
        self.budget_bar.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(
            budget, textvariable=self.exercice_info_var, style="Muted.TLabel",
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self._budget_cells: dict[str, tk.Label] = {}
        metrics = (
            ("plafond", "Plafond"),
            ("consomme", "Consommé"),
            ("encours", "Ce document"),
            ("reste", "Reste dispo."),
        )
        for index, (key, label) in enumerate(metrics):
            row = 2 + index // 2
            col = (index % 2) * 2
            ttk.Label(budget, text=label, style="Muted.TLabel").grid(
                row=row, column=col, sticky="w", padx=(0 if index % 2 == 0 else 28, 6), pady=(4, 0),
            )
            value_label = tk.Label(
                budget,
                textvariable=getattr(self, f"budget_{key}_var"),
                bg=COLORS["bg"], fg=COLORS["text"], font=(FONT, 10, "bold"),
            )
            value_label.grid(row=row, column=col + 1, sticky="w", pady=(4, 0))
            self._budget_cells[key] = value_label
        self.budget_alert_var = tk.StringVar(value="")
        self.budget_alert_label = tk.Label(
            budget, textvariable=self.budget_alert_var,
            bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT, 9),
        )
        self.budget_alert_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        # --- zone de travail : catalogue à gauche, panier à droite
        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        select = ttk.LabelFrame(panes, text="Catalogue des articles", padding=12)
        select.columnconfigure(0, weight=1)
        # Barre unique : recherche (largeur réduite) + quantité + ajout.
        bar = ttk.Frame(select)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Recherche :").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_entry = search = ttk.Entry(bar, textvariable=self.search_var, font=(FONT, 11))
        search.grid(row=0, column=1, sticky="ew", padx=(6, 14), ipady=3)
        # Rafraîchit la liste uniquement quand le TEXTE change (pas sur les flèches) :
        # sinon les flèches haut/bas réinitialiseraient la sélection au 1er résultat.
        self.search_var.trace_add("write", lambda *_a: self.refresh_articles())
        search.bind("<Down>", lambda e: self.move_article_selection(1))
        search.bind("<Up>", lambda e: self.move_article_selection(-1))
        search.bind("<Return>", lambda e: self.add_selected())
        ttk.Label(bar, text="Quantité :").grid(row=0, column=2, sticky="e")
        self.qty_var = tk.StringVar(value="1")
        ttk.Spinbox(
            bar, from_=0.01, to=999999, increment=1, textvariable=self.qty_var, width=5
        ).grid(row=0, column=3, padx=(6, 12))
        ttk.Button(
            bar, text="Ajouter", style="Accent.TButton", command=self.add_selected
        ).grid(row=0, column=4)

        cols = ("code", "designation", "unit", "price")
        tree_wrap = ttk.Frame(select)
        tree_wrap.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        self.article_tree = ttk.Treeview(tree_wrap, columns=cols, show="headings", selectmode="browse")
        headers = {"code": "N°", "designation": "Désignation", "unit": "Unité", "price": "Prix unitaire HT"}
        widths = {"code": 80, "designation": 320, "unit": 95, "price": 150}
        for c in cols:
            self.article_tree.heading(c, text=headers[c])
            self.article_tree.column(
                c, width=widths[c], minwidth=60, stretch=(c == "designation"),
                anchor="w" if c == "designation" else "center",
            )
        self.article_tree.grid(row=0, column=0, sticky="nsew")
        self.article_tree.bind("<Double-1>", lambda e: self.add_selected())
        self.article_tree.bind("<<TreeviewSelect>>", self.on_article_select)
        avs = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.article_tree.yview)
        avs.grid(row=0, column=1, sticky="ns")
        ahs = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.article_tree.xview)
        ahs.grid(row=1, column=0, sticky="ew")
        self.article_tree.configure(yscrollcommand=avs.set, xscrollcommand=ahs.set)
        select.rowconfigure(1, weight=1)
        panes.add(select, weight=1)

        cartf = ttk.LabelFrame(panes, text="Articles du document", padding=12)
        ttk.Label(cartf, textvariable=self.cart_count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8),
        )
        tree_wrap = ttk.Frame(cartf)
        tree_wrap.grid(row=1, column=0, sticky="nsew")
        ccols = ("code", "designation", "unit", "price", "qty", "total")
        self.cart_tree = ttk.Treeview(tree_wrap, columns=ccols, show="headings")
        h2 = {"code": "N°", "designation": "Désignation", "unit": "Unité", "price": "Prix HT", "qty": "Qté", "total": "Total HT"}
        w2 = {"code": 70, "designation": 240, "unit": 80, "price": 115, "qty": 70, "total": 125}
        for c in ccols:
            self.cart_tree.heading(c, text=h2[c])
            self.cart_tree.column(
                c, width=w2[c], minwidth=50, stretch=(c == "designation"),
                anchor="w" if c == "designation" else "center",
            )
        self.cart_tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.cart_tree.yview)
        vs.grid(row=0, column=1, sticky="ns")
        hs = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.cart_tree.xview)
        hs.grid(row=1, column=0, sticky="ew")
        self.cart_tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        cartf.rowconfigure(1, weight=1)
        cartf.columnconfigure(0, weight=1)
        self.cart_tree.bind("<Delete>", lambda e: self.remove_selected())
        panes.add(cartf, weight=1)

        # --- pied de page : actions secondaires + enregistrement (ligne 1),
        # --- pied de page : une seule barre d'actions.
        #     À gauche les actions secondaires ; à droite les totaux puis le
        #     bouton d'enregistrement (montant -> action d'un seul geste).
        footer = ttk.Frame(self)
        footer.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        footer.columnconfigure(1, weight=1)
        secondary = ttk.Frame(footer)
        secondary.grid(row=0, column=0, sticky="w")
        ttk.Button(secondary, text="Nouveau document", command=self.new_document).pack(side="left")
        ttk.Button(secondary, text="Retirer la ligne", command=self.remove_selected).pack(side="left", padx=(10, 0))
        ttk.Button(secondary, text="Vider le document", command=self.clear_cart).pack(side="left", padx=(10, 0))

        right = ttk.Frame(footer)
        right.grid(row=0, column=2, sticky="e")
        totals = tk.Frame(
            right, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1,
        )
        totals.pack(side="left")
        self.total_var = tk.StringVar(value="0.00 DA")
        self.tva_var = tk.StringVar(value="0.00 DA")
        self.ttc_var = tk.StringVar(value="0.00 DA")
        # Synthèse sur deux lignes : (Total HT + TVA) puis TOTAL TTC.
        ttk.Label(totals, text="Total HT", style="TotalLabel.TLabel").grid(
            row=0, column=0, sticky="w", padx=(16, 6), pady=(8, 2)
        )
        ttk.Label(totals, textvariable=self.total_var, style="TotalValue.TLabel").grid(
            row=0, column=1, sticky="w", padx=(0, 28), pady=(8, 2)
        )
        ttk.Label(totals, text=f"TVA {TVA_RATE * 100:g}%", style="TotalLabel.TLabel").grid(
            row=0, column=2, sticky="w", padx=(0, 6), pady=(8, 2)
        )
        ttk.Label(totals, textvariable=self.tva_var, style="TotalValue.TLabel").grid(
            row=0, column=3, sticky="w", padx=(0, 16), pady=(8, 2)
        )
        ttk.Label(totals, text="TOTAL TTC", style="TotalTTCLabel.TLabel").grid(
            row=1, column=0, columnspan=2, sticky="w", padx=(16, 6), pady=(2, 8)
        )
        ttk.Label(totals, textvariable=self.ttc_var, style="TotalTTCValue.TLabel").grid(
            row=1, column=2, columnspan=2, sticky="e", padx=(0, 16), pady=(2, 8)
        )
        self.save_button = ttk.Button(
            right, text="Enregistrer et générer PDF + Excel",
            style="Accent.TButton", command=self.save_document,
        )
        self.save_button.pack(side="left", padx=(12, 0))

    # -------------------------------------------------------------- catégories

    def load_categories(self) -> None:
        names = self.db.active_category_names()
        visible = list(names)
        if self.cart and self.cart_category and self.cart_category not in visible:
            visible.append(self.cart_category)
        self.category_combo.configure(values=visible)
        if self.category_var.get() not in visible:
            self.category_var.set(visible[0] if visible else "")
        self.refresh_category_status()

    def refresh_category_status(self) -> None:
        if not hasattr(self, "category_status_var"):
            return
        name = self.category_var.get().strip()
        if not name:
            self.category_status_var.set("")
            return
        status, _ = self.db.category_status(name)
        labels = {"active": "Active", "closed": "Clôturée", "expiree": "Expirée"}
        colors = {
            "active": BUDGET_COLORS["ok"],
            "closed": BUDGET_COLORS["critical"],
            "expiree": BUDGET_COLORS["over"],
        }
        self.category_status_var.set("Convention : " + labels.get(status, status))
        self.category_status_label.configure(fg=colors.get(status, COLORS["muted"]))

    def ensure_active_category(self, category: str) -> bool:
        status, _ = self.db.category_status(category)
        if status != "active":
            reason = {
                "closed": "est clôturée",
                "expiree": "est expirée (échéance dépassée)",
            }.get(status, "n'est pas active")
            messagebox.showwarning(
                "Convention",
                f"La convention « {category} » {reason}.\n"
                "Aucun document ne peut y être ajouté.",
            )
            return False
        return True

    # -------------------------------------------------------------- document

    def current_exercice_label(self) -> str | None:
        if self.current_exercice:
            return self.current_exercice["label"]
        return None

    def next_free_document_number(self, category: str) -> str:
        label = self.current_exercice_label()
        number = self.db.next_document_number(category or None, label)
        seen: set[str] = set()
        while number not in seen:
            seen.add(number)
            if not (
                (EXPORT_DIR / f"{number}.pdf").exists()
                or (EXPORT_DIR / f"{number}.xlsx").exists()
            ):
                return number
            prefix, separator, sequence = number.rpartition("-")
            if not separator or not sequence.isdigit():
                break
            number = f"{prefix}-{int(sequence) + 1:04d}"
        raise ValueError("Impossible de générer un numéro de document libre.")

    def new_document(self) -> None:
        self.date_var.set(datetime.now().strftime("%d/%m/%Y"))
        names = self.db.active_category_names()
        if self.category_var.get() not in names:
            self.category_var.set(names[0] if names else "")
        self.current_exercice = self._load_exercice(self.category_var.get())
        self.number_var.set(self.next_free_document_number(self.category_var.get() or None))
        self.search_var.set("")
        self.qty_var.set("1")
        self.cart = []
        self.cart_category = None
        self.refresh_articles()
        self.refresh_cart()

    def _load_exercice(self, category: str) -> dict | None:
        if not category:
            return None
        row = self.db.get_active_exercice(category)
        if not row:
            return None
        return {
            "label": row["label"],
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "plafond": row["plafond"],
        }

    def on_category_change(self, _event=None) -> None:
        category = self.category_var.get().strip()
        if self.cart and category != self.cart_category:
            messagebox.showwarning(
                "Liste verrouillée",
                "Videz le document en cours avant de changer de liste.",
                parent=self.app,
            )
            self.category_var.set(self.cart_category or "")
            self.current_exercice = self._load_exercice(self.category_var.get())
            self.refresh_articles()
            self.refresh_budget_panel()
            self.refresh_category_status()
            return
        self.current_exercice = self._load_exercice(category)
        self.number_var.set(self.next_free_document_number(category or None))
        self.refresh_articles()
        self.refresh_budget_panel()
        self.refresh_category_status()
        self.maybe_warn_budget()

    # --------------------------------------------------------------- articles

    def refresh_articles(self) -> None:
        for item in self.article_tree.get_children():
            self.article_tree.delete(item)
        category = self.category_var.get().strip()
        for row in self.db.search_articles(category, self.search_var.get()):
            self.article_tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["code"], row["designation"], row["unit"] or "—",
                    money(float(row["unit_price_ht"])),
                ),
            )
        # Pointe le curseur sur le premier résultat pour permettre la
        # navigation immédiate avec les flèches haut/bas.
        children = self.article_tree.get_children()
        if children:
            first = children[0]
            self.article_tree.selection_set(first)
            self.article_tree.focus(first)
            self.article_tree.see(first)
            self.qty_var.set("1")

    def on_article_select(self, _event=None) -> None:
        self.qty_var.set("1")

    def move_article_selection(self, delta: int):
        items = self.article_tree.get_children()
        if not items:
            return "break"
        sel = self.article_tree.selection()
        if sel:
            idx = max(0, min(len(items) - 1, items.index(sel[0]) + delta))
        else:
            idx = 0 if delta > 0 else len(items) - 1
        iid = items[idx]
        self.article_tree.selection_set(iid)
        self.article_tree.focus(iid)
        self.article_tree.see(iid)
        return "break"

    def add_selected(self) -> None:
        category = self.category_var.get().strip()
        if category and not self.ensure_active_category(category):
            return
        if not self.current_exercice:
            messagebox.showwarning(
                "Exercice",
                f"La convention « {category} » n'a pas d'exercice actif.\n"
                "Ouvrez un exercice via Fichier → Conventions (exercices, plafonds)...",
            )
            return
        sel = self.article_tree.selection()
        if not sel:
            messagebox.showwarning("Article", "Sélectionnez un article.")
            return
        try:
            qty = parse_quantity(self.qty_var.get())
        except (TypeError, ValueError):
            messagebox.showwarning("Quantité", "Saisissez une quantité supérieure à zéro.")
            return
        if self.cart and category != self.cart_category:
            messagebox.showwarning(
                "Liste verrouillée",
                "Videz le document en cours avant de changer de liste.",
                parent=self.app,
            )
            return
        aid = int(sel[0])
        rows = self.db.search_articles(self.category_var.get(), self.search_var.get())
        row = next((r for r in rows if int(r["id"]) == aid), None)
        if row is None:
            return
        existing = next((i for i in self.cart if i["article_id"] == aid), None)
        if existing:
            existing["quantity"] += qty
        else:
            if not self.cart:
                self.cart_category = category
            self.cart.append({
                "article_id": aid,
                "category": category,
                "code": row["code"],
                "designation": row["designation"],
                "unit": str(row["unit"] or ""),
                "unit_price_ht": float(row["unit_price_ht"]),
                "quantity": qty,
            })
        self.refresh_cart()
        self.qty_var.set("1")
        self.search_entry.focus_set()

    # ----------------------------------------------------------------- panier

    def refresh_cart(self) -> None:
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        for idx, row in enumerate(self.cart):
            line = row["quantity"] * row["unit_price_ht"]
            self.cart_tree.insert(
                "", "end", iid=str(idx),
                values=(
                    row["code"], row["designation"], row["unit"] or "—",
                    money(row["unit_price_ht"]), f"{row['quantity']:g}", money(line),
                ),
            )
        total_ht, tva_amount, total_ttc = compute_totals(self.cart)
        self.total_var.set(money(total_ht))
        self.tva_var.set(money(tva_amount))
        self.ttc_var.set(money(total_ttc))
        if self.cart:
            units = sum(row["quantity"] for row in self.cart)
            plural = "s" if len(self.cart) > 1 else ""
            self.cart_count_var.set(
                f"{len(self.cart)} ligne{plural}  ·  {units:g} article{plural}  ·  {money(total_ht)} HT",
            )
        else:
            self.cart_count_var.set("Aucune ligne")
        self.refresh_budget_panel()

    def remove_selected(self) -> None:
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.cart.pop(idx)
        if not self.cart:
            self.cart_category = None
            self.current_exercice = self._load_exercice(self.category_var.get())
            self.number_var.set(self.next_free_document_number(self.category_var.get() or None))
        self.refresh_cart()

    def clear_cart(self) -> None:
        if self.cart and not messagebox.askyesno("Vider", "Supprimer toutes les lignes du document ?"):
            return
        self.cart = []
        self.cart_category = None
        self.current_exercice = self._load_exercice(self.category_var.get())
        self.number_var.set(self.next_free_document_number(self.category_var.get() or None))
        self.refresh_cart()

    # ----------------------------------------------------------------- budget

    def set_budget_alert(self, color: str, text: str) -> None:
        self.budget_alert_var.set(text)
        self.budget_alert_label.configure(fg=color)

    def set_budget_gauge(self, percent: float, level: str) -> None:
        """Positionne la jauge et sa couleur (ok / warn / critical / over)."""
        self.budget_rate_var.set(max(0.0, min(100.0, percent)))
        self.budget_bar.configure(style=f"Budget{level}.Horizontal.TProgressbar")

    def refresh_budget_panel(self) -> None:
        if not hasattr(self, "budget_plafond_var"):
            return
        category = self.category_var.get().strip()
        entry_total = compute_totals(self.cart)[0] if self.cart else 0.0
        if not category:
            for var in (
                self.budget_plafond_var, self.budget_consomme_var,
                self.budget_encours_var, self.budget_reste_var,
            ):
                var.set("—")
            self.exercice_info_var.set("—")
            self.set_budget_gauge(0.0, "Ok")
            self.set_budget_alert(BUDGET_COLORS["none"], "")
            self._set_save_enabled(False)
            return

        if not self.current_exercice:
            self.current_exercice = self._load_exercice(category)
        exercice = self.current_exercice
        if not exercice:
            for var in (
                self.budget_plafond_var, self.budget_consomme_var,
                self.budget_encours_var, self.budget_reste_var,
            ):
                var.set("—")
            self.exercice_info_var.set(
                "Aucun exercice actif — ouvrez-en un via Fichier → Conventions..."
            )
            self.set_budget_gauge(0.0, "Ok")
            self.set_budget_alert(BUDGET_COLORS["none"], "")
            self._set_save_enabled(False)
            return

        label = exercice["label"]
        self.exercice_info_var.set(
            f"Exercice {label}  ·  du {exercice['start_date']} au {exercice['end_date']}"
        )
        summary = self.db.exercice_summary(category, label)
        plafond = summary["plafond"]
        consumed = summary["consumed"]
        self.budget_consomme_var.set(money(consumed))
        self.budget_encours_var.set(money(entry_total))

        if plafond is None:
            self.budget_plafond_var.set("illimité")
            self.budget_reste_var.set("—")
            for key in ("plafond", "reste"):
                self._budget_cells[key].configure(fg=BUDGET_COLORS["none"])
            self.set_budget_gauge(0.0, "Ok")
            self.set_budget_alert(
                BUDGET_COLORS["none"],
                "Exercice sans plafond : aucune limite de consommation.",
            )
            self._set_save_enabled(bool(self.cart))
            return

        projected = round(consumed + entry_total, 2)
        remaining = round(plafond - projected, 2)
        rate = projected / plafond if plafond else 0.0
        self.budget_plafond_var.set(money(plafond))
        self.budget_reste_var.set(money(remaining))
        # Blocage ferme : l'égalité exacte avec le plafond bloque aussi.
        blocked = projected >= round(float(plafond), 2)
        if blocked:
            color = BUDGET_COLORS["over"]
            level = "Over"
            if projected > plafond + 0.005:
                state = (
                    f"DÉPASSEMENT de {money(projected - plafond)} — "
                    "enregistrement bloqué (plafond de l'exercice)."
                )
            else:
                state = "PLAFOND ATTEINT — enregistrement bloqué (plafond de l'exercice)."
        elif rate >= BUDGET_CRITICAL:
            color = BUDGET_COLORS["critical"]
            level = "Critical"
            state = f"{rate * 100:.0f} % du plafond de l'exercice — proche de la limite."
        elif rate >= BUDGET_WARN:
            color = BUDGET_COLORS["warn"]
            level = "Warn"
            state = f"{rate * 100:.0f} % du plafond de l'exercice consommé."
        else:
            color = BUDGET_COLORS["ok"]
            level = "Ok"
            state = f"{rate * 100:.0f} % du plafond de l'exercice consommé."

        for key in ("plafond", "consomme", "encours"):
            self._budget_cells[key].configure(fg=COLORS["text"])
        self._budget_cells["reste"].configure(fg=color)
        self.set_budget_gauge(rate * 100, level)
        self.set_budget_alert(color, state)
        # Le bouton d'enregistrement se désactive au plafond (blocage ferme).
        self._set_save_enabled(bool(self.cart) and not blocked)

    def _set_save_enabled(self, enabled: bool) -> None:
        if hasattr(self, "save_button"):
            state = "normal" if enabled else "disabled"
            try:
                self.save_button.configure(state=state)
            except tk.TclError:
                pass

    def maybe_warn_budget(self) -> None:
        category = self.category_var.get().strip()
        if not category or not self.current_exercice:
            return
        summary = self.db.exercice_summary(category, self.current_exercice["label"])
        plafond = summary["plafond"]
        if plafond is None:
            return
        consumed = summary["consumed"]
        if consumed >= plafond - 0.005:
            messagebox.showwarning(
                "Plafond atteint",
                f"La convention « {category} » a déjà consommé {money(consumed)} "
                f"sur un plafond de {money(plafond)} (exercice {self.current_exercice['label']}).\n"
                "Aucun nouveau document ne peut être enregistré.",
            )
        elif consumed >= plafond * BUDGET_CRITICAL:
            messagebox.showinfo(
                "Plafond presque atteint",
                f"La convention « {category} » a consommé {consumed / plafond * 100:.0f} % "
                f"de son plafond d'exercice.\n\nConsommé : {money(consumed)}\n"
                f"Plafond : {money(plafond)}",
            )

    # -------------------------------------------------------- contrôle prix

    def ensure_cart_prices(self) -> bool:
        category = self.category_var.get()
        article_map = self.db.article_map(category)
        issues: list[tuple[dict, dict | None]] = []
        refreshed = False
        for item in self.cart:
            current = article_map.get((item["code"], item["designation"], item["unit"]))
            if current is not None and current["id"] != item["article_id"]:
                item["article_id"] = current["id"]
                refreshed = True
            if current is None or abs(
                current["unit_price_ht"] - float(item["unit_price_ht"])
            ) > 0.0001:
                issues.append((item, current))
        if not issues:
            if refreshed:
                self.refresh_cart()
            return True
        if not confirm_price_refresh(self.app, category, issues):
            return False
        for item, current in issues:
            if current is None:
                self.cart.remove(item)
            else:
                item["article_id"] = current["id"]
                item["unit_price_ht"] = float(current["unit_price_ht"])
        if not self.cart:
            self.cart_category = None
        self.refresh_cart()
        return bool(self.cart)

    # ----------------------------------------------------------- enregistrement

    def save_document(self) -> None:
        if not self.cart:
            messagebox.showwarning("Document", "Ajoutez au moins un article.")
            return
        if not self.ensure_active_category(self.category_var.get().strip()):
            return
        if not self.ensure_cart_prices():
            return
        if not self.cart:
            messagebox.showwarning("Document", "Aucune ligne valide à enregistrer.")
            return
        category = (self.cart_category or self.category_var.get()).strip()
        self.category_var.set(category)
        if not self.current_exercice:
            self.current_exercice = self._load_exercice(category)
        if not self.current_exercice:
            messagebox.showwarning(
                "Exercice",
                f"La convention « {category} » n'a pas d'exercice actif.\n"
                "Ouvrez un exercice via Fichier → Conventions (exercices, plafonds)...",
            )
            return
        label = self.current_exercice["label"]
        number = self.next_free_document_number(category or None)
        self.number_var.set(number)
        summary = self.db.exercice_summary(category, label)
        total_ht = compute_totals(self.cart)[0]
        # Blocage ferme côté interface (défense en profondeur avec la base).
        if summary["plafond"] is not None and round(
            summary["consumed"] + total_ht, 2
        ) >= round(float(summary["plafond"]), 2):
            messagebox.showerror(
                "Plafond atteint",
                "L'enregistrement est bloqué : ce document atteint ou dépasse le "
                f"plafond de l'exercice {label} de la convention « {category} ».\n\n"
                f"Consommé : {money(summary['consumed'])}\n"
                f"Ce document : {money(total_ht)}\n"
                f"Plafond : {money(summary['plafond'])}\n\n"
                "Aucune exception n'est possible : retirez des lignes ou ouvrez "
                "un nouvel exercice.",
            )
            return
        if not confirm_document(self.app, number, category, self.date_var.get(), self.cart, summary):
            return
        created_at = datetime.now().isoformat(timespec="seconds")
        total_ht, tva, ttc = compute_totals(self.cart)
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        pdf_path = EXPORT_DIR / f"{number}.pdf"
        excel_path = EXPORT_DIR / f"{number}.xlsx"
        temp_dir = EXPORT_DIR / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        temp_paths = [
            temp_dir / f"{number}.{token}.pdf",
            temp_dir / f"{number}.{token}.xlsx",
        ]
        created_paths: list[Path] = []
        try:
            if pdf_path.exists() or excel_path.exists():
                raise FileExistsError(
                    "Un fichier porte déjà ce numéro de document. Vérifiez le dossier d'export."
                )
            build_pdf(
                temp_paths[0], number, self.date_var.get(), category,
                self.cart, total_ht, TVA_RATE, tva, ttc,
            )
            build_excel(
                temp_paths[1], number, self.date_var.get(), category,
                self.cart, total_ht, TVA_RATE, tva, ttc,
            )
            if self.db.document_number_exists(number):
                raise ValueError(f"Le numéro de document {number} existe déjà.")
            for temporary, destination in zip(temp_paths, (pdf_path, excel_path)):
                temporary.replace(destination)
                created_paths.append(destination)
            doc_id, total, tva, ttc = self.db.save_document(
                number, created_at, category, self.cart,
                exercice_label=label,
                pdf_path=str(pdf_path), excel_path=str(excel_path),
            )
        except Exception as exc:
            for path in temp_paths:
                path.unlink(missing_ok=True)
            for path in created_paths:
                path.unlink(missing_ok=True)
            messagebox.showerror("Enregistrement", f"Impossible d'enregistrer le document.\n\n{exc}")
            return
        refreshed = self.db.exercice_summary(category, label)
        budget_text = ""
        if refreshed["plafond"] is not None:
            budget_text = (
                f"\nExercice {label} — Plafond : {money(refreshed['plafond'])}"
                f"\nConsommé : {money(refreshed['consumed'])}"
                f"\nReste : {money(refreshed['remaining'])}\n"
            )
        messagebox.showinfo(
            "Enregistré",
            f"Document {number} enregistré.\n\n"
            f"Total HT : {money(total)}\n"
            f"TVA {TVA_RATE * 100:g}% : {money(tva)}\n"
            f"Total TTC : {money(ttc)}\n"
            f"{budget_text}\n"
            f"PDF : {pdf_path}\nExcel : {excel_path}",
        )
        self.app.history.refresh()
        self.new_document()
