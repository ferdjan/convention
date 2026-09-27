"""Boîtes de dialogue de l'application.

Chaque fonction est autonome : elle reçoit la fenêtre parente, la base de
données et les callbacks de rafraîchissement, et n'accède plus à l'état de la
fenêtre principale.
"""
from __future__ import annotations

from app.ui.dialogs.categories import delete_list
from app.ui.dialogs.confirm import (
    confirm_document,
    confirm_price_refresh,
)
from app.ui.dialogs.conventions import (
    close_exercice_dialog,
    edit_convention_status,
    edit_exercice,
    manage_conventions,
)
from app.ui.dialogs.documents import show_document_items
from app.ui.dialogs.help import FORMAT_HELP, show_excel_format
from app.ui.dialogs.importer import ask_import_target

__all__ = [
    "FORMAT_HELP",
    "ask_import_target",
    "close_exercice_dialog",
    "confirm_document",
    "confirm_price_refresh",
    "delete_list",
    "edit_convention_status",
    "edit_exercice",
    "manage_conventions",
    "show_document_items",
    "show_excel_format",
]
