from __future__ import annotations

import getpass
import sys
from pathlib import Path

APP_NAME = "Gestion Articles"

# Données utilisateur et ressources : à côté de l'exécutable une fois empaqueté
# (PyInstaller), sinon à la racine du projet en développement. Ainsi, la base
# `gestion_articles.db` et le dossier `documents_pdf` restent à côté de l'exe
# (facilement sauvegardables), tandis que `source_listes.xlsx` est lu depuis les
# ressources embarquées.
if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parent.parent
    BUNDLE_DIR = BASE_DIR

DB_PATH = BASE_DIR / "gestion_articles.db"
EXPORT_DIR = BASE_DIR / "documents_pdf"
SEED_XLSX = BUNDLE_DIR / "source_listes.xlsx"
try:
    CURRENT_USER = getpass.getuser()
except Exception:
    CURRENT_USER = "user"

TVA_RATE = 0.19

BUDGET_WARN = 0.80
BUDGET_CRITICAL = 0.90
# Blocage ferme : un document est refusé dès que le cumul atteint le plafond
# (égalité incluse). Pour autoriser l'égalité exacte, passer à une comparaison
# stricte au point de contrôle unique (Database.save_document + vue document).
BUDGET_BLOCK = 1.0

DEFAULT_CATEGORIES = ("Informatique", "Bureautique")
DEFAULT_PREFIXES = {"Informatique": "INF", "Bureautique": "BUR"}


