"""Gestion des conventions : statut, exercices et clôture d'exercice.

Chaque convention possède des exercices annuels (périodes configurables,
ex. 15-08-2026 → 14-08-2027) avec un plafond propre. Un seul exercice est
actif à la fois ; la clôture archive le cumul (consommé/reste) et le reste
repart à zéro au nouvel exercice.
"""
from __future__ import annotations

import tkinter as tk
from datetime import datetime, timedelta
from tkinter import messagebox, ttk

from app.config import COLORS, FONT_FAMILY as FONT
from app.database import Database
from app.ui.common import money


def _parse_date(value: str, field: str) -> str:
    value = (value or "").strip()
    try:
        parsed = datetime.strptime(value, "%Y-%m-%d")
    except ValueError:
        raise ValueError(f"Date {field} invalide (format attendu AAAA-MM-JJ).") from None
    return parsed.date().isoformat()


def _parse_amount(value: str) -> float | None:
    """Montant du plafond : vide = illimité, 0 = supprimé (illimité)."""
    raw = value.strip().replace(" ", "").replace("\u00a0", "").replace(",", ".")
    if not raw:
        return None
    try:
        amount = float(raw)
    except ValueError:
        raise ValueError("Montant du plafond invalide.") from None
    return amount if amount > 0 else None


def edit_exercice(
    parent: tk.Misc,
    db: Database,
    category: str,
    exercice: dict | None,
    on_done=None,
) -> None:
    """Création ou édition d'un exercice (dates, plafond)."""
    win = tk.Toplevel(parent)
    win.title("Nouvel exercice" if exercice is None else f"Exercice {exercice['label']}")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    ttk.Label(win, text=f"Convention : {category}", style="Section.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8)
    )

    ttk.Label(win, text="Libellé (ex. 2026-2027) :").grid(row=1, column=0, sticky="w", padx=14, pady=4)
    label_var = tk.StringVar(value=exercice["label"] if exercice else "")
    label_entry = ttk.Entry(win, textvariable=label_var, width=20)
    label_entry.grid(row=1, column=1, sticky="w", padx=(0, 14), pady=4)
    if exercice is not None:
        label_entry.configure(state="readonly")

    ttk.Label(win, text="Début (AAAA-MM-JJ) :").grid(row=2, column=0, sticky="w", padx=14, pady=4)
    start_var = tk.StringVar(value=exercice["start_date"] if exercice else "")
    ttk.Entry(win, textvariable=start_var, width=16).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Fin (AAAA-MM-JJ) :").grid(row=3, column=0, sticky="w", padx=14, pady=4)
    end_var = tk.StringVar(value=exercice["end_date"] if exercice else "")
    ttk.Entry(win, textvariable=end_var, width=16).grid(row=3, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Plafond (vide = illimité) :").grid(row=4, column=0, sticky="w", padx=14, pady=4)
    plafond_var = tk.StringVar(
        value="" if exercice is None or exercice["plafond"] is None else f"{exercice['plafond']:g}"
    )
    ttk.Entry(win, textvariable=plafond_var, width=16).grid(row=4, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(
        win,
        text="Un seul exercice actif par convention. La création d'un exercice\n"
             "alors qu'un autre est actif propose de clôturer l'existant.",
        style="Muted.TLabel",
    ).grid(row=5, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 0))

    def validate() -> None:
        try:
            label = label_var.get().strip()
            start = _parse_date(start_var.get(), "de début")
            end = _parse_date(end_var.get(), "de fin")
            plafond = _parse_amount(plafond_var.get())
        except ValueError as exc:
            messagebox.showwarning("Exercice", str(exc), parent=win)
            return
        try:
            if exercice is None:
                db.create_exercice(category, label, start, end, plafond)
            else:
                db.update_exercice(
                    category, exercice["label"],
                    start_date=start, end_date=end, plafond=plafond,
                )
        except ValueError as exc:
            messagebox.showwarning("Exercice", str(exc), parent=win)
            return
        win.destroy()
        if on_done:
            on_done()

    actions = ttk.Frame(win)
    actions.grid(row=6, column=0, columnspan=2, sticky="e", padx=14, pady=14)
    ttk.Button(actions, text="Enregistrer", style="Accent.TButton", command=validate).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)


