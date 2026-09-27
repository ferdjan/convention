"""Onglet « Historique » : consultation, suppression et export des documents."""
from __future__ import annotations

import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from app.config import COLORS, TVA_RATE
from app.database import Database
from app.reports.excel import build_excel
from app.ui.common import display_date, exercice_display, money, open_path
from app.ui.dialogs import edit_document, show_document_items


class HistoryView(ttk.Frame):
    """Liste des documents enregistrés et actions associées."""

    def __init__(self, master: tk.Misc, app) -> None:
        super().__init__(master, padding=16)
        self.app = app
        self.db: Database = app.db

    # ------------------------------------------------------------------ build

    def build(self) -> None:
        """Trois bandes : recherche + filtres, liste + aperçu, actions."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        # --- recherche et filtres
        top = ttk.Frame(self)
        top.grid(row=0, column=0, sticky="ew")
        ttk.Label(top, text="Rechercher", style="Section.TLabel").pack(side="left", padx=(0, 12))
        self.search_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.search_var)
        e.pack(side="left", fill="x", expand=True)
        e.bind("<KeyRelease>", lambda ev: self.refresh())
        ttk.Label(top, text="Convention :").pack(side="left", padx=(16, 6))
        self.category_filter_var = tk.StringVar(value="Toutes")
        self.category_filter = ttk.Combobox(
            top, textvariable=self.category_filter_var, state="readonly", width=18
        )
        self.category_filter.pack(side="left")
        self.category_filter.bind("<<ComboboxSelected>>", lambda ev: self.refresh())
        ttk.Label(top, text="Exercice :").pack(side="left", padx=(16, 6))
        self.exercice_filter_var = tk.StringVar(value="Tous")
        self.exercice_filter = ttk.Combobox(
            top, textvariable=self.exercice_filter_var, state="readonly", width=14
        )
        self.exercice_filter.pack(side="left")
        self.exercice_filter.bind("<<ComboboxSelected>>", lambda ev: self.refresh())
        ttk.Button(top, text="Actualiser", command=self.refresh).pack(side="left", padx=(12, 0))

        # --- liste à gauche, aperçu du document sélectionné à droite
        body = ttk.Panedwindow(self, orient="horizontal")
        body.grid(row=1, column=0, sticky="nsew", pady=(12, 0))

        listf = ttk.LabelFrame(body, text="Documents enregistrés", padding=12)
        self.count_var = tk.StringVar(value="")
        ttk.Label(listf, textvariable=self.count_var, style="Muted.TLabel").grid(row=0, column=0, sticky="w", pady=(0, 8))
        list_wrap = ttk.Frame(listf)
        list_wrap.grid(row=1, column=0, sticky="nsew")
        cols = ("number", "date", "category", "exercice", "total", "ttc")
        self.tree = ttk.Treeview(list_wrap, columns=cols, show="headings", selectmode="browse", height=10)
        for c, h, w, anchor in [
            ("number", "N° document", 150, "w"),
            ("date", "Date", 90, "center"),
            ("category", "Liste", 110, "w"),
            ("exercice", "Exercice", 100, "center"),
            ("total", "Total HT", 100, "e"),
            ("ttc", "Total TTC", 110, "e"),
        ]:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, minwidth=70, anchor=anchor, stretch=(c in ("number", "category", "ttc")))
        self.tree.grid(row=0, column=0, sticky="nsew")
        lvs = ttk.Scrollbar(list_wrap, orient="vertical", command=self.tree.yview)
        lvs.grid(row=0, column=1, sticky="ns")
        lhs = ttk.Scrollbar(list_wrap, orient="horizontal", command=self.tree.xview)
        lhs.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=lvs.set, xscrollcommand=lhs.set)
        list_wrap.rowconfigure(0, weight=1)
        list_wrap.columnconfigure(0, weight=1)
        listf.rowconfigure(1, weight=1)
        listf.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", lambda e: self.show_items())
        self.tree.bind("<<TreeviewSelect>>", lambda e: self.refresh_preview())
        body.add(listf, weight=3)

        preview = ttk.LabelFrame(body, text="Aperçu du document sélectionné", padding=12)
        self.preview_heading = ttk.Label(preview, text="Sélectionnez un document", style="Section.TLabel")
        self.preview_heading.grid(row=0, column=0, columnspan=2, sticky="w")
        self.preview_meta = ttk.Label(preview, text="—", style="Muted.TLabel")
        self.preview_meta.grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 10))

        self.preview_tree = ttk.Treeview(preview, columns=("designation", "unit", "price", "qty", "total"),
                                         show="headings", selectmode="none", height=8)
        for c, h, w, anchor in [
            ("designation", "Désignation", 240, "w"),
            ("unit", "Unité", 70, "center"),
            ("price", "Prix HT", 100, "e"),
            ("qty", "Qté", 60, "center"),
            ("total", "Total HT", 105, "e"),
        ]:
            self.preview_tree.heading(c, text=h)
            self.preview_tree.column(c, width=w, minwidth=50, anchor=anchor, stretch=(c == "designation"))
        self.preview_tree.grid(row=2, column=0, columnspan=2, sticky="nsew")
        pvs = ttk.Scrollbar(preview, orient="vertical", command=self.preview_tree.yview)
        pvs.grid(row=2, column=2, sticky="ns")
        self.preview_tree.configure(yscrollcommand=pvs.set)
        preview.rowconfigure(2, weight=1)
        preview.columnconfigure(0, weight=1)

        # Synthèse des montants du document prévisualisé
        summary = tk.Frame(
            preview, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1,
        )
        summary.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        self.preview_total_ht = tk.StringVar(value="0.00 DA")
        self.preview_tva = tk.StringVar(value="0.00 DA")
        self.preview_total_ttc = tk.StringVar(value="0.00 DA")
        for label, variable, label_style, value_style in (
            ("Total HT", self.preview_total_ht, "TotalLabel.TLabel", "TotalValue.TLabel"),
            (f"TVA {TVA_RATE * 100:g}%", self.preview_tva, "TotalLabel.TLabel", "TotalValue.TLabel"),
        ):
            ttk.Label(summary, text=label, style=label_style).pack(side="left", pady=(10, 10), padx=(0, 6))
            ttk.Label(summary, textvariable=variable, style=value_style).pack(side="left", pady=(10, 10), padx=(0, 20))
        tk.Frame(summary, width=1, bg=COLORS["border"]).pack(side="left", fill="y", pady=12)
        ttk.Label(summary, text="TOTAL TTC", style="TotalTTCLabel.TLabel").pack(side="left", pady=(10, 10), padx=(20, 8))
        ttk.Label(summary, textvariable=self.preview_total_ttc, style="TotalTTCValue.TLabel").pack(
            side="left", pady=(10, 10), padx=(0, 20),
        )
        body.add(preview, weight=4)
        # Partage initial équilibré : la liste garde ~640 px, l'aperçu le reste
        body.sashpos(0, 640)

        # --- barre d'actions, regroupée par intention
        toolbar = tk.Frame(self, bg=COLORS["surface"], highlightbackground=COLORS["border"], highlightthickness=1)
        toolbar.grid(row=2, column=0, sticky="ew", pady=(12, 0))
        actions = ttk.Frame(toolbar, style="Card.TFrame", padding=(14, 10))
        actions.pack(fill="x")
        ttk.Label(actions, text="Consulter", style="Muted.TLabel").pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Voir les lignes", command=self.show_items).pack(side="left")
        ttk.Button(
            actions, text="Modifier le document", command=self.modify_document
        ).pack(side="left", padx=(6, 0))
        ttk.Label(actions, text="Ouvrir", style="Muted.TLabel").pack(side="left", padx=(18, 6))
        ttk.Button(actions, text="PDF", command=lambda: self.open_file("pdf")).pack(side="left", padx=(0, 6))
        ttk.Button(actions, text="Excel", command=lambda: self.open_file("excel")).pack(side="left")
        ttk.Label(actions, text="Exporter", style="Muted.TLabel").pack(side="left", padx=(18, 6))
        ttk.Button(actions, text="Vers Excel…", command=self.export_excel).pack(side="left")
        ttk.Button(actions, text="Supprimer le document", style="Danger.TButton", command=self.delete_document).pack(side="right")

        self.refresh()

    # ----------------------------------------------------------------- lecture

    def refresh(self) -> None:
        category = self.category_filter_var.get().strip()
        exercice = self.exercice_filter_var.get().strip()
        rows = self.db.list_documents(
            self.search_var.get(),
            category=(category if category and category != "Toutes" else None),
            exercice=(exercice if exercice and exercice != "Tous" else None),
        )
        # Rafraîchit les valeurs des filtres sans réentrer dans refresh().
        names = ["Toutes"] + sorted(
            {row["category"] for row in self.db.list_documents("")}, key=str.casefold
        )
        self.category_filter.configure(values=names)
        labels = ["Tous"] + sorted(
            {row["exercice_label"] for row in self.db.list_documents("") if row["exercice_label"]},
            key=str.casefold,
        )
        self.exercice_filter.configure(values=labels)
        for item in self.tree.get_children():
            self.tree.delete(item)
        for row in rows:
            self.tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["number"],
                    display_date(row["created_at"]),
                    row["category"],
                    exercice_display(row["exercice_label"]),
                    money(row["total_ht"]),
                    money(row["total_ttc"] or 0),
                ),
            )
        if rows:
            self.count_var.set(f"{len(rows)} document{'s' if len(rows) > 1 else ''}")
        else:
            self.count_var.set("Aucun document")
        self.refresh_preview()

    def refresh_preserving_selection(self) -> None:
        """Recharge la liste en gardant le document sélectionné (changement de thème)."""
        selection = self.tree.selection()
        self.refresh()
        if selection and self.tree.exists(selection[0]):
            self.tree.selection_set(selection[0])
            self.refresh_preview()

    def refresh_preview(self) -> None:
        """Affiche le contenu du document sélectionné dans le panneau de droite."""
        for item in self.preview_tree.get_children():
            self.preview_tree.delete(item)
        sel = self.tree.selection()
        if not sel:
            self.preview_heading.configure(text="Sélectionnez un document")
            self.preview_meta.configure(text="—")
            for variable in (self.preview_total_ht, self.preview_tva, self.preview_total_ttc):
                variable.set(money(0))
            return
        doc_id = int(sel[0])
        row = self.db.get_document(doc_id)
        if not row:
            self.preview_heading.configure(text="Document introuvable")
            return
        self.preview_heading.configure(text=row["number"])
        self.preview_meta.configure(
            text=(
                f"Créé le {display_date(row['created_at'])}  ·  Liste « {row['category']} »"
                f"  ·  Exercice {exercice_display(row['exercice_label'])}"
            )
        )
        for item in self.db.document_items(doc_id):
            self.preview_tree.insert(
                "", "end",
                values=(
                    item["designation"],
                    item["unit"] or "—",
                    f"{item['unit_price_ht']:.2f}",
                    f"{item['quantity']:g}",
                    f"{item['total_ht']:.2f}",
                ),
            )
        self.preview_total_ht.set(money(row["total_ht"]))
        self.preview_tva.set(money(row["tva_amount"] or 0))
        self.preview_total_ttc.set(money(row["total_ttc"] or 0))

    def selected_id(self):
        sel = self.tree.selection()
        if not sel:
            messagebox.showwarning("Historique", "Sélectionnez un document.")
            return None
        return int(sel[0])

    # ----------------------------------------------------------------- actions

    def delete_document(self) -> None:
        doc_id = self.selected_id()
        if doc_id is None:
            return
        row = self.db.get_document(doc_id)
        if not row:
            return
        if not messagebox.askyesno(
            "Supprimer le document",
            f"Supprimer le document « {row['number']} » de l'historique ?\n\n"
            "Ses lignes seront supprimées. Les fichiers PDF/Excel restent sur le disque.",
        ):
            return
        try:
            self.db.delete_document(doc_id)
        except Exception as exc:
            messagebox.showerror("Historique", f"Impossible de supprimer le document.\n\n{exc}")
            return
        self.refresh()
        messagebox.showinfo("Historique", f"Document « {row['number']} » supprimé.")

    def show_items(self) -> None:
        doc_id = self.selected_id()
        if doc_id is None:
            return
        show_document_items(self, self.db, doc_id)

    def modify_document(self) -> None:
        """Ouvre l'édition des lignes du document sélectionné.

        Un document d'un exercice clôturé ou d'une convention clôturée/expirée
        reste en lecture seule : le dialogue en affiche le motif.
        """
        doc_id = self.selected_id()
        if doc_id is None:
            return
        edit_document(self, self.db, doc_id, on_saved=self.refresh_preserving_selection)

    def open_file(self, kind: str) -> None:
        doc_id = self.selected_id()
        if doc_id is None:
            return
        row = self.db.get_document(doc_id)
        column = "pdf_path" if kind == "pdf" else "excel_path"
        label = "PDF" if kind == "pdf" else "Excel"
        if not row or not row[column]:
            messagebox.showwarning(label, f"Aucun fichier {label} enregistré pour ce document.")
            return
        path = Path(row[column])
        if not path.exists():
            messagebox.showwarning(label, f"Le fichier {label} est introuvable.")
            return
        open_path(path)

    def export_excel(self) -> None:
        doc_id = self.selected_id()
        if doc_id is None:
            return
        row = self.db.get_document(doc_id)
        if not row:
            return
        default = f"{row['number']}.xlsx"
        dest = filedialog.asksaveasfilename(
            title="Exporter en Excel",
            defaultextension=".xlsx",
            initialfile=default,
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not dest:
            return
        try:
            items = self.db.document_items(doc_id)
            build_excel(
                dest,
                row["number"],
                display_date(row["created_at"]),
                row["category"],
                items,
                row["total_ht"],
                TVA_RATE if row["tva_rate"] is None else row["tva_rate"],
                row["tva_amount"] or 0,
                row["total_ttc"] or 0,
            )
        except Exception as exc:
            messagebox.showerror("Export Excel", f"Impossible d'exporter le document.\n\n{exc}")
            return
        messagebox.showinfo("Export Excel", f"Document exporté :\n{dest}")
