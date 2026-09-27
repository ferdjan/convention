from __future__ import annotations

from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer

from app.utils import money_format


def build_pdf(
    path: str | Path,
    number: str,
    date_text: str,
    category: str,
    items: list[dict],
    total_ht: float,
    tva_rate: float,
    tva_amount: float | None = None,
    total_ttc: float | None = None,
) -> Path:
    if tva_amount is None:
        tva_amount = round(total_ht * tva_rate, 2)
    if total_ttc is None:
        total_ttc = round(total_ht + tva_amount, 2)
    tva_label = f"TVA {tva_rate * 100:g}%"

    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    doc = SimpleDocTemplate(
        str(path), pagesize=A4,
        rightMargin=15*mm, leftMargin=15*mm,
        topMargin=14*mm, bottomMargin=14*mm,
        title=f"Document {number}", author="Gestion Articles"
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="DocTitle", parent=styles["Title"], alignment=TA_CENTER, fontSize=16, leading=20, spaceAfter=8))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="Right", parent=styles["Normal"], alignment=TA_RIGHT))

    story = []
    story.append(Paragraph("DOCUMENT DE COMMANDE", styles["DocTitle"]))
    info = [
        [
            Paragraph(f"<b>N° :</b> {escape(str(number))}", styles["Normal"]),
            Paragraph(f"<b>Date :</b> {escape(str(date_text))}", styles["Right"]),
        ],
        [Paragraph(f"<b>Liste :</b> {escape(str(category))}", styles["Normal"]), ""],
    ]
    tinfo = Table(info, colWidths=[90*mm, 85*mm])
    tinfo.setStyle(TableStyle([
        ("VALIGN", (0,0), (-1,-1), "TOP"),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(tinfo)
    story.append(Spacer(1, 6))

    data = [["N°", "Désignation", "Unité", "Prix unitaire HT", "Quantité", "Total HT"]]
    for item in items:
        data.append([
            escape(str(item["code"])),
            escape(str(item["designation"])),
            escape(str(item["unit"])),
            money_format(float(item["unit_price_ht"])),
            f"{float(item['quantity']):g}",
            money_format(float(item["quantity"]) * float(item["unit_price_ht"])),
        ])
    data.append(["", "", "", "", "TOTAL HT", money_format(total_ht)])
    data.append(["", "", "", "", tva_label, money_format(tva_amount)])
    data.append(["", "", "", "", "TOTAL TTC", money_format(total_ttc)])

    table = Table(data, colWidths=[17*mm, 68*mm, 25*mm, 28*mm, 18*mm, 28*mm], repeatRows=1)
    table.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#1f4e78")),
        ("TEXTCOLOR", (0,0), (-1,0), colors.white),
        ("FONTNAME", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONTSIZE", (0,0), (-1,-1), 8),
        ("GRID", (0,0), (-1,-1), 0.4, colors.HexColor("#B7C9D6")),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("ALIGN", (0,0), (0,-1), "CENTER"),
        ("ALIGN", (2,1), (5,-1), "RIGHT"),
        ("FONTNAME", (4,-3), (5,-1), "Helvetica-Bold"),
        ("BACKGROUND", (4,-2), (5,-1), colors.HexColor("#EAF2F8")),
        ("BACKGROUND", (4,-1), (5,-1), colors.HexColor("#1f4e78")),
        ("TEXTCOLOR", (4,-1), (5,-1), colors.white),
        ("TOPPADDING", (0,0), (-1,-1), 4),
        ("BOTTOMPADDING", (0,0), (-1,-1), 4),
    ]))
    story.append(table)
    story.append(Spacer(1, 20))
    story.append(Paragraph("Document généré par l'application de gestion des articles.", styles["Small"]))
    doc.build(story)
    return path