def ask_open_exercice(
    parent: tk.Misc,
    db: Database,
    category: str,
    on_done=None,
) -> None:
    """Ouverture d'un nouvel exercice : clôture de l'actif puis création.

    Pré-remplit le libellé et les dates à partir de l'exercice actif
    (période glissante d'un an) pour enchaîner les exercices.
    """
    current = db.get_active_exercice(category)
    win = tk.Toplevel(parent)
    win.title("Ouvrir un nouvel exercice")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)

    if current:
        try:
            next_start = datetime.fromisoformat(
                current["end_date"]
            ).date() + timedelta(days=1)
        except (ValueError, TypeError):
            next_start = datetime.now().date()
        suggested_start = next_start.isoformat()
        suggested_end = (
            next_start.replace(year=next_start.year + 1) - timedelta(days=1)
        ).isoformat()
        suggested_label = f"{next_start.year}-{suggested_end[:4]}"
        current_info = (
            f"Exercice actif : {current['label']} ({current['start_date']} → {current['end_date']})\n"
            "Il sera clôturé : son cumul (consommé / reste) est archivé et le\n"
            "reste ne se reporte pas sur le nouvel exercice."
        )
    else:
        suggested_start = datetime.now().date().isoformat()
        suggested_end = f"{datetime.now().year}-12-31"
        suggested_label = str(datetime.now().year)
        current_info = "Aucun exercice actif pour cette convention."

    ttk.Label(win, text=current_info, style="Muted.TLabel", justify="left").grid(
        row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8)
    )

    ttk.Label(win, text="Libellé (ex. 2026-2027) :").grid(row=1, column=0, sticky="w", padx=14, pady=4)
    label_var = tk.StringVar(value=suggested_label)
    ttk.Entry(win, textvariable=label_var, width=20).grid(row=1, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Début (AAAA-MM-JJ) :").grid(row=2, column=0, sticky="w", padx=14, pady=4)
    start_var = tk.StringVar(value=suggested_start)
    ttk.Entry(win, textvariable=start_var, width=16).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Fin (AAAA-MM-JJ) :").grid(row=3, column=0, sticky="w", padx=14, pady=4)
    end_var = tk.StringVar(value=suggested_end)
    ttk.Entry(win, textvariable=end_var, width=16).grid(row=3, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Plafond (vide = illimité) :").grid(row=4, column=0, sticky="w", padx=14, pady=4)
    plafond_var = tk.StringVar(value="")
    ttk.Entry(win, textvariable=plafond_var, width=16).grid(row=4, column=1, sticky="w", padx=(0, 14), pady=4)

    def validate() -> None:
        try:
            label = label_var.get().strip()
            start = _parse_date(start_var.get(), "de début")
            end = _parse_date(end_var.get(), "de fin")
            plafond = _parse_amount(plafond_var.get())
        except ValueError as exc:
            messagebox.showwarning("Exercice", str(exc), parent=win)
            return
        if db.exercice_exists(category, label):
            messagebox.showwarning("Exercice", f"L'exercice « {label} » existe déjà.", parent=win)
            return
        try:
            db.create_exercice(category, label, start, end, plafond, close_current=True)
        except ValueError as exc:
            messagebox.showwarning("Exercice", str(exc), parent=win)
            return
        win.destroy()
        if on_done:
            on_done()
        messagebox.showinfo(
            "Exercice",
            f"Exercice « {label} » ouvert pour « {category} ».\n"
            "Le cumul de l'exercice précédent est archivé ; le reste repart à zéro.",
        )

    actions = ttk.Frame(win)
    actions.grid(row=5, column=0, columnspan=2, sticky="e", padx=14, pady=14)
    ttk.Button(actions, text="Clôturer l'actif et ouvrir", style="Accent.TButton", command=validate).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)


def close_exercice_dialog(
    parent: tk.Misc,
    db: Database,
    category: str,
    label: str,
    on_done=None,
) -> None:
    """Clôture d'un exercice avec affichage du cumul archivé."""
    summary = db.exercice_summary(category, label)
    win = tk.Toplevel(parent)
    win.title("Clôture d'exercice")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    info = "\n".join([
        f"Convention : {category}",
        f"Exercice : {label}",
        f"Période : {summary['start_date']} → {summary['end_date']}",
        f"Plafond : {'illimité' if summary['plafond'] is None else money(summary['plafond'])}",
        f"Consommé : {money(summary['consumed'])}",
        f"Reste : {'—' if summary['remaining'] is None else money(summary['remaining'])}",
    ])
    ttk.Label(
        win, text=info, background=COLORS["surface"], foreground=COLORS["text"],
        justify="left", font=(FONT, 10),
    ).grid(row=0, column=0, sticky="w", padx=14, pady=(14, 10))
    ttk.Label(
        win,
        text="Le cumul (consommé / reste) est archivé. Le reste ne se reporte pas :\n"
             "ouvrez un nouvel exercice pour repartir de zéro. L'historique des\n"
             "documents de l'exercice est conservé et consultable.",
        style="Muted.TLabel", justify="left",
    ).grid(row=1, column=0, sticky="w", padx=14, pady=(0, 10))

    def validate() -> None:
        try:
            result = db.close_exercice(category, label)
        except ValueError as exc:
            messagebox.showwarning("Clôture", str(exc), parent=win)
            return
        win.destroy()
        if on_done:
            on_done()
        messagebox.showinfo(
            "Clôture",
            f"Exercice « {label} » clôturé pour « {category} ».\n"
            f"Consommé archivé : {money(result['consumed'])}\n"
            f"Reste archivé : {'—' if result['remaining'] is None else money(result['remaining'])}",
        )

    actions = ttk.Frame(win)
    actions.grid(row=2, column=0, sticky="e", padx=14, pady=(0, 14))
    ttk.Button(actions, text="Clôturer", style="Accent.TButton", command=validate).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)


