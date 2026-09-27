"""Fenêtre principale : barre latérale, en-tête et orchestration des écrans.

La logique d'écran est répartie entre :
- ``app.ui.views.dashboard``   : synthèse des conventions (accueil) ;
- ``app.ui.views.document``    : saisie d'un document ;
- ``app.ui.views.history``     : historique des documents ;
- ``app.ui.views.conventions`` : gestion des conventions et exercices ;
- ``app.ui.views.reports``     : rapport de consommation ;
- ``app.ui.views.settings``    : thème et à propos ;
- ``app.ui.theme`` / ``app.ui.common`` : style ttk et utilitaires partagés.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import filedialog, messagebox

from app.config import (
    APP_NAME,
    COLORS,
    DB_PATH,
    DEFAULT_THEME,
    EXPORT_DIR,
    FONT_FAMILY as FONT,
    SEED_XLSX,
)
from app.database import Database
from app.services.importer import import_articles, read_sheet_names, write_template
from app.ui import dialogs
from app.ui.theme import apply_theme, build_style, current_theme
from app.ui.views.conventions import ConventionsView
from app.ui.views.dashboard import DashboardView
from app.ui.views.document import DocumentView
from app.ui.views.history import HistoryView
from app.ui.views.reports import ReportsView
from app.ui.views.settings import SettingsView

# Écrans de l'application, dans l'ordre de la barre latérale.
NAV_ITEMS = (
    ("dashboard", "Tableau de bord"),
    ("document", "Nouveau document"),
    ("history", "Historique"),
    ("conventions", "Conventions"),
    ("reports", "Rapport de consommation"),
    ("settings", "Paramètres"),
)

SCREEN_SUBTITLES = {
    "dashboard": "Vue d'ensemble des conventions et de leurs exercices.",
    "document": "Composez une commande d'articles et enregistrez-la.",
    "history": "Consultez, exportez et supprimez les commandes enregistrées.",
    "conventions": "Gérez les conventions, leurs exercices et leurs plafonds.",
    "reports": "Exportez le rapport de consommation d'un exercice en Excel.",
    "settings": "Thème, taux de TVA et informations.",
}


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_NAME)
        self.minsize(1080, 640)
        self._apply_geometry()
        self.db = Database(DB_PATH)
        self._cleanup_export_temp()
        build_style(self)
        self._active_screen = "dashboard"
        self._build_sidebar()
        self._build_main()
        self._build_views()
        self.document.load_categories()
        self._ensure_seed_data()
        self.document.new_document()
        self.dashboard.refresh()
        self.conventions.load()
        self.reports.refresh()
        self.show_screen("dashboard")

    # ------------------------------------------------------------------ chrome

    def _apply_geometry(self) -> None:
        """Dimensionne la fenêtre pour qu'elle tienne dans l'écran.

        Évite que le pied de page (totaux, bouton Enregistrer) soit coupé par
        la barre des tâches quand l'écran est plus petit que la taille idéale.
        """
        self.update_idletasks()
        sw = self.winfo_screenwidth()
        sh = self.winfo_screenheight()
        width = min(1400, max(1080, sw - 40))
        height = min(880, max(640, sh - 70))
        x = max(0, (sw - width) // 2)
        y = max(0, (sh - height) // 3)
        self.geometry(f"{width}x{height}+{x}+{y}")

    def current_theme_name(self) -> str:
        return current_theme() or DEFAULT_THEME

    def set_theme(self, name: str) -> None:
        """Bascule l'interface sur un autre thème, sans redémarrer."""
        try:
            apply_theme(self, name)
        except KeyError:
            return
        self._refresh_sidebar_colors()
        self._refresh_header_colors()
        self.document.refresh_budget_panel()
        self.history.refresh_preserving_selection()
        if self._active_screen == "dashboard":
            self.dashboard.refresh()
        self._update_theme_toggle_label()

    def toggle_dark(self) -> None:
        """Bascule clair <-> nuit en un clic."""
        current = self.current_theme_name()
        self.set_theme("nuit" if current != "nuit" else "clair")

    # ------------------------------------------------------------ barre latérale

    def _build_sidebar(self) -> None:
        self.sidebar = tk.Frame(self, bg=COLORS["sidebar"], width=236)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        brand = tk.Frame(self.sidebar, bg=COLORS["sidebar"])
        brand.pack(fill="x", pady=(22, 18))
        tk.Label(
            brand, text=APP_NAME, bg=COLORS["sidebar"], fg=COLORS["on_primary"],
            font=(FONT, 15, "bold"),
        ).pack(anchor="w", padx=22)
        tk.Label(
            brand, text="Conventions & commandes",
            bg=COLORS["sidebar"], fg=COLORS["on_primary_muted"], font=(FONT, 9),
        ).pack(anchor="w", padx=22)

        self._nav_buttons: dict[str, tk.Button] = {}
        for key, label in NAV_ITEMS:
            btn = tk.Button(
                self.sidebar,
                text=label,
                command=lambda k=key: self.show_screen(k),
                bg=COLORS["sidebar"], fg=COLORS["on_primary_muted"],
                activebackground=COLORS["sidebar_hover"],
                activeforeground=COLORS["on_primary"],
                font=(FONT, 10),
                anchor="w", padx=22, pady=11,
                relief="flat", bd=0, highlightthickness=0, cursor="hand2",
            )
            btn.pack(fill="x")
            self._nav_buttons[key] = btn

        # Bascule clair / sombre en pied de barre.
        self.theme_toggle = tk.Button(
            self.sidebar,
            text="",
            command=self.toggle_dark,
            bg=COLORS["sidebar"], fg=COLORS["on_primary_muted"],
            activebackground=COLORS["sidebar_hover"],
            activeforeground=COLORS["on_primary"],
            font=(FONT, 10),
            anchor="w", padx=22, pady=11,
            relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        self.theme_toggle.pack(fill="x", side="bottom")
        self._update_theme_toggle_label()
        self._refresh_sidebar_colors()

    def _update_theme_toggle_label(self) -> None:
        dark = self.current_theme_name() == "nuit"
        self.theme_toggle.configure(text="Mode clair" if dark else "Mode sombre")

    def _refresh_sidebar_colors(self) -> None:
        for key, btn in self._nav_buttons.items():
            if key == self._active_screen:
                btn.configure(
                    bg=COLORS["accent"], fg=COLORS["on_accent"],
                    activebackground=COLORS["accent_hover"],
                    activeforeground=COLORS["on_accent"],
                )
            else:
                btn.configure(
                    bg=COLORS["sidebar"], fg=COLORS["on_primary_muted"],
                    activebackground=COLORS["sidebar_hover"],
                    activeforeground=COLORS["on_primary"],
                )
        self.sidebar.configure(bg=COLORS["sidebar"])
        self.theme_toggle.configure(
            bg=COLORS["sidebar"], fg=COLORS["on_primary_muted"],
            activebackground=COLORS["sidebar_hover"],
            activeforeground=COLORS["on_primary"],
        )

    # ------------------------------------------------------------------- main

    def _build_main(self) -> None:
        self.main = tk.Frame(self, bg=COLORS["bg"])
        self.main.pack(side="left", fill="both", expand=True)

        self.header = tk.Frame(self.main, bg=COLORS["bg"])
        self.header.pack(fill="x", padx=28, pady=(22, 0))
        self.title_var = tk.StringVar()
        self.subtitle_var = tk.StringVar()
        title_box = tk.Frame(self.header, bg=COLORS["bg"])
        title_box.pack(side="left")
        tk.Label(
            title_box, textvariable=self.title_var, bg=COLORS["bg"],
            fg=COLORS["text"], font=(FONT, 20, "bold"),
        ).pack(anchor="w")
        tk.Label(
            title_box, textvariable=self.subtitle_var, bg=COLORS["bg"],
            fg=COLORS["muted"], font=(FONT, 10),
        ).pack(anchor="w", pady=(2, 0))
        help_btn = tk.Button(
            self.header, text="?  Format Excel",
            command=lambda: self.show_excel_format(None),
            bg=COLORS["bg"], fg=COLORS["accent"],
            activebackground=COLORS["bg"], activeforeground=COLORS["accent_hover"],
            font=(FONT, 9), relief="flat", bd=0, highlightthickness=0, cursor="hand2",
        )
        help_btn.pack(side="right", pady=(8, 0))

        self.content = tk.Frame(self.main, bg=COLORS["bg"])
        self.content.pack(fill="both", expand=True, padx=28, pady=(18, 6))
        self.content.rowconfigure(0, weight=1)
        self.content.columnconfigure(0, weight=1)

    def _refresh_header_colors(self) -> None:
        self.header.configure(bg=COLORS["bg"])
        self.main.configure(bg=COLORS["bg"])
        self.content.configure(bg=COLORS["bg"])
        for child in self.header.winfo_children():
            if isinstance(child, tk.Label):
                child.configure(bg=COLORS["bg"])

    def _build_views(self) -> None:
        self.dashboard = DashboardView(self.content, self)
        self.document = DocumentView(self.content, self)
        self.history = HistoryView(self.content, self)
        self.conventions = ConventionsView(self.content, self)
        self.reports = ReportsView(self.content, self)
        self.settings = SettingsView(self.content, self)

        self.dashboard.build()
        self.document.build()
        self.history.build()
        self.conventions.build()
        self.reports.build()
        self.settings.build()

        self._screens = {
            "dashboard": self.dashboard,
            "document": self.document,
            "history": self.history,
            "conventions": self.conventions,
            "reports": self.reports,
            "settings": self.settings,
        }
        for view in self._screens.values():
            view.grid(row=0, column=0, sticky="nsew")

    # -------------------------------------------------------------- navigation

    def show_screen(self, name: str) -> None:
        if name not in self._screens:
            return
        self._active_screen = name
        self._screens[name].tkraise()
        self.title_var.set(dict(NAV_ITEMS)[name])
        self.subtitle_var.set(SCREEN_SUBTITLES.get(name, ""))
        self._refresh_sidebar_colors()
        # Rafraîchit les données des écrans qui en dépendent.
        if name == "dashboard":
            self.dashboard.refresh()
        elif name == "conventions":
            self.conventions.refresh()
        elif name == "reports":
            self.reports.refresh()
        elif name == "history":
            self.history.refresh()

    def open_document_for(self, category: str) -> None:
        """Ouvre l'écran de saisie avec une convention présélectionnée."""
        self.show_screen("document")
        if category in self.db.active_category_names():
            self.document.category_var.set(category)
            self.document.current_exercice = self.document._load_exercice(category)
            self.document.number_var.set(self.document.next_free_document_number(category))
            self.document.refresh_articles()
            self.document.refresh_budget_panel()
            self.document.refresh_category_status()

    # ----------------------------------------------------------------- startup

    def _ensure_seed_data(self):
        if self.db.article_count() > 0:
            return
        if SEED_XLSX.exists():
            try:
                rows = import_articles(SEED_XLSX)
                self.db.replace_articles(rows)
            except Exception as exc:
                messagebox.showerror("Import initial", f"Impossible d'importer les listes initiales.\n\n{exc}")

    @staticmethod
    def _cleanup_export_temp() -> None:
        temp_dir = EXPORT_DIR / ".tmp"
        if not temp_dir.is_dir():
            return
        for path in temp_dir.iterdir():
            if path.is_file():
                path.unlink(missing_ok=True)

    # ---------------------------------------------------------------- dialogues

    def _after_categories_changed(self) -> None:
        self.document.load_categories()
        self.document.refresh_articles()
        self.document.refresh_budget_panel()
        self.dashboard.refresh()
        self.conventions.load()

    def delete_list(self) -> None:
        dialogs.delete_list(self, self.db, self._after_categories_changed)

    def show_excel_format(self, categories: list[str] | None = None) -> None:
        dialogs.show_excel_format(categories)

    # ------------------------------------------------------------------ import

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

        target = dialogs.ask_import_target(self, sheets)
        if not target:
            return
        sheet, name = target["sheet"], target["name"].strip()
        if not name:
            messagebox.showwarning("Import", "Le nom de liste ne peut pas être vide.")
            return
        canonical = self.db.resolve_category_name(name)
        is_new = canonical is None
        if canonical:
            name = canonical
        if not is_new and not messagebox.askyesno(
            "Remplacer",
            f"La liste « {name} » existe déjà.\n\nRemplacer ses articles par ceux de la feuille « {sheet} » ?",
        ):
            return

        try:
            rows = import_articles(path, {name: sheet})
            if not rows:
                raise ValueError(f"Aucune donnée exploitable dans la feuille « {sheet} ».")
        except Exception as exc:
            messagebox.showerror("Import Excel", str(exc))
            return

        try:
            result = self.db.replace_articles_by_category(rows)
        except Exception as exc:
            messagebox.showerror("Import Excel", str(exc))
            return

        self.document.load_categories()
        switched = False
        if not self.document.cart:
            self.document.category_var.set(name)
            self.document.current_exercice = self.document._load_exercice(name)
            self.document.number_var.set(self.document.next_free_document_number(name))
            switched = True
        self.document.refresh_articles()
        self.document.refresh_budget_panel()
        message = f"{result['imported']} articles importés dans la liste « {name} »."
        if self.document.cart and not switched and name != self.document.cart_category:
            message += f"\n\nLe document en cours reste rattaché à « {self.document.cart_category} »."
        self._after_categories_changed()
        messagebox.showinfo("Import terminé", message)


def run() -> None:
    try:
        app = App()
    except Exception as exc:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror(
            "Démarrage impossible",
            "La base de données n'a pas pu être ouverte ou migrée.\n\n"
            f"{exc}\n\nLa migration est annulée automatiquement en cas d'erreur. "
            "Conservez une sauvegarde avant toute intervention.",
            parent=root,
        )
        root.destroy()
        return
    app.mainloop()


__all__ = ["App", "run"]
