"""Utilitaires métier : prix, quantités, montants, dates."""
from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable

from app.config import TVA_RATE


def parse_price(price) -> float:
    numeric_text = str(price).replace("\u00a0", "").replace(" ", "").strip()
    if not numeric_text:
        raise ValueError("Le prix est obligatoire.")
    if "," in numeric_text and "." in numeric_text:
        if numeric_text.rfind(",") > numeric_text.rfind("."):
            numeric_text = numeric_text.replace(".", "").replace(",", ".")
        else:
            numeric_text = numeric_text.replace(",", "")
    elif numeric_text.count(",") > 1:
        parts = numeric_text.split(",")
        numeric_text = "".join(parts[:-1]) + "." + parts[-1]
    elif numeric_text.count(",") == 1:
        left, right = numeric_text.split(",")
        numeric_text = left + "." + right
    try:
        value = float(numeric_text)
    except ValueError as exc:
        raise ValueError(f"Montant invalide : {price!r}.") from exc
    if not math.isfinite(value) or value < 0:
        raise ValueError("Le prix doit être un montant fini positif ou nul.")
    return value


def parse_quantity(quantity) -> float:
    text = str(quantity).replace("\u00a0", "").replace(" ", "").strip()
    if not text:
        raise ValueError("La quantité est obligatoire.")
    try:
        value = float(text.replace(",", "."))
    except ValueError as exc:
        raise ValueError(f"Quantité invalide : {quantity!r}.") from exc
    if not math.isfinite(value) or value <= 0:
        raise ValueError("La quantité doit être un nombre strictement positif.")
    return value


def parse_optional_amount(value) -> float | None:
    """Montant libre (plafond) : vide/``None``/``0``/``illimité`` = illimité."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        text = str(value)
    else:
        text = str(value).replace("\u00a0", "").replace(" ", "").strip()
    if text in ("", "-", "—", "0", "0.0", "0,00", "illimite", "illimité", "aucun"):
        return None
    amount = parse_price(text)
    if amount <= 0:
        return None
    return round(amount, 2)


def excel_safe_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def _french_number(value: float) -> str:
    """Nombre à la française : espace en milliers, virgule en décimales."""
    return f"{value:,.2f}".replace(",", " ").replace(".", ",")


def money_format(value: float) -> str:
    return _french_number(value) + " DA"


def money_short(value) -> str:
    """Montant compact pour l'interface (séparateur d'espace, 2 décimales)."""
    if value is None:
        return "—"
    return _french_number(float(value)) + " DA"


def percent_format(value) -> str:
    if value is None:
        return "—"
    return f"{float(value) * 100:.1f} %".replace(".", ",")


def format_date(value, fmt: str = "%d/%m/%Y %H:%M") -> str:
    if not value:
        return "—"
    try:
        return datetime.fromisoformat(str(value)).strftime(fmt)
    except (TypeError, ValueError):
        return str(value)


def format_day(value) -> str:
    return format_date(value, "%d/%m/%Y")


def line_total(quantity: float, unit_price: float) -> float:
    return round(float(quantity) * float(unit_price), 2)


def compute_totals(items: Iterable[dict], rate: float = TVA_RATE) -> tuple[float, float, float]:
    """Totaux du document.

    Le total HT est la **somme des totaux de ligne arrondis** : identique à ce
    qui est affiché, stocké dans ``document_items`` et imprimé dans le PDF/Excel
    (aucune divergence d'un centime possible).
    """
    rate = float(rate)
    if not math.isfinite(rate) or rate < 0:
        raise ValueError("Le taux de TVA doit être un taux fini positif ou nul.")
    total_ht = 0.0
    for item in items:
        quantity = float(item["quantity"])
        price = float(item["unit_price_ht"])
        if not math.isfinite(quantity) or quantity <= 0:
            raise ValueError("La quantité doit être un nombre strictement positif.")
        if not math.isfinite(price) or price < 0:
            raise ValueError("Le prix doit être un montant fini positif ou nul.")
        total_ht += line_total(quantity, price)
    total_ht = round(total_ht, 2)
    tva_amount = round(total_ht * rate, 2)
    total_ttc = round(total_ht + tva_amount, 2)
    return total_ht, tva_amount, total_ttc
