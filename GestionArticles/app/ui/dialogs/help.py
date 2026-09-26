"""Rappel du format Excel attendu (menu Aide)."""
from __future__ import annotations

from tkinter import messagebox

FORMAT_HELP = (
    "Rappel du format Excel attendu\n\n"
    "• Le classeur contient une feuille par liste.\n"
    "• La première ligne de chaque feuille doit contenir exactement :\n"
    "   N°  |  Désignation  |  Unité de mesure  |  Prix unitaire HT\n\n"
    "• N° : code / référence de l'article\n"
    "• Désignation : libellé de l'article\n"
    "• Unité de mesure : pièce, boîte, mètre, ...\n"
    "• Prix unitaire HT : nombre (point ou virgule acceptés)\n\n"
    "Une éventuelle ligne TOTAL en fin de feuille est ignorée.\n"
    "Utilisez « Fichier → Importer des articles Excel... » pour charger la liste."
)


def show_excel_format(categories: list[str] | None = None) -> None:
    text = FORMAT_HELP
    if categories:
        text += "\n\nListe(s) : " + ", ".join(categories)
    messagebox.showinfo("Format Excel", text)
