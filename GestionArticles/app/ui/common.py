"""Utilitaires partagés par les vues et les dialogues de l'interface."""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

from app.utils import format_date, money_format


def money(value: float) -> str:
    return money_format(value)


def display_date(value: str) -> str:
    return format_date(value)


def exercice_display(label: str | None) -> str:
    """Libellé d'exercice affichable (« 2026-2027 » ou «—»)."""
    return label.strip() if label and label.strip() else "—"


def open_path(path: Path) -> None:
    try:
        os.startfile(str(path))
    except AttributeError:
        if sys.platform == "win32":
            raise
        subprocess.Popen(["xdg-open", str(path)])
