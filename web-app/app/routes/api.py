"""API JSON consommée par l'interface (recherche, plafond, aperçu)."""
from __future__ import annotations

from datetime import datetime

from flask import Blueprint, jsonify, request

from app import get_db
from app.services import documents as documents_service

blueprint = Blueprint("api", __name__, url_prefix="/api")


@blueprint.post("/documents/preview")
def preview_document():
    """Valide un document sans rien écrire : totaux, exercice, n° proposé."""
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    db = get_db()
    exclude = payload.get("exclude")
    preview = db.preview_document(
        str(payload.get("category") or ""),
        items,
        payload.get("exercice_label") or None,
        accept_new_prices=bool(payload.get("accept_new_prices")),
        exclude_document=int(exclude) if exclude else None,
    )
    preview["number"] = (
        None
        if exclude
        else documents_service.free_number(
            db, preview["category"], preview["exercice_label"]
        )
    )
    preview["created_at"] = datetime.now().isoformat(timespec="seconds")
    return jsonify(preview)


@blueprint.get("/categories")
def categories():
    db = get_db()
    out = []
    for row in db.list_categories():
        exercice = db.get_active_exercice(row["name"])
        out.append(
            {
                "name": row["name"],
                "prefix": row["prefix"],
                "status": db.effective_status(row["status"], row["expiry_date"]),
                "expiry_date": row["expiry_date"],
                "articles": db.article_count(row["name"]),
                "exercice": exercice["label"] if exercice else None,
            }
        )
    return jsonify(out)


@blueprint.get("/articles")
def articles():
    category = request.args.get("category", "").strip()
    text = request.args.get("q", "").strip()
    if not category:
        return jsonify(error="bad_request", message="Convention manquante."), 400
    rows = get_db().search_articles(category, text, limit=300)
    return jsonify(
        [
            {
                "id": int(row["id"]),
                "code": row["code"],
                "designation": row["designation"],
                "unit": row["unit"],
                "unit_price_ht": float(row["unit_price_ht"]),
            }
            for row in rows
        ]
    )


@blueprint.get("/budget")
def budget():
    category = request.args.get("category", "").strip()
    if not category:
        return jsonify(error="bad_request", message="Convention manquante."), 400
    try:
        amount = float(request.args.get("amount", 0) or 0)
    except ValueError:
        amount = 0.0
    exclude = request.args.get("exclude", "").strip()
    exclude_id = int(exclude) if exclude.isdigit() else None
    return jsonify(get_db().budget_status(category, amount, exclude_id))


@blueprint.get("/exercices")
def exercices():
    category = request.args.get("category", "").strip()
    db = get_db()
    rows = db.list_exercices(category) if category else db.list_all_exercices()
    return jsonify(
        [
            {
                "id": int(row["id"]),
                "category": row["category"],
                "label": row["label"],
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "plafond": row["plafond"],
                "status": row["status"],
                "consumed_at_close": row["consumed_at_close"],
                "remaining_at_close": row["remaining_at_close"],
            }
            for row in rows
        ]
    )


@blueprint.get("/documents/<int:document_id>")
def document(document_id: int):
    db = get_db()
    doc = db.get_document(document_id)
    if not doc:
        return jsonify(error="not_found", message="Commande introuvable."), 404
    editable, reason = db.document_editable(document_id)
    return jsonify(
        {
            "id": int(doc["id"]),
            "number": doc["number"],
            "created_at": doc["created_at"],
            "category": doc["category"],
            "exercice_label": doc["exercice_label"],
            "total_ht": float(doc["total_ht"]),
            "tva_rate": float(doc["tva_rate"] or 0),
            "tva_amount": float(doc["tva_amount"] or 0),
            "total_ttc": float(doc["total_ttc"] or 0),
            "editable": editable,
            "edit_reason": reason,
            "items": [
                {
                    "id": int(row["id"]),
                    "article_id": row["article_id"],
                    "code": row["code"],
                    "designation": row["designation"],
                    "unit": row["unit"],
                    "unit_price_ht": float(row["unit_price_ht"]),
                    "quantity": float(row["quantity"]),
                    "total_ht": float(row["total_ht"]),
                }
                for row in db.document_items(document_id)
            ],
        }
    )
