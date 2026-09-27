"""Édition d'un document déjà enregistré : quantités, ajout et retrait de lignes.

Le document n'est modifiable que si sa convention **et** son exercice sont
encore actifs (sinon lecture seule). Le plafond reste ferme : dès que
« consommé hors ce document + nouveau total » atteint le plafond,
l'enregistrement est refusé, sans exception possible. Le PDF et l'Excel sont
régénérés aux mêmes chemins, les anciens fichiers étant restaurés en cas
d'échec de la mise à jour de la base.
"""
from __future__ import annotations

import shutil
import tkinter as tk
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
from app.ui.common import display_date, exercice_display, money
from app.utils import compute_totals, parse_quantity


class EditDocumentDialog(tk.Toplevel):
    """Fenêtre modale d'édition des lignes d'un document."""

    def __init__(self, parent: tk.Misc, db: Database, doc, on_saved=None) -> None:
        super().__init__(parent)
        self.db = db
        self.doc = doc
        self.on_saved = on_saved
        self.document_id = int(doc["id"])
        self.category = str(doc["category"])
        self.exercice_label = doc["exercice_label"]
        self.old_total = float(doc["total_ht"] or 0.0)
        self.lines: list[dict] = []
        self.initial_ids: set[int] = set()
        self.saved = False
        self._editor: ttk.Entry | None = None
        self._articles: dict[int, dict] = {}

        self.title("Modifier le document")
        self.configure(bg=COLORS["bg"])
        self.geometry("1080x660")
        self.minsize(940, 580)
        self.transient(parent)
        self._build()
        self._load_lines()
        self._refresh_articles()
        self.grab_set()

    # ------------------------------------------------------------------ build

    def _build(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        header = ttk.Frame(self)
        header.grid(row=0, column=0, sticky="ew", padx=16, pady=(14, 0))
        ttk.Label(header, text=str(self.doc["number"]), style="Section.TLabel").pack(side="left")
        ttk.Label(header, text=f"Date : {display_date(self.doc['created_at'])}").pack(
            side="left", padx=(18, 0)
        )
        ttk.Label(header, text=f"Liste : {self.category}").pack(side="left", padx=(18, 0))
        ttk.Label(
            header, text=f"Exercice : {exercice_display(self.exercice_label)}"
        ).pack(side="left", padx=(18, 0))
        ttk.Label(
            header,
            text="Double-cliquez sur une ligne pour changer sa quantité.",
            style="Muted.TLabel",
        ).pack(side="right")

        panes = ttk.Panedwindow(self, orient="horizontal")
        panes.grid(row=1, column=0, sticky="nsew", padx=16, pady=(12, 0))

        # --- lignes du document
        left = ttk.LabelFrame(panes, text="Lignes du document", padding=12)
        left.columnconfigure(0, weight=1)
        left.rowconfigure(1, weight=1)
        self.count_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.count_var, style="Muted.TLabel").grid(
            row=0, column=0, sticky="w", pady=(0, 8)
        )

        wrap = ttk.Frame(left)
        wrap.grid(row=1, column=0, sticky="nsew")
        wrap.columnconfigure(0, weight=1)
        wrap.rowconfigure(0, weight=1)
        cols = ("code", "designation", "unit", "price", "qty", "total")
        self.tree = ttk.Treeview(
            wrap, columns=cols, show="headings", selectmode="browse", height=12
        )
        for c, h, w, anchor in [
            ("code", "N°", 70, "w"),
            ("designation", "Désignation", 300, "w"),
            ("unit", "Unité", 70, "center"),
            ("price", "Prix HT", 100, "e"),
            ("qty", "Qté", 70, "center"),
            ("total", "Total HT", 110, "e"),
        ]:
            self.tree.heading(c, text=h)
            self.tree.column(c, width=w, minwidth=50, anchor=anchor, stretch=(c == "designation"))
        self.tree.grid(row=0, column=0, sticky="nsew")
        vs = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview)
        vs.grid(row=0, column=1, sticky="ns")
        hs = ttk.Scrollbar(wrap, orient="horizontal", command=self.tree.xview)
        hs.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vs.set, xscrollcommand=hs.set)
        self.tree.bind("<Double-1>", self._edit_quantity)

        line_actions = ttk.Frame(left)
        line_actions.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(
            line_actions, text="Modifier la quantité", command=self._edit_quantity
        ).pack(side="left")
        ttk.Button(
            line_actions, text="Retirer la ligne", style="Danger.TButton",
            command=self._remove_line,
        ).pack(side="left", padx=(8, 0))
        ttk.Label(
            line_actions,
            text="Entrée valide · Échap annule",
            style="Muted.TLabel",
        ).pack(side="right")
        panes.add(left, weight=3)

        # --- ajout d'articles
        right = ttk.LabelFrame(panes, text="Ajouter un article", padding=12)
        right.columnconfigure(0, weight=1)
        right.rowconfigure(2, weight=1)
        bar = ttk.Frame(right)
        bar.grid(row=0, column=0, sticky="ew")
        bar.columnconfigure(1, weight=1)
        ttk.Label(bar, text="Recherche :").grid(row=0, column=0, sticky="w")
        self.search_var = tk.StringVar()
        search = ttk.Entry(bar, textvariable=self.search_var, font=(FONT, 11))
        search.grid(row=0, column=1, sticky="ew", padx=(6, 0), ipady=3)
        self.search_var.trace_add("write", lambda *_a: self._refresh_articles())
        search.bind("<Return>", lambda _e: self._add_article())
        search.bind("<Down>", lambda _e: self._move_results(1))
        search.bind("<Up>", lambda _e: self._move_results(-1))

        res_wrap = ttk.Frame(right)
        res_wrap.grid(row=1, column=0, sticky="nsew", pady=(10, 0))
        res_wrap.columnconfigure(0, weight=1)
        res_wrap.rowconfigure(0, weight=1)
        self.results = ttk.Treeview(
            res_wrap, columns=("code", "designation", "unit", "price"),
            show="headings", selectmode="browse", height=10,
        )
        for c, h, w, anchor in [
            ("code", "N°", 60, "w"),
            ("designation", "Désignation", 240, "w"),
            ("unit", "Unité", 60, "center"),
            ("price", "Prix HT", 90, "e"),
        ]:
            self.results.heading(c, text=h)
            self.results.column(c, width=w, minwidth=50, anchor=anchor, stretch=(c == "designation"))
        self.results.grid(row=0, column=0, sticky="nsew")
        rs = ttk.Scrollbar(res_wrap, orient="vertical", command=self.results.yview)
        rs.grid(row=0, column=1, sticky="ns")
        self.results.configure(yscrollcommand=rs.set)
        self.results.bind("<Double-1>", lambda _e: self._add_article())

        add_bar = ttk.Frame(right)
        add_bar.grid(row=2, column=0, sticky="ew", pady=(10, 0))
        ttk.Label(add_bar, text="Quantité :").pack(side="left")
        self.qty_var = tk.StringVar(value="1")
        ttk.Spinbox(
            add_bar, from_=0.01, to=999999, increment=1, textvariable=self.qty_var, width=6
        ).pack(side="left", padx=(6, 10))
        ttk.Button(
            add_bar, text="Ajouter", style="Accent.TButton", command=self._add_article
        ).pack(side="left")
        ttk.Label(
            right,
            text="Les prix sont figés pour l'exercice : ils sont repris tels quels\nde la liste active.",
            style="Muted.TLabel", justify="left",
        ).grid(row=3, column=0, sticky="w", pady=(10, 0))
        panes.add(right, weight=3)

        # --- exercice / plafond et synthèse des montants
        bottom = ttk.Frame(self)
        bottom.grid(row=2, column=0, sticky="ew", padx=16, pady=(12, 0))
        bottom.columnconfigure(1, weight=1)

        budget = ttk.LabelFrame(bottom, text="Exercice et plafond", padding=10)
        budget.grid(row=0, column=0, sticky="nsew", padx=(0, 12))
        self.exercice_info_var = tk.StringVar(value="—")
        self.plafond_var = tk.StringVar(value="—")
        self.consomme_var = tk.StringVar(value="—")
        self.doc_var = tk.StringVar(value="—")
        self.reste_var = tk.StringVar(value="—")
        self.rate_var = tk.DoubleVar(value=0.0)
        self.gauge = ttk.Progressbar(
            budget, variable=self.rate_var, maximum=100.0,
            style="BudgetOk.Horizontal.TProgressbar",
        )
        self.gauge.grid(row=0, column=0, columnspan=4, sticky="ew")
        ttk.Label(
            budget, textvariable=self.exercice_info_var, style="Muted.TLabel"
        ).grid(row=1, column=0, columnspan=4, sticky="w", pady=(4, 0))
        self._cells: dict[str, tk.Label] = {}
        for index, (key, label) in enumerate(
            (
                ("plafond", "Plafond"),
                ("consomme", "Consommé (hors doc.)"),
                ("doc", "Ce document"),
                ("reste", "Reste dispo."),
            )
        ):
            row = 2 + index // 2
            col = (index % 2) * 2
            ttk.Label(budget, text=label, style="Muted.TLabel").grid(
                row=row, column=col, sticky="w",
                padx=(0 if index % 2 == 0 else 18, 6), pady=(4, 0),
            )
            cell = tk.Label(
                budget,
                textvariable=getattr(self, f"{key}_var"),
                bg=COLORS["bg"], fg=COLORS["text"], font=(FONT, 10, "bold"),
            )
            cell.grid(row=row, column=col + 1, sticky="w", pady=(4, 0))
            self._cells[key] = cell
        self.alert_var = tk.StringVar(value="")
        self.alert_label = tk.Label(
            budget, textvariable=self.alert_var,
            bg=COLORS["bg"], fg=COLORS["muted"], font=(FONT, 9),
        )
        self.alert_label.grid(row=4, column=0, columnspan=4, sticky="w", pady=(6, 0))

        summary = tk.Frame(
            bottom, bg=COLORS["surface"],
            highlightbackground=COLORS["border"], highlightthickness=1,
        )
        summary.grid(row=0, column=1, sticky="nsew")
        self.total_var = tk.StringVar(value=money(0))
        self.tva_var = tk.StringVar(value=money(0))
        self.ttc_var = tk.StringVar(value=money(0))
        for label, variable, label_style, value_style in (
            ("Total HT", self.total_var, "TotalLabel.TLabel", "TotalValue.TLabel"),
            (f"TVA {TVA_RATE * 100:g}%", self.tva_var, "TotalLabel.TLabel", "TotalValue.TLabel"),
        ):
            ttk.Label(summary, text=label, style=label_style).pack(
                side="left", pady=(14, 14), padx=(16, 6)
            )
            ttk.Label(summary, textvariable=variable, style=value_style).pack(
                side="left", pady=(14, 14), padx=(0, 18)
            )
        tk.Frame(summary, width=1, bg=COLORS["border"]).pack(side="left", fill="y", pady=14)
        ttk.Label(summary, text="TOTAL TTC", style="TotalTTCLabel.TLabel").pack(
            side="left", padx=(18, 8)
        )
        ttk.Label(summary, textvariable=self.ttc_var, style="TotalTTCValue.TLabel").pack(
            side="left", padx=(0, 16)
        )

        # --- actions
        actions = ttk.Frame(self)
        actions.grid(row=3, column=0, sticky="ew", padx=16, pady=(12, 16))
        self.status_var = tk.StringVar(value="")
        ttk.Label(actions, textvariable=self.status_var, style="Muted.TLabel").pack(side="left")
        ttk.Button(actions, text="Annuler", command=self.destroy).pack(side="right")
        self.save_button = ttk.Button(
            actions, text="Enregistrer les modifications", style="Accent.TButton",
            command=self._save,
        )
        self.save_button.pack(side="right", padx=(0, 8))

    # ------------------------------------------------------------- rafraîchir

    def _load_lines(self) -> None:
        self.lines = [
            {
                "item_id": int(row["id"]),
                "category": self.category,
                "code": row["code"],
                "designation": row["designation"],
                "unit": row["unit"],
                "unit_price_ht": float(row["unit_price_ht"]),
                "quantity": float(row["quantity"]),
            }
            for row in self.db.document_items(self.document_id)
        ]
        self.initial_ids = {line["item_id"] for line in self.lines if line["item_id"]}
        self._refresh()

    def _refresh(self, select: int | None = None) -> None:
        for item in self.tree.get_children():
            self.tree.delete(item)
        for index, line in enumerate(self.lines):
            self.tree.insert(
                "", "end", iid=str(index),
                values=(
                    line["code"], line["designation"], line["unit"] or "—",
                    money(line["unit_price_ht"]), f"{line['quantity']:g}",
                    money(line["quantity"] * line["unit_price_ht"]),
                ),
            )
        if select is not None and self.lines and self.tree.exists(str(select)):
            self.tree.selection_set(str(select))
            self.tree.see(str(select))
        count = len(self.lines)
        units = sum(line["quantity"] for line in self.lines)
        self.count_var.set(
            f"{count} ligne{'s' if count > 1 else ''}  ·  {units:g} unité{'s' if units != 1 else ''}"
            if count
            else "Aucune ligne"
        )
        total_ht, tva_amount, total_ttc = compute_totals(self.lines)
        self.total_var.set(money(total_ht))
        self.tva_var.set(money(tva_amount))
        self.ttc_var.set(money(total_ttc))
        self._refresh_budget(total_ht)

    def _refresh_budget(self, total_ht: float) -> None:
        summary = self.db.exercice_summary(self.category, self.exercice_label)
        plafond = summary["plafond"]
        other = round(max(0.0, float(summary["consumed"]) - self.old_total), 2)
        self.consomme_var.set(money(other))
        self.doc_var.set(money(total_ht))
        self.exercice_info_var.set(
            f"Exercice {exercice_display(self.exercice_label)}  ·  du "
            f"{summary['start_date'] or '—'} au {summary['end_date'] or '—'}"
        )
        for key in ("plafond", "consomme", "doc", "reste"):
            self._cells[key].configure(fg=COLORS["text"])

        blocked = False
        if plafond is None:
            self.plafond_var.set("illimité")
            self.reste_var.set("—")
            self._cells["reste"].configure(fg=BUDGET_COLORS["none"])
            self._set_gauge(0.0, "Ok")
            self._set_alert(
                BUDGET_COLORS["none"], "Exercice sans plafond : aucune limite de consommation."
            )
        else:
            projected = round(other + total_ht, 2)
            remaining = round(float(plafond) - projected, 2)
            rate = projected / float(plafond) if plafond else 0.0
            self.plafond_var.set(money(plafond))
            self.reste_var.set(money(remaining))
            # Blocage ferme : l'égalité exacte avec le plafond bloque aussi.
            blocked = projected >= round(float(plafond), 2)
            if blocked:
                color, level = BUDGET_COLORS["over"], "Over"
                if projected > float(plafond) + 0.005:
                    text = (
                        f"DÉPASSEMENT de {money(projected - float(plafond))} — "
                        "modification bloquée (plafond de l'exercice)."
                    )
                else:
                    text = "PLAFOND ATTEINT — modification bloquée (plafond de l'exercice)."
            elif rate >= BUDGET_CRITICAL:
                color, level = BUDGET_COLORS["critical"], "Critical"
                text = f"{rate * 100:.0f} % du plafond après modification — proche de la limite."
            elif rate >= BUDGET_WARN:
                color, level = BUDGET_COLORS["warn"], "Warn"
                text = f"{rate * 100:.0f} % du plafond consommé après modification."
            else:
                color, level = BUDGET_COLORS["ok"], "Ok"
                text = f"{rate * 100:.0f} % du plafond consommé après modification."
            self._cells["reste"].configure(fg=color)
            self._set_gauge(rate * 100, level)
            self._set_alert(color, text)

        self.status_var.set("Plafond atteint : enregistrement impossible." if blocked else "")
        self.save_button.configure(
            state="normal" if (self.lines and not blocked) else "disabled"
        )

    def _set_gauge(self, percent: float, level: str) -> None:
        self.rate_var.set(max(0.0, min(100.0, percent)))
        self.gauge.configure(style=f"Budget{level}.Horizontal.TProgressbar")

    def _set_alert(self, color: str, text: str) -> None:
        self.alert_var.set(text)
        self.alert_label.configure(fg=color)

    # ------------------------------------------------------------- édition

    def _edit_quantity(self, event: tk.Event | None = None) -> str:
        if self._editor is not None:
            return "break"
        if event is not None:
            row_id = self.tree.identify_row(event.y)
            if row_id:
                self.tree.selection_set(row_id)
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                "Quantité", "Sélectionnez une ligne à modifier.", parent=self
            )
            return "break"
        index = int(selection[0])
        bbox = self.tree.bbox(selection[0], "qty")
        if not bbox:
            return "break"
        x, y, w, h = bbox
        entry = ttk.Entry(self.tree, justify="center")
        entry.place(x=x, y=y, width=max(w, 46), height=h)
        self._editor = entry
        entry.insert(0, f"{self.lines[index]['quantity']:g}")
        entry.select_range(0, "end")
        # Le champ doit être affiché avant de prendre le focus : sans cela la
        # première frappe part ailleurs tant que le gestionnaire n'a pas
        # positionné la fenêtre.
        entry.update_idletasks()
        entry.focus_set()

        def stop() -> None:
            self._editor = None
            try:
                entry.destroy()
            except tk.TclError:
                pass

        def commit(save: bool) -> None:
            if self._editor is None:
                return
            text = entry.get()
            stop()
            if not save:
                return
            try:
                quantity = parse_quantity(text)
            except (TypeError, ValueError) as exc:
                messagebox.showwarning("Quantité", str(exc), parent=self)
                return
            self.lines[index]["quantity"] = quantity
            self._refresh(select=index)

        def on_return(_event: tk.Event) -> str:
            commit(True)
            return "break"

        def on_escape(_event: tk.Event) -> str:
            commit(False)
            return "break"

        entry.bind("<Return>", on_return)
        entry.bind("<Escape>", on_escape)
        entry.bind("<FocusOut>", lambda _e: commit(False))
        return "break"

    def _remove_line(self) -> None:
        selection = self.tree.selection()
        if not selection:
            messagebox.showwarning(
                "Retirer", "Sélectionnez une ligne à retirer.", parent=self
            )
            return
        index = int(selection[0])
        line = self.lines[index]
        if not messagebox.askyesno(
            "Retirer la ligne",
            f"Retirer « {line['designation']} » de ce document ?",
            parent=self,
        ):
            return
        del self.lines[index]
        self._refresh(select=(min(index, len(self.lines) - 1) if self.lines else None))

    def _refresh_articles(self) -> None:
        for item in self.results.get_children():
            self.results.delete(item)
        self._articles.clear()
        rows = self.db.search_articles(self.category, self.search_var.get())
        for row in rows:
            article_id = int(row["id"])
            self._articles[article_id] = {
                "code": row["code"],
                "designation": row["designation"],
                "unit": row["unit"],
                "unit_price_ht": float(row["unit_price_ht"]),
            }
            self.results.insert(
                "", "end", iid=str(article_id),
                values=(
                    row["code"], row["designation"], row["unit"] or "—",
                    money(float(row["unit_price_ht"])),
                ),
            )
        children = self.results.get_children()
        if children:
            self.results.selection_set(children[0])
            self.results.focus(children[0])
            self.results.see(children[0])

    def _move_results(self, delta: int) -> str:
        items = self.results.get_children()
        if not items:
            return "break"
        selection = self.results.selection()
        if selection:
            index = max(0, min(len(items) - 1, items.index(selection[0]) + delta))
        else:
            index = 0 if delta > 0 else len(items) - 1
        iid = items[index]
        self.results.selection_set(iid)
        self.results.focus(iid)
        self.results.see(iid)
        return "break"

    def _add_article(self) -> None:
        selection = self.results.selection()
        if not selection:
            messagebox.showwarning(
                "Ajouter", "Sélectionnez un article dans la liste.", parent=self
            )
            return
        article_id = int(selection[0])
        article = self._articles.get(article_id)
        if article is None:
            return
        try:
            quantity = parse_quantity(self.qty_var.get())
        except (TypeError, ValueError):
            messagebox.showwarning(
                "Quantité", "Saisissez une quantité supérieure à zéro.", parent=self
            )
            return
        for index, line in enumerate(self.lines):
            if (
                line["code"] == article["code"]
                and line["designation"] == article["designation"]
                and line["unit"] == article["unit"]
            ):
                line["quantity"] = round(line["quantity"] + quantity, 4)
                self._refresh(select=index)
                self.qty_var.set("1")
                return
        self.lines.append(
            {
                "item_id": None,
                "category": self.category,
                "code": article["code"],
                "designation": article["designation"],
                "unit": article["unit"],
                "unit_price_ht": article["unit_price_ht"],
                "quantity": quantity,
            }
        )
        self._refresh(select=len(self.lines) - 1)
        self.qty_var.set("1")

    # ------------------------------------------------------------ enregistrement

    def _save(self) -> bool:
        if not self.lines:
            messagebox.showwarning(
                "Modification", "Le document doit contenir au moins une ligne.", parent=self
            )
            return False
        total_ht, tva_amount, total_ttc = compute_totals(self.lines)
        summary = self.db.exercice_summary(self.category, self.exercice_label)
        plafond = summary["plafond"]
        if plafond is not None:
            other = round(max(0.0, float(summary["consumed"]) - self.old_total), 2)
            if round(other + total_ht, 2) >= round(float(plafond), 2):
                messagebox.showerror(
                    "Plafond atteint",
                    "La modification est bloquée : elle atteint ou dépasse le "
                    f"plafond de l'exercice {exercice_display(self.exercice_label)} "
                    f"de la convention « {self.category} ».\n\n"
                    f"Consommé hors ce document : {money(other)}\n"
                    f"Ce document : {money(total_ht)}\n"
                    f"Plafond : {money(plafond)}\n\n"
                    "Aucune exception n'est possible : retirez des lignes ou "
                    "ouvrez un nouvel exercice.",
                    parent=self,
                )
                return False

        kept = sum(1 for line in self.lines if line["item_id"])
        added = len(self.lines) - kept
        removed = len(self.initial_ids) - kept
        if not messagebox.askyesno(
            "Confirmer la modification",
            f"Document {self.doc['number']} — liste « {self.category} », "
            f"exercice {exercice_display(self.exercice_label)}\n\n"
            f"Lignes : {len(self.initial_ids)} → {len(self.lines)}"
            f"{f'  (+{added})' if added else ''}{f'  (-{removed})' if removed else ''}\n"
            f"Total HT : {money(self.old_total)} → {money(total_ht)}\n"
            f"TVA {TVA_RATE * 100:g}% : {money(self.doc['tva_amount'] or 0)} → {money(tva_amount)}\n"
            f"Total TTC : {money(self.doc['total_ttc'] or 0)} → {money(total_ttc)}\n\n"
            "Le PDF et l'Excel du document seront régénérés.",
            parent=self,
        ):
            return False
        return self._write(total_ht, tva_amount, total_ttc)

    def _write(self, total_ht: float, tva_amount: float, total_ttc: float) -> bool:
        number = str(self.doc["number"])
        pdf_path = Path(self.doc["pdf_path"]) if self.doc["pdf_path"] else EXPORT_DIR / f"{number}.pdf"
        excel_path = (
            Path(self.doc["excel_path"]) if self.doc["excel_path"] else EXPORT_DIR / f"{number}.xlsx"
        )
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        temp_dir = EXPORT_DIR / ".tmp"
        temp_dir.mkdir(parents=True, exist_ok=True)
        token = uuid4().hex
        tmp_pdf = temp_dir / f"{number}.{token}.pdf"
        tmp_excel = temp_dir / f"{number}.{token}.xlsx"
        date_text = display_date(self.doc["created_at"])
        backups: list[tuple[Path, Path]] = []
        created: list[Path] = []
        try:
            build_pdf(
                tmp_pdf, number, date_text, self.category, self.lines,
                total_ht, TVA_RATE, tva_amount, total_ttc,
            )
            build_excel(
                tmp_excel, number, date_text, self.category, self.lines,
                total_ht, TVA_RATE, tva_amount, total_ttc,
            )
            for temporary, destination in ((tmp_pdf, pdf_path), (tmp_excel, excel_path)):
                destination.parent.mkdir(parents=True, exist_ok=True)
                if destination.exists():
                    backup = temp_dir / f"{destination.name}.{token}.bak"
                    shutil.copy2(destination, backup)
                    backups.append((backup, destination))
                else:
                    created.append(destination)
                temporary.replace(destination)
            self.db.update_document(
                self.document_id, self.lines, TVA_RATE,
                pdf_path=str(pdf_path), excel_path=str(excel_path),
            )
        except Exception as exc:
            for backup, destination in backups:
                try:
                    shutil.copy2(backup, destination)
                except OSError:
                    pass
            for path in created:
                path.unlink(missing_ok=True)
            self._cleanup_temp(temp_dir, token)
            messagebox.showerror(
                "Modification",
                f"Impossible d'enregistrer la modification.\n\n{exc}",
                parent=self,
            )
            return False
        self._cleanup_temp(temp_dir, token)
        self.saved = True
        messagebox.showinfo(
            "Document modifié",
            f"Document {number} modifié.\n\n"
            f"Total HT : {money(total_ht)}\n"
            f"TVA {TVA_RATE * 100:g}% : {money(tva_amount)}\n"
            f"Total TTC : {money(total_ttc)}\n\n"
            f"PDF : {pdf_path}\nExcel : {excel_path}",
            parent=self,
        )
        if self.on_saved:
            self.on_saved()
        self.destroy()
        return True

    @staticmethod
    def _cleanup_temp(temp_dir: Path, token: str) -> None:
        for path in temp_dir.glob(f"*{token}*"):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


def edit_document(
    parent: tk.Misc,
    db: Database,
    document_id: int,
    on_saved=None,
) -> bool:
    """Ouvre l'édition d'un document. Renvoie ``True`` si une modification a eu lieu."""
    editable, reason = db.document_editable(document_id)
    if not editable:
        messagebox.showwarning(
            "Lecture seule",
            f"Ce document ne peut pas être modifié.\n\n{reason}",
            parent=parent,
        )
        return False
    doc = db.get_document(document_id)
    if not doc:
        messagebox.showwarning(
            "Modification", "Document introuvable.", parent=parent
        )
        return False
    dialog = EditDocumentDialog(parent, db, doc, on_saved)
    parent.wait_window(dialog)
    return dialog.saved
