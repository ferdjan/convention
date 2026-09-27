from __future__ import annotations

from datetime import datetime
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

from app.utils import excel_safe_text

HEADER_FILL = PatternFill("solid", fgColor="1F4E78")
HEADER_FONT = Font(bold=True, color="FFFFFF")
TITLE_FONT = Font(bold=True, size=14, color="1F4E78")
LABEL_FONT = Font(bold=True)
TOTAL_FILL = PatternFill("solid", fgColor="EAF2F8")
OVER_FILL = PatternFill("solid", fgColor="F9D6D5")
MONEY_FORMAT = '#,##0.00" DA"'
PERCENT_FORMAT = '0.0" %"'
THIN = Side(style="thin", color="B7C9D6")
BORDER = Border(left=THIN, right=THIN, top=THIN, bottom=THIN)


def build_exercice_report(
    path: str | Path,
    label: str,
    summary_rows: list[dict],
    documents: list,
    generated_by: str | None = None,
    kind: str = "EXERCICE",
) -> Path:
    """Rapport de consommation d'un exercice (feuilles Synthèse + Documents)."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    wb = Workbook()
    ws = wb.active
    ws.title = "Synthèse"

    ws.merge_cells("A1:F1")
    ws["A1"] = f"RAPPORT DE CONSOMMATION — {kind} {label}"
    ws["A1"].font = TITLE_FONT
    ws["A1"].alignment = Alignment(horizontal="center")
    info = f"Généré le {datetime.now().strftime('%d/%m/%Y %H:%M')}"
    if generated_by:
        info += f" par {generated_by}"
    ws["A2"] = excel_safe_text(info)
    ws["A2"].font = Font(italic=True, color="5A6B7B")

    headers = ["Convention", "Plafond de l'exercice", "Consommé", "Reste", "Taux", "Nb commandes"]
    header_row = 4
    for col, title in enumerate(headers, start=1):
        ws.cell(row=header_row, column=col, value=title)

    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=header_row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")

    row_idx = header_row + 1
    total_plafond = 0.0
    total_consumed = 0.0
    total_remaining = 0.0
    total_docs = 0
    has_plafond = False
    for item in summary_rows:
        plafond = item.get("plafond")
        consumed = item.get("consumed") or 0.0
        remaining = item.get("remaining")
        rate = item.get("rate")
        docs = item.get("doc_count") or 0
        over = plafond is not None and consumed > plafond + 0.005

        ws.cell(row=row_idx, column=1, value=excel_safe_text(item.get("category")))
        ws.cell(row=row_idx, column=2, value="—" if plafond is None else round(plafond, 2))
        ws.cell(row=row_idx, column=3, value=round(consumed, 2)).number_format = MONEY_FORMAT
        ws.cell(row=row_idx, column=4, value="—" if remaining is None else round(remaining, 2))
        ws.cell(
            row=row_idx,
            column=5,
            value=None if rate is None else rate * 100,
        ).number_format = PERCENT_FORMAT
        ws.cell(row=row_idx, column=6, value=docs)
        if plafond is not None:
            ws.cell(row=row_idx, column=2).number_format = MONEY_FORMAT
            ws.cell(row=row_idx, column=4).number_format = MONEY_FORMAT
            # Correctif TOTAL : seules les conventions avec plafond comptent
            # dans le total des plafonds et des restes.
            total_plafond += float(plafond)
            has_plafond = True
            if remaining is not None:
                total_remaining += float(remaining)
        total_consumed += float(consumed)
        total_docs += docs

        for col in range(1, len(headers) + 1):
            cell = ws.cell(row=row_idx, column=col)
            cell.border = BORDER
            if col == 1:
                cell.alignment = Alignment(horizontal="left", vertical="center")
            else:
                cell.alignment = Alignment(horizontal="right", vertical="center")
        if over:
            for col in range(1, len(headers) + 1):
                ws.cell(row=row_idx, column=col).fill = OVER_FILL
        row_idx += 1

    ws.cell(row=row_idx, column=1, value="TOTAL").font = LABEL_FONT
    ws.cell(row=row_idx, column=2, value="—" if not has_plafond else round(total_plafond, 2)).number_format = MONEY_FORMAT
    ws.cell(row=row_idx, column=3, value=round(total_consumed, 2)).number_format = MONEY_FORMAT
    ws.cell(
        row=row_idx,
        column=4,
        value="—" if not has_plafond else round(total_remaining, 2),
    ).number_format = MONEY_FORMAT
    # Correctif TOTAL : taux global = (Σ plafonds - Σ restes) / Σ plafonds,
    # cohérent avec les colonnes Reste de chaque ligne.
    ws.cell(
        row=row_idx,
        column=5,
        value=(
            "—"
            if not has_plafond or not total_plafond
            else (total_plafond - total_remaining) / total_plafond * 100
        ),
    ).number_format = PERCENT_FORMAT
    ws.cell(row=row_idx, column=6, value=total_docs)
    for col in range(1, len(headers) + 1):
        cell = ws.cell(row=row_idx, column=col)
        cell.fill = TOTAL_FILL
        cell.font = LABEL_FONT
        cell.border = BORDER
        cell.alignment = Alignment(
            horizontal="left" if col == 1 else "right", vertical="center"
        )

    for col, width in enumerate((26, 22, 18, 18, 12, 15), start=1):
        ws.column_dimensions[get_column_letter(col)].width = width

    ws2 = wb.create_sheet("Commandes")
    ws2.merge_cells("A1:F1")
    ws2["A1"] = f"DOCUMENTS — {kind} {label}"
    ws2["A1"].font = TITLE_FONT
    ws2["A1"].alignment = Alignment(horizontal="center")

    doc_headers = [
        "Convention", "N° commande", "Date", "Total HT", "TVA", "Total TTC",
    ]
    dheader_row = 3
    for col, title in enumerate(doc_headers, start=1):
        ws2.cell(row=dheader_row, column=col, value=title)

    for col in range(1, len(doc_headers) + 1):
        cell = ws2.cell(row=dheader_row, column=col)
        cell.fill = HEADER_FILL
        cell.font = HEADER_FONT
        cell.border = BORDER
        cell.alignment = Alignment(horizontal="center", vertical="center")

    drow = dheader_row + 1
    for doc in documents:
        try:
            date_text = datetime.fromisoformat(doc["created_at"]).strftime("%d/%m/%Y")
        except (ValueError, TypeError):
            date_text = doc["created_at"]
        ws2.cell(row=drow, column=1, value=excel_safe_text(doc["category"]))
        ws2.cell(row=drow, column=2, value=excel_safe_text(doc["number"]))
        ws2.cell(row=drow, column=3, value=excel_safe_text(date_text))
        ws2.cell(row=drow, column=4, value=round(float(doc["total_ht"] or 0), 2)).number_format = MONEY_FORMAT
        ws2.cell(row=drow, column=5, value=round(float(doc["tva_amount"] or 0), 2)).number_format = MONEY_FORMAT
        ws2.cell(row=drow, column=6, value=round(float(doc["total_ttc"] or 0), 2)).number_format = MONEY_FORMAT
        for col in range(1, len(doc_headers) + 1):
            cell = ws2.cell(row=drow, column=col)
            cell.border = BORDER
            cell.alignment = Alignment(
                horizontal="left" if col == 1 else "center", vertical="center"
            )
        drow += 1

    for col, width in enumerate((24, 22, 14, 16, 16, 16), start=1):
        ws2.column_dimensions[get_column_letter(col)].width = width

    wb.save(path)
    return path


# Compatibilité : l'ancien nom reste importable pour les appels externes.
build_annual_report = build_exercice_report
