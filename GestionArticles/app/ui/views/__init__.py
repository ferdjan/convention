"""Vues (écrans) de l'application.

- ``app.ui.views.dashboard``   : synthèse des conventions (accueil) ;
- ``app.ui.views.document``    : saisie d'un nouveau document ;
- ``app.ui.views.history``     : historique des documents ;
- ``app.ui.views.conventions`` : gestion des conventions et exercices ;
- ``app.ui.views.reports``     : rapport de consommation ;
- ``app.ui.views.settings``    : thème et à propos.
"""
from __future__ import annotations

__all__ = [
    "ConventionsView",
    "DashboardView",
    "DocumentView",
    "HistoryView",
    "ReportsView",
    "SettingsView",
]


def __getattr__(name: str):
    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    module = {
        "DashboardView": "dashboard",
        "DocumentView": "document",
        "HistoryView": "history",
        "ConventionsView": "conventions",
        "ReportsView": "reports",
        "SettingsView": "settings",
    }[name]
    return getattr(__import__(f"app.ui.views.{module}", fromlist=[name]), name)
