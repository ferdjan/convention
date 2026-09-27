"""Écran : historique des documents (filtres, aperçu, actions)."""
from __future__ import annotations

from flask import Blueprint, render_template, request

from app import get_db

blueprint = Blueprint("history", __name__)


@blueprint.get("/history")
def index():
    db = get_db()
    text = request.args.get("text", "").strip()
    category = request.args.get("category", "").strip()
    exercice = request.args.get("exercice", "").strip()
    selected = request.args.get("doc", "").strip()

    documents = db.list_documents(
        text, category or None, exercice or None
    )
    preview = None
    if selected.isdigit():
        document_id = int(selected)
        doc = db.get_document(document_id)
        if doc:
            editable, reason = db.document_editable(document_id)
            preview = {
                "doc": doc,
                "items": db.document_items(document_id),
                "editable": editable,
                "edit_reason": reason,
            }

    return render_template(
        "history.html",
        documents=documents,
        preview=preview,
        filters={"text": text, "category": category, "exercice": exercice},
        categories=db.category_names(),
        exercices=db.exercice_labels(),
        total=len(db.list_documents()),
    )
