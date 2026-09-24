from __future__ import annotations

import os
import sqlite3
import sys
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from db import Database, TVA_RATE, compute_totals
from pdf_report import build_pdf
from excel_report import build_excel
from xlsx_importer import extract_articles, read_sheet_names, write_template

APP_NAME = "Gestion Articles"
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "gestion_articles.db"
EXPORT_DIR = BASE_DIR / "documents_pdf"
SEED_XLSX = BASE_DIR / "source_listes.xlsx"

COLORS = {
    "primary": "#1F4E78",
    "primary_dark": "#173B5C",
    "accent": "#2E86C1",
    "bg": "#EDF1F5",
    "surface": "#FFFFFF",
    "stripe": "#F5F8FB",
    "text": "#22303C",
    "muted": "#5A6B7B",
    "border": "#C9D6E2",
}
FONT = "Segoe UI"


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.geometry("1250x700")
        self.minsize(1000, 600)
        self.db = Database(DB_PATH)
        self.cart: list[dict] = []
        self.selected_article = None
        self._build_style()
        self._build_menu()
        self._build_ui()
        self._load_categories()
        self._ensure_seed_data()
        self._new_document()

    def _build_style(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        c = COLORS
        self.configure(bg=c["bg"])

        style.configure(".", background=c["bg"], foreground=c["text"], font=(FONT, 10))
        style.configure("TFrame", background=c["bg"])
        style.configure("Card.TFrame", background=c["surface"])
        style.configure("TLabel", background=c["bg"], foreground=c["text"])
        style.configure("Card.TLabel", background=c["surface"], foreground=c["text"])
        style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
        style.configure("Title.TLabel", font=(FONT, 20, "bold"), background=c["primary"], foreground="white")
        style.configure("Subtitle.TLabel", font=(FONT, 10), background=c["primary"], foreground="#D6E4F0")
        style.configure("Section.TLabel", font=(FONT, 11, "bold"), background=c["bg"], foreground=c["primary"])

        style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"], relief="solid", borderwidth=1)
        style.configure("TLabelframe.Label", background=c["bg"], foreground=c["primary"], font=(FONT, 10, "bold"))

        style.configure(
            "TButton", padding=(12, 6), font=(FONT, 10),
            background=c["surface"], foreground=c["text"], borderwidth=1, focusthickness=0,
        )
        style.map("TButton", background=[("active", c["stripe"]), ("pressed", c["border"])])
        style.configure(
            "Accent.TButton", background=c["accent"], foreground="white",
            font=(FONT, 10, "bold"), padding=(14, 8), borderwidth=0,
        )
        style.map(
            "Accent.TButton",
            background=[("active", c["primary"]), ("pressed", c["primary_dark"])],
            foreground=[("disabled", "#D6E4F0")],
        )

        style.configure(
            "Treeview", background=c["surface"], fieldbackground=c["surface"],
            foreground=c["text"], rowheight=28, borderwidth=0, font=(FONT, 9),
        )
        style.map("Treeview", background=[("selected", c["accent"])], foreground=[("selected", "white")])
        style.configure(
            "Treeview.Heading", background=c["primary"], foreground="white",
            font=(FONT, 9, "bold"), relief="flat", padding=(6, 6),
        )
        style.map("Treeview.Heading", background=[("active", c["primary_dark"])])

        style.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(16, 8, 16, 0))
        style.configure(
            "TNotebook.Tab", background=c["bg"], foreground=c["muted"],
            padding=(28, 11), font=(FONT, 10, "bold"),
            borderwidth=0, focusthickness=0, relief="flat",
            lightcolor=c["bg"], darkcolor=c["bg"], bordercolor=c["bg"],
        )
        style.map(
            "TNotebook.Tab",
            background=[("selected", c["accent"]), ("active", c["border"])],
            foreground=[("selected", "white"), ("active", c["text"])],
            lightcolor=[("selected", c["accent"])],
            darkcolor=[("selected", c["accent"])],
            bordercolor=[("selected", c["accent"])],
        )

        for widget in ("TEntry", "TCombobox", "TSpinbox"):
            style.configure(widget, fieldbackground=c["surface"], background=c["surface"], padding=4)
        style.map("TCombobox", fieldbackground=[("readonly", c["surface"])])

    def _build_menu(self):
        menu = tk.Menu(self)
        f = tk.Menu(menu, tearoff=False)
        f.add_command(label="Nouveau document", command=self._new_document)
        f.add_separator()
        f.add_command(label="Importer des articles Excel...", command=self.import_excel)
        f.add_command(label="Enregistrer un modèle Excel...", command=self.save_template)
        f.add_separator()
        f.add_command(label="Supprimer une liste...", command=self.delete_list)
        f.add_separator()
        f.add_command(label="Quitter", command=self.destroy)
        menu.add_cascade(label="Fichier", menu=f)
        h = tk.Menu(menu, tearoff=False)
        h.add_command(label="Format Excel attendu...", command=lambda: self.show_excel_format(None))
        h.add_separator()
        h.add_command(label="À propos", command=lambda: messagebox.showinfo(APP_NAME, "Gestion hors ligne des articles Informatique et Bureautique."))
        menu.add_cascade(label="Aide", menu=h)
        self.config(menu=menu)

    def _build_ui(self):
        header = tk.Frame(self, bg=COLORS["primary"], height=72)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=APP_NAME, bg=COLORS["primary"], fg="white", font=(FONT, 20, "bold")).pack(
            side="left", padx=(22, 16)
        )
        tk.Label(
            header,
            text="Sélection d'articles  •  Calcul HT  •  Historique  •  PDF & Excel",
            bg=COLORS["primary"], fg="#D6E4F0", font=(FONT, 10),
        ).pack(side="left")

        root = ttk.Frame(self, padding=14)
        root.pack(fill="both", expand=True)

        nb = ttk.Notebook(root)
        nb.pack(fill="both", expand=True, pady=(4, 0))
        self.tab_document = ttk.Frame(nb, padding=10)
        self.tab_history = ttk.Frame(nb, padding=10)
        nb.add(self.tab_document, text="Nouveau document")
        nb.add(self.tab_history, text="Historique")
        self.notebook = nb
        self._build_document_tab()
        self._build_history_tab()

    def _build_document_tab(self):
        meta = ttk.LabelFrame(self.tab_document, text="Document", padding=10)
        meta.pack(fill="x")
        ttk.Label(meta, text="N° document :").grid(row=0, column=0, sticky="w", padx=(0,6))
        self.number_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.number_var, width=18, state="readonly").grid(row=0, column=1, sticky="w")
        ttk.Label(meta, text="Date :").grid(row=0, column=2, sticky="w", padx=(25,6))
        self.date_var = tk.StringVar()
        ttk.Entry(meta, textvariable=self.date_var, width=14, state="readonly").grid(row=0, column=3, sticky="w")
        ttk.Label(meta, text="Liste :").grid(row=0, column=4, sticky="w", padx=(25,6))
        self.category_var = tk.StringVar()
        self.category_combo = ttk.Combobox(meta, textvariable=self.category_var, state="readonly", width=18)
        self.category_combo.grid(row=0, column=5, sticky="w")
        self.category_combo.bind("<<ComboboxSelected>>", self._on_category_change)

        actions = ttk.Frame(self.tab_document)
        actions.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(actions, text="Enregistrer + Générer PDF et Excel", style="Accent.TButton", command=self.save_document).pack(side="right")
        ttk.Button(actions, text="Nouveau", command=self._new_document).pack(side="right", padx=8)

        panes = ttk.Panedwindow(self.tab_document, orient="horizontal")
        panes.pack(fill="both", expand=True, pady=(10, 0))

        select = ttk.LabelFrame(panes, text="Sélection d'un article", padding=10)
        ttk.Label(select, text="Recherche :").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        self.search_entry = search = ttk.Entry(select, textvariable=self.search_var)
        search.grid(row=0, column=1, sticky="ew", padx=8)
        search.bind("<KeyRelease>", lambda e: self.refresh_articles())
        search.bind("<Down>", lambda e: self._move_article_selection(1))
        search.bind("<Up>", lambda e: self._move_article_selection(-1))
        search.bind("<Return>", lambda e: self.add_selected())
        ttk.Label(select, text="Qté :").grid(row=0, column=2, sticky="e")
        self.qty_var = tk.StringVar(value="1")
        qty = ttk.Spinbox(select, from_=0.01, to=999999, increment=1, textvariable=self.qty_var, width=6)
        qty.grid(row=0, column=3, padx=6)
        ttk.Button(select, text="Ajouter", style="Accent.TButton", command=self.add_selected).grid(row=0, column=4)

        cols = ("code", "designation", "unit", "price")
        self.article_tree = ttk.Treeview(select, columns=cols, show="headings", selectmode="browse", height=6)
        headers = {"code":"N°", "designation":"Désignation", "unit":"Unité", "price":"Prix unitaire HT"}
        widths = {"code":60, "designation":230, "unit":80, "price":110}
        for c in cols:
            self.article_tree.heading(c, text=headers[c])
            self.article_tree.column(c, width=widths[c], minwidth=50, anchor="center" if c != "designation" else "w")
        self.article_tree.grid(row=1, column=0, columnspan=5, sticky="nsew", pady=(10,0))
        self.article_tree.bind("<Double-1>", lambda e: self.add_selected())
        self.article_tree.bind("<<TreeviewSelect>>", self._on_article_select)
        scroll = ttk.Scrollbar(select, orient="vertical", command=self.article_tree.yview)
        scroll.grid(row=1, column=5, sticky="ns", pady=(10,0))
        hscroll = ttk.Scrollbar(select, orient="horizontal", command=self.article_tree.xview)
        hscroll.grid(row=2, column=0, columnspan=5, sticky="ew")
        self.article_tree.configure(yscrollcommand=scroll.set, xscrollcommand=hscroll.set)
        select.columnconfigure(1, weight=1)
        select.rowconfigure(1, weight=1)
        panes.add(select, weight=1)

        cartf = ttk.LabelFrame(panes, text="Articles du document", padding=10)
        bottom = ttk.Frame(cartf)
        bottom.pack(side="bottom", fill="x", pady=(8, 0))
        ttk.Button(bottom, text="Supprimer", command=self.remove_selected).pack(side="left")
        ttk.Button(bottom, text="Vider", command=self.clear_cart).pack(side="left", padx=8)
        totals = ttk.Frame(bottom)
        totals.pack(side="right")
        self.total_var = tk.StringVar(value="0,00 DA")
        self.tva_var = tk.StringVar(value="0,00 DA")
        self.ttc_var = tk.StringVar(value="0,00 DA")
        ttk.Label(totals, text="TOTAL HT :").grid(row=0, column=0, sticky="e")
        ttk.Label(totals, textvariable=self.total_var).grid(row=0, column=1, sticky="e", padx=(6, 0))
        ttk.Label(totals, text=f"TVA {TVA_RATE * 100:g}% :").grid(row=1, column=0, sticky="e")
        ttk.Label(totals, textvariable=self.tva_var).grid(row=1, column=1, sticky="e", padx=(6, 0))
        ttk.Label(totals, text="TOTAL TTC :", style="Section.TLabel").grid(row=2, column=0, sticky="e")
        ttk.Label(totals, textvariable=self.ttc_var, style="Section.TLabel").grid(row=2, column=1, sticky="e", padx=(6, 0))

        tree_wrap = ttk.Frame(cartf)
        tree_wrap.pack(fill="both", expand=True)
        ccols = ("code", "designation", "unit", "price", "qty", "total")
        self.cart_tree = ttk.Treeview(tree_wrap, columns=ccols, show="headings", height=6)
        h2 = {"code":"N°", "designation":"Désignation", "unit":"Unité", "price":"Prix HT", "qty":"Qté", "total":"Total HT"}
        w2 = {"code":55, "designation":200, "unit":70, "price":85, "qty":55, "total":95}
        for c in ccols:
            self.cart_tree.heading(c, text=h2[c])
            self.cart_tree.column(c, width=w2[c], minwidth=45, anchor="center" if c != "designation" else "w")
        self.cart_tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.cart_tree.yview)
        vs.grid(row=0, column=1, sticky="ns")
        hs = ttk.Scrollbar(tree_wrap, orient="horizontal", command=self.cart_tree.xview)
        hs.grid(row=1, column=0, sticky="ew")
        self.cart_tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        tree_wrap.rowconfigure(0, weight=1)
        tree_wrap.columnconfigure(0, weight=1)
        self.cart_tree.bind("<Delete>", lambda e: self.remove_selected())
        panes.add(cartf, weight=1)

    def _build_history_tab(self):
        top = ttk.Frame(self.tab_history)
        top.pack(fill="x")
        ttk.Label(top, text="Rechercher :").pack(side="left")
        self.history_search_var = tk.StringVar()
        e = ttk.Entry(top, textvariable=self.history_search_var, width=40)
        e.pack(side="left", padx=8)
        e.bind("<KeyRelease>", lambda ev: self.refresh_history())
        ttk.Button(top, text="Actualiser", command=self.refresh_history).pack(side="left")
        ttk.Button(top, text="Supprimer le document", command=self.delete_history_document).pack(side="left", padx=8)
        ttk.Button(top, text="Exporter en Excel", command=self.export_history_excel).pack(side="right")
        ttk.Button(top, text="Ouvrir l'Excel", command=lambda: self.open_history_file("excel")).pack(side="right", padx=8)
        ttk.Button(top, text="Ouvrir le PDF", command=lambda: self.open_history_file("pdf")).pack(side="right")
        ttk.Button(top, text="Voir les lignes", command=self.show_history_items).pack(side="right", padx=8)

        cols = ("number", "date", "category", "tva", "total", "ttc")
        self.history_tree = ttk.Treeview(self.tab_history, columns=cols, show="headings")
        for c, h, w in [
            ("number", "N° document", 170),
            ("date", "Date", 150),
            ("category", "Liste", 160),
            ("tva", "TVA", 110),
            ("total", "Total HT", 140),
            ("ttc", "Total TTC", 140),
        ]:
            self.history_tree.heading(c, text=h)
            self.history_tree.column(c, width=w, anchor="center")
        self.history_tree.pack(fill="both", expand=True, pady=(10,0))
        self.history_tree.bind("<Double-1>", lambda e: self.show_history_items())
        self.refresh_history()

    def _load_categories(self):
        names = self.db.category_names()
        self.category_combo.configure(values=names)
        if self.category_var.get() not in names:
            self.category_var.set(names[0] if names else "")

    def _ensure_seed_data(self):
        if self.db.article_count() > 0:
            return
        if SEED_XLSX.exists():
            try:
                rows = extract_articles(SEED_XLSX)
                self.db.replace_articles(rows)
            except Exception as exc:
                messagebox.showerror("Import initial", f"Impossible d'importer les listes initiales.\n\n{exc}")

    def _new_document(self):
        self.date_var.set(datetime.now().strftime("%d/%m/%Y"))
        names = self.db.category_names()
        if self.category_var.get() not in names:
            self.category_var.set(names[0] if names else "")
        self.number_var.set(self.db.next_document_number(self.category_var.get() or None))
        self.search_var.set("")
        self.qty_var.set("1")
        self.cart = []
        self.refresh_articles()
        self.refresh_cart()

    def _on_category_change(self, _event=None):
        if not self.cart:
            self.number_var.set(self.db.next_document_number(self.category_var.get() or None))
        self.refresh_articles()

    def refresh_articles(self):
        for item in self.article_tree.get_children():
            self.article_tree.delete(item)
        category = self.category_var.get().strip()
        for row in self.db.search_articles(category, self.search_var.get()):
            self.article_tree.insert("", "end", iid=str(row["id"]), values=(row["code"], row["designation"], row["unit"] or "—", f"{row['unit_price_ht']:.2f}"))

    def _on_article_select(self, _event=None):
        self.qty_var.set("1")

    def _move_article_selection(self, delta: int):
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

    def add_selected(self):
        sel = self.article_tree.selection()
        if not sel:
            messagebox.showwarning("Article", "Sélectionnez un article.")
            return
        try:
            qty = float(self.qty_var.get().replace(",", "."))
            if qty <= 0:
                raise ValueError
        except ValueError:
            messagebox.showwarning("Quantité", "Saisissez une quantité supérieure à zéro.")
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
            self.cart.append({
                "article_id": aid,
                "code": row["code"],
                "designation": row["designation"],
                "unit": row["unit"] or "—",
                "unit_price_ht": float(row["unit_price_ht"]),
                "quantity": qty,
            })
        self.refresh_cart()
        self.qty_var.set("1")
        self.search_entry.focus_set()

    def refresh_cart(self):
        for item in self.cart_tree.get_children():
            self.cart_tree.delete(item)
        for idx, row in enumerate(self.cart):
            line = row["quantity"] * row["unit_price_ht"]
            self.cart_tree.insert("", "end", iid=str(idx), values=(row["code"], row["designation"], row["unit"], f"{row['unit_price_ht']:.2f}", f"{row['quantity']:g}", f"{line:.2f}"))
        total_ht, tva_amount, total_ttc = compute_totals(self.cart)
        self.total_var.set(self._money(total_ht))
        self.tva_var.set(self._money(tva_amount))
        self.ttc_var.set(self._money(total_ttc))

    @staticmethod
    def _money(value: float) -> str:
        return f"{value:,.2f}".replace(",", " ") + " DA"

    def remove_selected(self):
        sel = self.cart_tree.selection()
        if not sel:
            return
        idx = int(sel[0])
        self.cart.pop(idx)
        self.refresh_cart()

    def clear_cart(self):
        if self.cart and messagebox.askyesno("Vider", "Supprimer toutes les lignes du document ?"):
            self.cart = []
            self.refresh_cart()

    def save_document(self):
        if not self.cart:
            messagebox.showwarning("Document", "Ajoutez au moins un article.")
            return
        number = self.number_var.get()
        category = self.category_var.get()
        created_at = datetime.now().isoformat(timespec="seconds")
        try:
            doc_id, total, tva, ttc = self.db.save_document(number, created_at, category, self.cart)
            EXPORT_DIR.mkdir(parents=True, exist_ok=True)
            pdf_path = EXPORT_DIR / f"{number}.pdf"
            excel_path = EXPORT_DIR / f"{number}.xlsx"
            build_pdf(pdf_path, number, self.date_var.get(), category, self.cart, total, TVA_RATE, tva, ttc)
            build_excel(excel_path, number, self.date_var.get(), category, self.cart, total, TVA_RATE, tva, ttc)
            self.db.set_paths(doc_id, str(pdf_path), str(excel_path))
        except Exception as exc:
            messagebox.showerror("Enregistrement", f"Impossible d'enregistrer le document.\n\n{exc}")
            return
        messagebox.showinfo(
            "Enregistré",
            f"Document {number} enregistré.\n\n"
            f"Total HT : {self._money(total)}\n"
            f"TVA {TVA_RATE * 100:g}% : {self._money(tva)}\n"
            f"Total TTC : {self._money(ttc)}\n\n"
            f"PDF : {pdf_path}\nExcel : {excel_path}",
        )
        self.refresh_history()
        self._new_document()

    def refresh_history(self):
        for item in self.history_tree.get_children():
            self.history_tree.delete(item)
        for row in self.db.list_documents(self.history_search_var.get()):
            self.history_tree.insert(
                "",
                "end",
                iid=str(row["id"]),
                values=(
                    row["number"],
                    self._format_date(row["created_at"]),
                    row["category"],
                    self._money(row["tva_amount"] or 0),
                    self._money(row["total_ht"]),
                    self._money(row["total_ttc"] or 0),
                ),
            )

    @staticmethod
    def _format_date(value: str) -> str:
        try:
            return datetime.fromisoformat(value).strftime("%d/%m/%Y %H:%M")
        except ValueError:
            return value

    def _selected_history_id(self):
        sel = self.history_tree.selection()
        if not sel:
            messagebox.showwarning("Historique", "Sélectionnez un document.")
            return None
        return int(sel[0])

    def delete_history_document(self):
        doc_id = self._selected_history_id()
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
        self.refresh_history()
        messagebox.showinfo("Historique", f"Document « {row['number']} » supprimé.")

    def show_history_items(self):
        doc_id = self._selected_history_id()
        if doc_id is None:
            return
        rows = self.db.document_items(doc_id)
        doc = self.db.get_document(doc_id)
        win = tk.Toplevel(self)
        win.title("Détail du document")
        win.configure(bg=COLORS["bg"])
        win.geometry("900x480")
        tree = ttk.Treeview(win, columns=("code","designation","unit","price","qty","total"), show="headings")
        for c,h,w in [("code","N°",80),("designation","Désignation",420),("unit","Unité",100),("price","Prix HT",100),("qty","Quantité",90),("total","Total HT",120)]:
            tree.heading(c,text=h); tree.column(c,width=w)
        tree.pack(fill="both", expand=True, padx=10, pady=(10, 4))
        for r in rows:
            tree.insert("", "end", values=(r["code"], r["designation"], r["unit"], f"{r['unit_price_ht']:.2f}", f"{r['quantity']:g}", f"{r['total_ht']:.2f}"))
        if doc:
            rate = doc["tva_rate"] or TVA_RATE
            summary = ttk.Frame(win)
            summary.pack(fill="x", padx=10, pady=(0, 10))
            ttk.Label(summary, text=f"TOTAL HT : {self._money(doc['total_ht'])}").pack(side="right", padx=(12, 0))
            ttk.Label(summary, text=f"TVA {rate * 100:g}% : {self._money(doc['tva_amount'] or 0)}").pack(side="right", padx=(12, 0))
            ttk.Label(summary, text=f"TOTAL TTC : {self._money(doc['total_ttc'] or 0)}", style="Section.TLabel").pack(side="right", padx=(12, 0))

    def open_history_file(self, kind: str) -> None:
        doc_id = self._selected_history_id()
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
        self._open_path(path)

    @staticmethod
    def _open_path(path: Path) -> None:
        try:
            os.startfile(str(path))
        except AttributeError:
            import subprocess
            subprocess.Popen(["xdg-open", str(path)])

    def export_history_excel(self) -> None:
        doc_id = self._selected_history_id()
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
                self._format_date(row["created_at"]),
                row["category"],
                items,
                row["total_ht"],
                row["tva_rate"] or TVA_RATE,
                row["tva_amount"] or 0,
                row["total_ttc"] or 0,
            )
        except Exception as exc:
            messagebox.showerror("Export Excel", f"Impossible d'exporter le document.\n\n{exc}")
            return
        messagebox.showinfo("Export Excel", f"Document exporté :\n{dest}")

    FORMAT_HELP = (
        "Rappel du format Excel attendu\n\n"
        "• Le classeur contient une feuille par liste.\n"
        "• La première ligne de chaque feuille doit contenir exactement :\n"
        "   N°  |  Désignation  |  Unité de mesure  |  Prix unitaire HT\n\n"
        "• N° : code / référence de l'article\n"
        "• Désignation : libellé de l'article\n"
        "• Unité de mesure : pièce, boîte, mètre, ...\n"
        "• Prix unitaire HT : nombre (point ou virgule acceptés)\n\n"
        "Une éventuelle ligne TOTAL en fin de feuille est ignorée.\n"
        "Utilisez « Fichier → Importer des articles Excel... » pour charger la liste."
    )

    def show_excel_format(self, categories: list[str] | None = None) -> None:
        text = self.FORMAT_HELP
        if categories:
            text += "\n\nListe(s) : " + ", ".join(categories)
        messagebox.showinfo("Format Excel", text)

    def save_template(self) -> None:
        dest = filedialog.asksaveasfilename(
            title="Enregistrer le modèle Excel",
            defaultextension=".xlsx",
            initialfile="modele_listes.xlsx",
            filetypes=[("Classeur Excel", "*.xlsx")],
        )
        if not dest:
            return
        try:
            write_template(dest, self.db.category_names())
        except Exception as exc:
            messagebox.showerror("Modèle Excel", f"Impossible de créer le modèle.\n\n{exc}")
            return
        messagebox.showinfo("Modèle Excel", f"Modèle créé :\n{dest}")

    def delete_list(self) -> None:
        names = self.db.category_names()
        if len(names) <= 1:
            messagebox.showwarning("Liste", "Au moins une liste doit être conservée.")
            return
        win = tk.Toplevel(self)
        win.title("Supprimer une liste")
        win.configure(bg=COLORS["bg"])
        win.transient(self)
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
            self.db.delete_category(name)
            win.destroy()
            self._load_categories()
            self.refresh_articles()
            messagebox.showinfo("Liste", f"La liste « {name} » a été supprimée.")

        actions = ttk.Frame(win)
        actions.pack(fill="x", padx=14, pady=14)
        ttk.Button(actions, text="Supprimer", style="Accent.TButton", command=confirm).pack(side="right")
        ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)

    def _ask_import_target(self, sheets: list[str]) -> dict[str, str] | None:
        win = tk.Toplevel(self)
        win.title("Importer une feuille Excel")
        win.configure(bg=COLORS["bg"])
        win.transient(self)
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

        self.wait_window(win)
        return result or None

    def import_excel(self) -> None:
        path = filedialog.askopenfilename(title="Sélectionner le classeur Excel", filetypes=[("Excel", "*.xlsx")])
        if not path:
            return
        try:
            sheets = read_sheet_names(path)
        except Exception as exc:
            messagebox.showerror("Import Excel", f"Impossible de lire le classeur.\n\n{exc}")
            return
        if not sheets:
            messagebox.showerror("Import Excel", "Le classeur ne contient aucune feuille.")
            return

        target = self._ask_import_target(sheets)
        if not target:
            return
        sheet, name = target["sheet"], target["name"]

        existing = {n.lower() for n in self.db.category_names()}
        is_new = name.lower() not in existing
        if not is_new and not messagebox.askyesno(
            "Remplacer",
            f"La liste « {name} » existe déjà.\n\nRemplacer ses articles par ceux de la feuille « {sheet} » ?",
        ):
            return

        try:
            rows = extract_articles(path, {name: sheet})
            if not rows:
                raise ValueError(f"Aucune donnée exploitable dans la feuille « {sheet} ».")
            if is_new:
                self.db.add_category(name)
            self.db.replace_articles_by_category(rows)
        except Exception as exc:
            messagebox.showerror("Import Excel", str(exc))
            return

        self._load_categories()
        self.category_var.set(name)
        self.refresh_articles()
        messagebox.showinfo("Import terminé", f"{len(rows)} articles importés dans la liste « {name} ».")


if __name__ == "__main__":
    app = App()
    app.mainloop()
