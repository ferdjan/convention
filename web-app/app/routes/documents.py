"""Écrans : nouveau document, détail, modification, suppression."""
from __future__ import annotations

import json

from flask import (
    Blueprint,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

from app import get_db
from app.services import documents as documents_service

blueprint = Blueprint("documents", __name__)


def _open_categories():
    """Conventions actives (avec exercice d'abord) + budget et volumes.

    Sert l'étape 1 de l'assistant : chaque carte affiche l'exercice actif,
    l'état du plafond et le nombre d'articles.
    """
    db = get_db()
    out = []
    for name in db.active_category_names():
        exercice = db.get_active_exercice(name)
        out.append(
            {
                "name": name,
                "prefix": db.category_prefix(name),
                "exercice": exercice["label"] if exercice else None,
                "articles": db.article_count(name),
                "budget": db.budget_status(name, 0.0),
            }
        )
    out.sort(key=lambda c: (c["exercice"] is None, c["name"].casefold()))
    return out


@blueprint.get("/documents/new")
def new_document():
    categories = _open_categories()
    selected = request.args.get("category", "")
    if not any(c["name"] == selected for c in categories):
        selected = categories[0]["name"] if categories else ""
    return render_template(
        "document_form.html",
        mode="new",
        doc=None,
        categories=categories,
        selected=selected,
        items=[],
        exclude_id=None,
        initial_cart="[]",
        preview_url=url_for("api.preview_document"),
        save_url=url_for("documents.create_document"),
    )


@blueprint.get("/documents/<int:document_id>/edit")
def edit_document(document_id: int):
    db = get_db()
    doc = db.get_document(document_id)
    if not doc:
        return render_template(
            "error.html", code=404, title="Commande introuvable",
            message="Cette commande n'existe plus.",
        ), 404
    editable, reason = db.document_editable(document_id)
    if not editable:
        flash(reason, "error")
        return redirect(url_for("documents.document_detail", document_id=document_id))

    items = db.document_items(document_id)
    categories = _open_categories()
    cart = [
        {
            "item_id": int(row["id"]),
            "article_id": row["article_id"],
            "code": row["code"],
            "designation": row["designation"],
            "unit": row["unit"],
            "unit_price_ht": float(row["unit_price_ht"]),
            "quantity": float(row["quantity"]),
            "frozen": True,
        }
        for row in items
    ]
    return render_template(
        "document_form.html",
        mode="edit",
        doc=doc,
        categories=categories,
        selected=doc["category"],
        items=items,
        exclude_id=document_id,
        initial_cart=json.dumps(cart, ensure_ascii=False),
        preview_url=url_for("api.preview_document", exclude=document_id),
        save_url=url_for("documents.update_document", document_id=document_id),
    )


@blueprint.get("/documents/<int:document_id>")
def document_detail(document_id: int):
    db = get_db()
    doc = db.get_document(document_id)
    if not doc:
        return render_template(
            "error.html", code=404, title="Commande introuvable",
            message="Cette commande n'existe plus.",
        ), 404
    items = db.document_items(document_id)
    editable, reason = db.document_editable(document_id)
    return render_template(
        "document_detail.html", doc=doc, items=items,
        editable=editable, edit_reason=reason,
    )


@blueprint.post("/documents")
def create_document():
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    result = documents_service.create_document(
        get_db(),
        category=str(payload.get("category") or ""),
        items=items,
        exercice_label=payload.get("exercice_label") or None,
        accept_new_prices=bool(payload.get("accept_new_prices")),
    )
    return jsonify(result), 201


@blueprint.post("/documents/<int:document_id>")
def update_document(document_id: int):
    payload = request.get_json(silent=True) or {}
    items = payload.get("items") or []
    result = documents_service.update_document(
        get_db(),
        document_id,
        items=items,
        accept_new_prices=bool(payload.get("accept_new_prices")),
    )
    return jsonify(result)


@blueprint.get("/documents/<int:document_id>/export")
def export_document(document_id: int):
    payload, name = documents_service.export_document_excel(get_db(), document_id)
    if payload is None:
        return render_template(
            "error.html", code=404, title="Commande introuvable",
            message="Cette commande n'existe plus.",
        ), 404
    import io

    from app.security import filename_safe

    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=filename_safe(name),
    )


@blueprint.post("/documents/<int:document_id>/delete")
def delete_document(document_id: int):
    db = get_db()
    doc = db.get_document(document_id)
    if doc:
        db.delete_document(document_id)
        flash(
            f"Commande {doc['number']} supprimée (les fichiers restent sur le disque).",
            "success",
        )
    else:
        flash("Commande introuvable.", "error")
    return redirect(url_for("history.index"))
