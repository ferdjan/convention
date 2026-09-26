"""Thèmes visuels (ttk) de l'application.

`build_style` construit les styles ttk à partir des jetons de couleur courants.
`apply_theme` bascule vers un autre thème **à chaud** : il met à jour les
dictionnaires partagés `COLORS` / `BUDGET_COLORS`, reconstruit les styles, puis
recolore les widgets `tk` (Label, Frame...) dont la couleur a été figée à la
construction. Les dialogues ouverts sont eux aussi traités, car on parcourt toute
la hiérarchie de widgets.
"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk

from app.config import (
    BUDGET_COLORS,
    COLORS,
    FONT_FAMILY as FONT,
    THEMES,
    THEME_BUDGET_TOKENS,
    THEME_TOKENS,
)

# Hauteur des lignes de tableau
ROW_HEIGHT = 32
# Barre de progression du budget annuel
BAR_THICKNESS = 14

# Nom du thème appliqué, mis à jour par apply_theme
_current_theme: str | None = None

# Options tk::* qui portent une couleur et peuvent être recalées à chaud
_TK_COLOR_OPTIONS = (
    "bg",
    "fg",
    "highlightbackground",
    "highlightcolor",
    "activebackground",
    "activeforeground",
    "selectbackground",
    "selectforeground",
    "insertbackground",
    "disabledforeground",
)
_TK_WIDGETS = ("Label", "Frame", "Canvas", "Button", "Entry", "Listbox", "Text")


def theme_names() -> list[str]:
    """Clés des thèmes déclarés, dans l'ordre d'affichage."""
    return list(THEMES)


def theme_label(name: str) -> str:
    return THEMES[name]["label"] if name in THEMES else name


def current_theme() -> str | None:
    return _current_theme


def validate_themes() -> list[str]:
    """Renvoie la liste des jetons manquants ou en trop dans chaque thème."""
    problems: list[str] = []
    for name, spec in THEMES.items():
        for kind, expected in (("colors", THEME_TOKENS), ("budget", THEME_BUDGET_TOKENS)):
            found = set(spec[kind])
            for missing in sorted(set(expected) - found):
                problems.append(f"{name}.{kind}: jeton manquant « {missing} »")
            for extra in sorted(found - set(expected)):
                problems.append(f"{name}.{kind}: jeton inconnu « {extra} »")
    return problems


def _restyle(widget: tk.Misc, mapping: dict[str, str]) -> None:
    """Reapplique aux widgets tk fils la correspondance de couleurs donnée.

    Les widgets ttk sont ignorés : leurs couleurs viennent des styles, que
    `build_style` vient de reconstruire.
    """
    for child in widget.winfo_children():
        if not isinstance(child, ttk.Widget) and child.__class__.__name__ in _TK_WIDGETS:
            for option in _TK_COLOR_OPTIONS:
                try:
                    current = child[option]
                except (tk.TclError, KeyError):
                    continue
                if isinstance(current, str):
                    replacement = mapping.get(current.lower())
                    if replacement is not None:
                        try:
                            child.configure(**{option: replacement})
                        except tk.TclError:
                            pass
        _restyle(child, mapping)


def apply_theme(root: tk.Misc, name: str) -> str:
    """Bascule l'interface sur le thème `name` et renvoie son libellé."""
    global _current_theme
    if name not in THEMES:
        raise KeyError(f"thème inconnu : {name!r}")
    spec = THEMES[name]

    previous = {key: COLORS.get(key) for key in spec["colors"]}
    previous.update({f"budget_{key}": BUDGET_COLORS.get(key) for key in spec["budget"]})

    COLORS.clear()
    COLORS.update(spec["colors"])
    BUDGET_COLORS.clear()
    BUDGET_COLORS.update(spec["budget"])

    # Correspondance « ancienne valeur -> nouvelle valeur » pour les widgets tk
    mapping: dict[str, str] = {}
    for key, old in previous.items():
        new = COLORS.get(key) or BUDGET_COLORS.get(key.removeprefix("budget_"))
        if old and new and old.lower() != new.lower():
            mapping[old.lower()] = new

    build_style(root)
    _restyle(root, mapping)
    _current_theme = name
    return spec["label"]