def edit_convention_status(
    parent: tk.Misc,
    db: Database,
    name: str,
    on_done=None,
) -> None:
    """Statut d'une convention : active, clôturée, ou expirée (via échéance)."""
    win = tk.Toplevel(parent)
    win.title("Statut de la convention")
    win.configure(bg=COLORS["bg"])
    win.transient(parent)
    win.grab_set()
    win.resizable(False, False)
    raw = db.category_raw(name)
    ttk.Label(win, text=f"Convention : {name}", style="Section.TLabel").grid(
        row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8)
    )
    ttk.Label(win, text="Statut :").grid(row=1, column=0, sticky="w", padx=14, pady=4)
    current = (raw["status"] if raw and raw["status"] else "active")
    status_var = tk.StringVar(value="active" if current == "active" else "closed")
    ttk.Combobox(
        win, textvariable=status_var, state="readonly", width=22,
        values=["active", "closed"],
    ).grid(row=1, column=1, sticky="w", padx=(0, 14), pady=4)

    ttk.Label(win, text="Échéance (AAAA-MM-JJ) :").grid(row=2, column=0, sticky="w", padx=14, pady=4)
    expiry_var = tk.StringVar(value=(raw["expiry_date"] or "") if raw else "")
    ttk.Entry(win, textvariable=expiry_var, width=22).grid(row=2, column=1, sticky="w", padx=(0, 14), pady=4)
    ttk.Label(
        win,
        text="Une convention clôturée ne reçoit plus de documents.\n"
             "Une convention active dont l'échéance est dépassée devient « expirée » :\n"
             "elle ne reçoit plus de documents non plus. Laissez vide pour ne pas fixer d'échéance.",
        style="Muted.TLabel", justify="left",
    ).grid(row=3, column=0, columnspan=2, sticky="w", padx=14, pady=(6, 0))

    def validate() -> None:
        expiry = expiry_var.get().strip() or None
        if expiry:
            try:
                datetime.strptime(expiry, "%Y-%m-%d")
            except ValueError:
                messagebox.showwarning(
                    "Statut", "Échéance invalide (format attendu AAAA-MM-JJ).", parent=win
                )
                return
        db.set_category_status(name, status_var.get(), expiry)
        win.destroy()
        if on_done:
            on_done()

    actions = ttk.Frame(win)
    actions.grid(row=4, column=0, columnspan=2, sticky="e", padx=14, pady=14)
    ttk.Button(actions, text="Enregistrer", style="Accent.TButton", command=validate).pack(side="right")
    ttk.Button(actions, text="Annuler", command=win.destroy).pack(side="right", padx=8)
    parent.wait_window(win)


