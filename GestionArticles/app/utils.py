from __future__ import annotations

import math
from datetime import datetime
from typing import Iterable

from app.config import TVA_RATE


def parse_price(price: str) -> float:
    numeric_text = str(price).replace("\u00a0", "").replace(" ", "")
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
    value = float(numeric_text)
    if not math.isfinite(value) or value < 0:
        raise ValueError("Le prix doit être un montant fini positif ou nul.")
    return value


def parse_quantity(quantity: str) -> float:
    value = float(str(quantity).replace("\u00a0", "").replace(" ", "").replace(",", "."))
    if not math.isfinite(value) or value <= 0:
        raise ValueError("La quantité doit être un nombre strictement positif.")
    return value


def excel_safe_text(value: object) -> object:
    if not isinstance(value, str):
        return value
    if value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def money_format(value: float) -> str:
    return f"{value:,.2f}".replace(",", " ") + " DA"


def format_date(value: str, fmt: str = "%d/%m/%Y %H:%M") -> str:
    try:
        return datetime.fromisoformat(value).strftime(fmt)
    except (AttributeError, TypeError, ValueError):
        return value


def compute_totals(
    items: Iterable[dict],
    rate: float = TVA_RATE,
) -> tuple[float, float, float]:
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
        total_ht += quantity * price
    total_ht = round(total_ht, 2)
    tva_amount = round(total_ht * rate, 2)
    total_ttc = round(total_ht + tva_amount, 2)
    return total_ht, tva_amount, total_ttc