def build_style(root: tk.Misc) -> None:
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    c = COLORS
    root.configure(bg=c["bg"])

    style.configure(".", background=c["bg"], foreground=c["text"], font=(FONT, 10))
    style.configure("TFrame", background=c["bg"])
    style.configure("Card.TFrame", background=c["surface"])
    style.configure("TLabel", background=c["bg"], foreground=c["text"])
    style.configure("Card.TLabel", background=c["surface"], foreground=c["text"])
    style.configure("Muted.TLabel", background=c["bg"], foreground=c["muted"])
    style.configure("Title.TLabel", font=(FONT, 18, "bold"), background=c["primary"], foreground=c["on_primary"])
    style.configure("Subtitle.TLabel", font=(FONT, 10), background=c["primary"], foreground=c["on_primary_muted"])
    style.configure("Section.TLabel", font=(FONT, 11, "bold"), background=c["bg"], foreground=c["accent"])

    # Libellés de la synthèse des montants : taille uniforme et modérée.
    style.configure("TotalLabel.TLabel", font=(FONT, 9, "bold"), background=c["surface"], foreground=c["muted"])
    style.configure("TotalValue.TLabel", font=(FONT, 11, "bold"), background=c["surface"], foreground=c["text"])
    style.configure("TotalTTCLabel.TLabel", font=(FONT, 9, "bold"), background=c["surface"], foreground=c["accent"])
    style.configure("TotalTTCValue.TLabel", font=(FONT, 11, "bold"), background=c["surface"], foreground=c["accent"])

    style.configure("TLabelframe", background=c["bg"], bordercolor=c["border"], relief="solid", borderwidth=1)
    style.configure("TLabelframe.Label", background=c["bg"], foreground=c["accent"], font=(FONT, 10, "bold"))

    style.configure(
        "TButton", padding=(14, 8), font=(FONT, 10),
        background=c["surface"], foreground=c["text"], borderwidth=1, focusthickness=0,
    )
    style.map(
        "TButton",
        background=[("active", c["stripe"]), ("pressed", c["border"])],
        foreground=[("disabled", c["muted"])],
    )
    style.configure(
        "Accent.TButton", background=c["accent"], foreground=c["on_accent"],
        font=(FONT, 10, "bold"), padding=(18, 10), borderwidth=0,
    )
    style.map(
        "Accent.TButton",
        background=[("active", c["accent_hover"]), ("pressed", c["accent_light"])],
        foreground=[("disabled", c["muted"])],
    )
    style.configure(
        "Danger.TButton", background=c["surface"], foreground=c["danger"],
        font=(FONT, 10, "bold"), padding=(14, 8), borderwidth=1, bordercolor=c["border"],
    )
    style.map(
        "Danger.TButton",
        background=[("active", c["danger_hover"]), ("pressed", c["danger_pressed"])],
    )

    style.configure(
        "Treeview", background=c["surface"], fieldbackground=c["surface"],
        foreground=c["text"], rowheight=ROW_HEIGHT, borderwidth=0, font=(FONT, 9),
    )
    style.map(
        "Treeview",
        background=[("selected", c["accent"])],
        foreground=[("selected", c["on_accent"])],
    )
    style.configure(
        "Treeview.Heading", background=c["primary"], foreground=c["on_primary"],
        font=(FONT, 9, "bold"), relief="flat", padding=(8, 8),
    )
    style.map("Treeview.Heading", background=[("active", c["border_strong"])])

    style.configure("TNotebook", background=c["bg"], borderwidth=0, tabmargins=(18, 8, 18, 0))
    style.configure(
        "TNotebook.Tab", background=c["bg"], foreground=c["muted"],
        padding=(32, 13), font=(FONT, 10, "bold"),
        borderwidth=0, focusthickness=0, relief="flat",
        lightcolor=c["bg"], darkcolor=c["bg"], bordercolor=c["bg"],
    )
    style.map(
        "TNotebook.Tab",
        background=[("selected", c["accent"]), ("active", c["surface"])],
        foreground=[("selected", c["on_accent"]), ("active", c["text"])],
        lightcolor=[("selected", c["accent"])],
        darkcolor=[("selected", c["accent"])],
        bordercolor=[("selected", c["accent"])],
    )

    for widget in ("TEntry", "TCombobox", "TSpinbox"):
        style.configure(
            widget, fieldbackground=c["surface"], background=c["surface"],
            foreground=c["text"], insertcolor=c["text"], padding=6,
        )
    style.map("TCombobox", fieldbackground=[("readonly", c["surface"])])
    # Liste déroulante des combobox (thème clam)
    style.configure(
        "ComboboxPopdown.TFrame", background=c["surface"],
    )

    # Jauge du budget annuel : une couleur selon l'état
    for name, color in (
        ("BudgetOk", BUDGET_COLORS["ok"]),
        ("BudgetWarn", BUDGET_COLORS["warn"]),
        ("BudgetCritical", BUDGET_COLORS["critical"]),
        ("BudgetOver", BUDGET_COLORS["over"]),
    ):
        style.configure(
            f"{name}.Horizontal.TProgressbar",
            troughcolor=c["stripe"], background=color,
            lightcolor=color, darkcolor=color, bordercolor=c["surface"], thickness=BAR_THICKNESS,
        )
