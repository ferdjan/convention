"""Configuration de l'application web (100 % hors-ligne)."""
from __future__ import annotations

import getpass
from pathlib import Path

APP_NAME = "Gestion Articles"
APP_SUBTITLE = "Conventions & commandes — édition web"
VERSION = "2.0-web"

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "web_app.db"
EXPORT_DIR = BASE_DIR / "documents_pdf" / "web"
SECRET_FILE = BASE_DIR / ".session.key"
UPLOAD_DIR = BASE_DIR / "uploads"

# Classeur source : à côté de l'app web, sinon dans le dépôt parent (racine du
# projet bureau) — permet de réutiliser source_listes.xlsx sans le dupliquer.
SEED_CANDIDATES = (
    BASE_DIR / "source_listes.xlsx",
    BASE_DIR.parent / "source_listes.xlsx",
)


def seed_xlsx() -> Path | None:
    for candidate in SEED_CANDIDATES:
        if candidate.is_file():
            return candidate
    return None


try:
    CURRENT_USER = getpass.getuser()
except Exception:  # pragma: no cover - environnement exotique
    CURRENT_USER = "user"

TVA_RATE = 0.19

BUDGET_WARN = 0.80
BUDGET_CRITICAL = 0.90
# Blocage ferme : égalité incluse (consommé + commande >= plafond).
BUDGET_BLOCK = 1.0

DEFAULT_CATEGORIES = ("Informatique", "Bureautique")
DEFAULT_PREFIXES = {"Informatique": "INF", "Bureautique": "BUR"}

HOST = "127.0.0.1"
PORT = 8765
PORT_SEARCH_LIMIT = 20
MAX_UPLOAD_BYTES = 20 * 1024 * 1024

# --- Thèmes -----------------------------------------------------------------
# Deux thèmes uniquement : Clair et Sombre (choix utilisateur, Phase 2).
THEMES: dict[str, dict] = {
    "clair": {
        "label": "Clair",
        "colors": {
            "primary": "#1E3A8A",
            "primary_dark": "#172554",
            "bg": "#F4F6FB",
            "surface": "#FFFFFF",
            "card": "#FFFFFF",
            "stripe": "#EEF2F9",
            "text": "#1A2233",
            "muted": "#5B6472",
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
            "sidebar": "#1E3A8A",
            "sidebar_hover": "#1E40AF",
            "shadow": "0 1px 2px rgba(15, 23, 42, .06), 0 8px 24px rgba(15, 23, 42, .06)",
            "shadow_lg": "0 12px 40px rgba(15, 23, 42, .18)",
        },
        "budget": {"ok": "#047857", "warn": "#B45309", "critical": "#C2410C", "over": "#B91C1C", "none": "#6B7280"},
    },
    "sombre": {
        "label": "Sombre",
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
            "sidebar": "#020617",
            "sidebar_hover": "#273449",
            "shadow": "0 1px 2px rgba(0, 0, 0, .45), 0 8px 24px rgba(0, 0, 0, .35)",
            "shadow_lg": "0 12px 40px rgba(0, 0, 0, .5)",
        },
        "budget": {"ok": "#34D399", "warn": "#FBBF24", "critical": "#FB923C", "over": "#F87171", "none": "#94A3B8"},
    },
}

DEFAULT_THEME = "clair"