def manage_conventions(parent: tk.Misc, db: Database) -> None:
    win = tk.Toplevel(parent)
    win.title("Conventions — exercices et plafonds")
    win.configure(bg=COLORS["bg"])
    win.geometry("980x560")
    win.minsize(800, 460)
    win.transient(parent)

    top = ttk.Frame(win, padding=(14, 12, 14, 4))
    top.pack(fill="x")
    ttk.Label(top, text="Convention :").pack(side="left")
    conv_var = tk.StringVar()
    conv_combo = ttk.Combobox(top, textvariable=conv_var, state="readonly", width=24)
    conv_combo.pack(side="left", padx=6)
    names = db.category_names()
    if names:
        conv_var.set(names[0])
    conv_combo.configure(values=names)
    ttk.Label(
        top,
        text="Sélectionnez une convention pour gérer ses exercices.",
        style="Muted.TLabel",
    ).pack(side="left", padx=16)

    table = ttk.Frame(win, padding=(14, 8, 14, 0))
    table.pack(fill="both", expand=True)
    cols = ("label", "periode", "plafond", "consomme", "reste", "status")
    tree = ttk.Treeview(table, columns=cols, show="headings", selectmode="browse")
    for c, h, w in (
        ("label", "Exercice", 110),
        ("periode", "Période", 200),
        ("plafond", "Plafond", 130),
        ("consomme", "Consommé", 130),
        ("reste", "Reste", 130),
        ("status", "Statut", 110),
    ):
        tree.heading(c, text=h)
        tree.column(c, width=w, anchor="center" if c != "label" else "w")
    vs = ttk.Scrollbar(table, orient="vertical", command=tree.yview)
    vs.pack(side="right", fill="y")
    tree.configure(yscrollcommand=vs.set)
    tree.pack(fill="both", expand=True)

    def current_convention() -> str | None:
        name = conv_var.get().strip()
        return name or None

    def load() -> None:
        name = current_convention()
        for item in tree.get_children():
            tree.delete(item)
        if not name:
            return
        for row in db.list_exercices(name):
            if row["status"] == "active":
                summary = db.exercice_summary(name, row["label"])
                plafond = summary["plafond"]
                consumed = summary["consumed"]
                remaining = summary["remaining"]
                status_text = "Actif"
            else:
                plafond = row["plafond"]
                consumed = row["consumed_at_close"]
                remaining = row["remaining_at_close"]
                status_text = "Clôturé"
            tree.insert(
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

    def selected_label() -> str | None:
        sel = tree.selection()
        if not sel:
            return None
        return sel[0]

    def on_convention_change(_event=None) -> None:
        load()

    def new_exercice() -> None:
        name = current_convention()
        if not name:
            messagebox.showwarning("Conventions", "Sélectionnez une convention.", parent=win)
            return
        if db.get_active_exercice(name):
            ask_open_exercice(win, db, name, load)
        else:
            edit_exercice(win, db, name, None, load)

    def edit_selected() -> None:
        name = current_convention()
        label = selected_label()
        if not name or not label:
            messagebox.showwarning("Conventions", "Sélectionnez un exercice.", parent=win)
            return
        row = db.get_exercice(name, label)
        edit_exercice(
            win, db, name,
            {
                "label": row["label"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "plafond": row["plafond"],
            },
            load,
        )

    def close_selected() -> None:
        name = current_convention()
        label = selected_label()
        if not name or not label:
            messagebox.showwarning("Conventions", "Sélectionnez un exercice.", parent=win)
            return
        row = db.get_exercice(name, label)
        if row["status"] != "active":
            messagebox.showinfo("Conventions", "Cet exercice est déjà clôturé.", parent=win)
            return
        close_exercice_dialog(win, db, name, label, load)

    def change_status() -> None:
        name = current_convention()
        if not name:
            messagebox.showwarning("Conventions", "Sélectionnez une convention.", parent=win)
            return
        edit_convention_status(win, db, name, load)

    conv_combo.bind("<<ComboboxSelected>>", on_convention_change)
    tree.bind("<Double-1>", lambda e: edit_selected())

    actions = ttk.Frame(win, padding=14)
    actions.pack(fill="x")
    ttk.Button(actions, text="Changer le statut de la convention...", command=change_status).pack(side="right")
    ttk.Button(
        actions, text="Clôturer l'exercice sélectionné",
        command=close_selected,
    ).pack(side="right", padx=8)
    ttk.Button(actions, text="Modifier l'exercice...", command=edit_selected).pack(side="right", padx=8)
    ttk.Button(
        actions, text="Ouvrir un nouvel exercice...",
        style="Accent.TButton", command=new_exercice,
    ).pack(side="right", padx=8)
    ttk.Button(actions, text="Fermer", command=win.destroy).pack(side="left")

    load()
    parent.wait_window(win)
