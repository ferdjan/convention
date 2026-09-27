"""Écran : tableau de bord (cartes par convention)."""
from __future__ import annotations

from flask import Blueprint, render_template

from app import get_db

blueprint = Blueprint("dashboard", __name__)


@blueprint.get("/")
def index():
    db = get_db()
    active = []
    no_exercice = []
    expired = []
    closed = []
    total_plafond = 0.0
    total_consumed = 0.0
    has_plafond = False

    for cat in db.list_categories():
        status = db.effective_status(cat["status"], cat["expiry_date"])
        exercice = db.get_active_exercice(cat["name"])
        articles = db.article_count(cat["name"])
        entry = {
            "id": int(cat["id"]),
            "name": cat["name"],
            "prefix": cat["prefix"],
            "status": status,
            "expiry_date": cat["expiry_date"],
            "articles": articles,
            "has_exercice": exercice is not None,
        }
        if status != "active":
            (expired if status == "expiree" else closed).append(entry)
            continue
        if not exercice:
            no_exercice.append(entry)
            continue
        summary = db.exercice_summary(cat["name"], exercice["label"])
        documents = db.exercice_documents(exercice["label"], cat["name"])
        consumed = float(summary["consumed"] or 0.0)
        total_consumed += consumed
        if summary["plafond"] is not None:
            has_plafond = True
            total_plafond += float(summary["plafond"])
        entry.update(
            {"summary": summary, "doc_count": len(documents)}
        )
        active.append(entry)

    stats = {
        "categories": len(active),
        "categories_total": len(active) + len(no_exercice) + len(expired) + len(closed),
        "documents": len(db.list_documents()),
        "articles": db.article_count(),
        "plafond": round(total_plafond, 2) if has_plafond else None,
        "consumed": round(total_consumed, 2),
        "remaining": round(total_plafond - total_consumed, 2) if has_plafond else None,
    }
    return render_template(
        "dashboard.html",
        active=active,
        no_exercice=no_exercice,
        expired=expired,
        closed=closed,
        stats=stats,
    )
