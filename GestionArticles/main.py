"""Point d'entrée de l'application de gestion des articles.

L'interface Tkinter vit désormais dans le paquet ``app.ui`` :

- ``app.ui.app.App``      : fenêtre principale, menus et chrome.
- ``app.ui.views``        : onglets « Nouveau document » et « Historique ».
- ``app.ui.dialogs``      : fenêtres modales (budgets, conventions, import, ...).
- ``app.ui.theme``        : style ttk.
- ``app.ui.common``       : utilitaires partagés (dates, montants, fichiers).

Ce fichier se limite à démarrer l'application et à afficher l'écran d'erreur
en cas d'échec d'ouverture ou de migration de la base.
"""
from __future__ import annotations

from app.ui.app import App, run

__all__ = ["App", "run"]


if __name__ == "__main__":
    run()
