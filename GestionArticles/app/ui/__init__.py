"""Interface graphique Tkinter de l'application.

- ``app.ui.app``      : fenêtre principale et orchestration des menus.
- ``app.ui.theme``    : style ttk partagé.
- ``app.ui.common``   : utilitaires (dates, montants, ouverture de fichier).
- ``app.ui.views``    : onglets « Nouveau document » et « Historique ».
- ``app.ui.dialogs``  : fenêtres modales autonomes.
"""
from __future__ import annotations

__all__ = ["App", "run"]


def __getattr__(name: str):
    if name in __all__:
        from app.ui import app as _app

        return getattr(_app, name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
