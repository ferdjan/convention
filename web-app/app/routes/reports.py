"""Écran : rapport de consommation par exercice (Excel)."""
from __future__ import annotations

import io

from flask import Blueprint, render_template, request, send_file

from app import get_db
from app.services import documents as documents_service
from app.security import filename_safe

blueprint = Blueprint("reports", __name__)


@blueprint.get("/reports")
def index():
    db = get_db()
    mode = request.args.get("mode", "exercice").strip()
    if mode not in ("exercice", "civil"):
        mode = "exercice"
    if mode == "civil":
        options = db.civil_years()
        selected = request.args.get("year", "").strip()
        if selected not in options:
            selected = options[0] if options else ""
        rows = db.civil_year_report(selected) if selected else []
        documents = db.civil_year_documents(selected) if selected else []
        period = f"année civile {selected}" if selected else ""
        download_args = {"mode": "civil", "year": selected}
        empty_title = "Aucune année"
        empty_text = "Aucune commande n'a été enregistrée pour le moment."
    else:
        options = db.exercice_labels()
        selected = request.args.get("label", "").strip()
        if selected not in options:
            selected = options[0] if options else ""
        rows = db.exercice_consumption_report(selected) if selected else []
        documents = db.exercice_documents(selected) if selected else []
        period = f"exercice {selected}" if selected else ""
        download_args = {"mode": "exercice", "label": selected}
        empty_title = "Aucun exercice"
        empty_text = "Ouvrez d'abord un exercice dans les conventions."
    totals = {
        "plafond": sum(r["plafond"] for r in rows if r["plafond"] is not None),
        "consumed": round(sum(float(r["consumed"] or 0) for r in rows), 2),
        "docs": sum(int(r["doc_count"] or 0) for r in rows),
        "has_plafond": any(r["plafond"] is not None for r in rows),
    }
    if totals["has_plafond"]:
        remaining = sum(
            float(r["remaining"] or 0) for r in rows if r["remaining"] is not None
        )
        totals["remaining"] = round(remaining, 2)
    else:
        totals["remaining"] = None
    return render_template(
        "reports.html",
        mode=mode,
        options=options,
        selected=selected,
        rows=rows,
        documents=documents,
        totals=totals,
        period=period,
        download_args=download_args,
        empty_title=empty_title,
        empty_text=empty_text,
    )


@blueprint.get("/reports/download")
def download():
    db = get_db()
    mode = request.args.get("mode", "exercice").strip()
    if mode == "civil":
        year = request.args.get("year", "").strip()
        if year not in db.civil_years():
            return render_template(
                "error.html", code=404, title="Année introuvable",
                message="Choisissez une année civile existante.",
            ), 404
        payload, name = documents_service.export_civil_report(db, year)
    else:
        label = request.args.get("label", "").strip()
        if label not in db.exercice_labels():
            return render_template(
                "error.html", code=404, title="Exercice introuvable",
                message="Choisissez un exercice existant.",
            ), 404
        payload, name = documents_service.export_exercice_report(db, label)
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename_safe(name),
    )