# --- Thèmes -----------------------------------------------------------------
# Chaque thème définit les mêmes jetons de couleur. `primary` est toujours la
# teinte la plus sombre (barre d'en-tête, en-têtes de colonnes), `bg` le fond
# général et `surface` les cartes et tableaux.
# Ajouter un thème = ajouter une entrée ici ; l'appliquer à chaud se fait via
# `app.ui.theme.apply_theme`.
THEMES: dict[str, dict] = {
    "clair": {
        "label": "Clair (bleu moderne)",
        "colors": {
            "primary": "#1E3A8A",
            "primary_dark": "#172554",
            "bg": "#F4F6FB",
            "surface": "#FFFFFF",
            "card": "#FFFFFF",
            "stripe": "#EEF2F9",
            "text": "#1A2233",
            "muted": "#6B7280",
            "border": "#E2E8F0",
            "border_strong": "#CBD5E1",
            "accent": "#2563EB",
            "accent_hover": "#1D4ED8",
            "accent_light": "#DBEAFE",
            "on_accent": "#FFFFFF",
            "on_primary": "#FFFFFF",
            "on_primary_muted": "#BFDBFE",
            "success": "#16A34A",
            "warn": "#D97706",
            "danger": "#DC2626",
            "danger_hover": "#FEF2F2",
            "danger_pressed": "#FEE2E2",
            "sidebar": "#1E3A8A",
            "sidebar_hover": "#1E40AF",
        },
        "budget": {
            "ok": "#047857",
            "warn": "#B45309",
            "critical": "#C2410C",
            "over": "#B91C1C",
            "none": "#6B7280",
        },
    },
    "nuit": {
        "label": "Nuit (ardoise / bleu nuit)",
        "colors": {
            "primary": "#020617",
            "primary_dark": "#000000",
            "bg": "#0F172A",
            "surface": "#1E293B",
            "card": "#1E293B",
            "stripe": "#29374D",
            "text": "#E2E8F0",
            "muted": "#94A3B8",
            "border": "#334155",
            "border_strong": "#475569",
            "accent": "#38BDF8",
            "accent_hover": "#0EA5E9",
            "accent_light": "#075985",
            "on_accent": "#0B1220",
            "on_primary": "#FFFFFF",
            "on_primary_muted": "#94A3B8",
            "success": "#34D399",
            "warn": "#FBBF24",
            "danger": "#F87171",
            "danger_hover": "#3B2226",
            "danger_pressed": "#4C2A2F",
            "sidebar": "#020617",
            "sidebar_hover": "#1E293B",
        },
        "budget": {
            "ok": "#34D399",
            "warn": "#FBBF24",
            "critical": "#FB923C",
            "over": "#F87171",
            "none": "#94A3B8",
        },
    },
    "aube": {
        "label": "Aube (clair / indigo)",
        "colors": {
            "primary": "#1E1B4B",
            "primary_dark": "#171534",
            "bg": "#F8FAFC",
            "surface": "#FFFFFF",
            "card": "#FFFFFF",
            "stripe": "#EEF2FF",
            "text": "#1E293B",
            "muted": "#64748B",
            "border": "#E2E8F0",
            "border_strong": "#CBD5E1",
            "accent": "#4F46E5",
            "accent_hover": "#4338CA",
            "accent_light": "#C7D2FE",
            "on_accent": "#FFFFFF",
            "on_primary": "#FFFFFF",
            "on_primary_muted": "#A5B4FC",
            "success": "#059669",
            "warn": "#D97706",
            "danger": "#DC2626",
            "danger_hover": "#FEF2F2",
            "danger_pressed": "#FEE2E2",
            "sidebar": "#1E1B4B",
            "sidebar_hover": "#312E81",
        },
        "budget": {
            "ok": "#047857",
            "warn": "#B45309",
            "critical": "#C2410C",
            "over": "#DC2626",
            "none": "#64748B",
        },
    },
    "classique": {
        "label": "Classique (clair / bleu marine)",
        "colors": {
            "primary": "#172554",
            "primary_dark": "#0F1E3D",
            "bg": "#F4F6F8",
            "surface": "#FFFFFF",
            "card": "#FFFFFF",
            "stripe": "#F1F5F9",
            "text": "#1F2937",
            "muted": "#5B6472",
            "border": "#D8DEE6",
            "border_strong": "#B9C2CE",
            "accent": "#1E40AF",
            "accent_hover": "#1E3A8A",
            "accent_light": "#DBEAFE",
            "on_accent": "#FFFFFF",
            "on_primary": "#FFFFFF",
            "on_primary_muted": "#93C5FD",
            "success": "#047857",
            "warn": "#B45309",
            "danger": "#B91C1C",
            "danger_hover": "#FEF2F2",
            "danger_pressed": "#FEE2E2",
            "sidebar": "#172554",
            "sidebar_hover": "#1E3A8A",
        },
        "budget": {
            "ok": "#047857",
            "warn": "#B45309",
            "critical": "#C2410C",
            "over": "#B91C1C",
            "none": "#5B6472",
        },
    },
    "cockpit": {
        "label": "Cockpit (presque noir / turquoise)",
        "colors": {
            "primary": "#020609",
            "primary_dark": "#000000",
            "bg": "#0B0F19",
            "surface": "#131A2A",
            "card": "#131A2A",
            "stripe": "#1E2740",
            "text": "#E6EDF7",
            "muted": "#8B98AD",
            "border": "#253048",
            "border_strong": "#38455F",
            "accent": "#14B8A6",
            "accent_hover": "#2DD4BF",
            "accent_light": "#0F766E",
            "on_accent": "#041210",
            "on_primary": "#FFFFFF",
            "on_primary_muted": "#7DD3C7",
            "success": "#22C55E",
            "warn": "#FACC15",
            "danger": "#F43F5E",
            "danger_hover": "#3A1220",
            "danger_pressed": "#4C1728",
            "sidebar": "#020609",
            "sidebar_hover": "#131A2A",
        },
        "budget": {
            "ok": "#22C55E",
            "warn": "#FACC15",
            "critical": "#FB923C",
            "over": "#F43F5E",
            "none": "#8B98AD",
        },
    },
}

DEFAULT_THEME = "clair"

# Jetons attendus dans chaque thème (garde-fou au démarrage).
THEME_TOKENS = tuple(sorted(THEMES[DEFAULT_THEME]["colors"]))
THEME_BUDGET_TOKENS = tuple(sorted(THEMES[DEFAULT_THEME]["budget"]))

# Jetons appliqués au thème courant. Ces deux dictionnaires ne sont jamais
# remplacés, seulement mis à jour sur place : les modules qui les ont importés
# voient donc immédiatement le thème changer.
COLORS: dict[str, str] = dict(THEMES[DEFAULT_THEME]["colors"])
BUDGET_COLORS: dict[str, str] = dict(THEMES[DEFAULT_THEME]["budget"])

FONT_FAMILY = "Segoe UI"
RADIUS = 10
