"""Écran : conventions, exercices, import des listes de prix."""
from __future__ import annotations

import io
import uuid
from datetime import date
from pathlib import Path

from flask import (
    Blueprint,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)

from app import config as cfg, get_db
from app.importer import import_articles, read_sheet_names
from app.services import documents as documents_service
from app.utils import parse_optional_amount

blueprint = Blueprint("conventions", __name__)


def _rows_for_view():
    db = get_db()
    rows = []
    for cat in db.list_categories():
        status = db.effective_status(cat["status"], cat["expiry_date"])
        exercice = db.get_active_exercice(cat["name"])
        summary = (
            db.exercice_summary(cat["name"], exercice["label"]) if exercice else None
        )
        rows.append(
            {
                "row": cat,
                "status": status,
                "exercice": exercice,
                "summary": summary,
                "articles": db.article_count(cat["name"]),
                "documents": len(db.list_documents(category=cat["name"])),
            }
        )
    return rows


@blueprint.get("/conventions")
def index():
    db = get_db()
    rows = _rows_for_view()
    selected = request.args.get("category", "").strip()
    if not selected and rows:
        selected = rows[0]["row"]["name"]
    current = next(
        (entry for entry in rows if entry["row"]["name"] == selected), None
    )
    current_status = current["status"] if current else None
    exercices = db.list_exercices(selected) if selected else []
    live_consumed = {}
    live_remaining = {}
    for ex in exercices:
        if ex["status"] == "closed":
            continue
        consumed = db.exercice_consumed(selected, ex["label"])
        live_consumed[ex["label"]] = consumed
        live_remaining[ex["label"]] = (
            None if ex["plafond"] is None else round(float(ex["plafond"]) - consumed, 2)
        )
    return render_template(
        "conventions.html",
        rows=rows,
        selected=selected,
        current=current,
        current_status=current_status,
        exercices=exercices,
        live_consumed=live_consumed,
        live_remaining=live_remaining,
        seed_imported=db.article_count() > 0,
        today=date.today().isoformat(),
        now_label=date.today().strftime("%d/%m/%Y"),
    )


@blueprint.get("/conventions/<int:cat_id>")
def detail(cat_id: int):
    """Fiche de suivi d'une convention : exercices, consommation, documents."""
    db = get_db()
    cat = next((c for c in db.list_categories() if int(c["id"]) == cat_id), None)
    if not cat:
        return render_template(
            "error.html", code=404, title="Convention introuvable",
            message="Cette convention n'existe plus.",
        ), 404
    name = cat["name"]
    status = db.effective_status(cat["status"], cat["expiry_date"])
    exercices = db.list_exercices(name)
    active = next((ex for ex in exercices if ex["status"] == "active"), None)
    summary = db.exercice_summary(name, active["label"]) if active else None
    consumed_total = round(
        sum(
            db.exercice_consumed(name, ex["label"]) if ex["status"] == "active"
            else float(ex["consumed_at_close"] or 0.0)
            for ex in exercices
        ),
        2,
    )
    documents = db.list_documents(category=name)[:20]
    return render_template(
        "convention_detail.html",
        cat=cat,
        status=status,
        exercices=exercices,
        active=active,
        summary=summary,
        articles=db.article_count(name),
        doc_total=len(db.list_documents(category=name)),
        consumed_total=consumed_total,
        documents=documents,
    )


# ------------------------------------------------------------- statut / échéance

@blueprint.post("/conventions/<int:cat_id>/status")
def set_status(cat_id: int):
    db = get_db()
    cat = next((c for c in db.list_categories() if int(c["id"]) == cat_id), None)
    if not cat:
        flash("Convention introuvable.", "error")
        return redirect(url_for("conventions.index"))
    status = request.form.get("status", "active")
    expiry = request.form.get("expiry_date", "").strip() or None
    try:
        db.set_category_status(cat["name"], status, expiry)
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        word = "activée" if status == "active" else "clôturée"
        flash(f"Convention « {cat['name']} » {word}.", "success")
    return redirect(url_for("conventions.index", category=cat["name"]))


@blueprint.post("/conventions/<int:cat_id>/delete")
def delete_list(cat_id: int):
    db = get_db()
    cat = next((c for c in db.list_categories() if int(c["id"]) == cat_id), None)
    if not cat:
        flash("Convention introuvable.", "error")
        return redirect(url_for("conventions.index"))
    if (request.form.get("confirm") or "").strip().casefold() != cat["name"].casefold():
        flash("Saisissez exactement le nom de la liste pour la supprimer.", "error")
        return redirect(url_for("conventions.index", category=cat["name"]))
    db.delete_category(cat["name"])
    flash(
        f"Liste « {cat['name']} » supprimée (articles et exercices effacés, "
        "commandes conservées dans l'historique).",
        "success",
    )
    return redirect(url_for("conventions.index"))


# ------------------------------------------------------------------- exercices

@blueprint.post("/conventions/<int:cat_id>/exercices")
def create_exercice(cat_id: int):
    db = get_db()
    cat = next((c for c in db.list_categories() if int(c["id"]) == cat_id), None)
    if not cat:
        flash("Convention introuvable.", "error")
        return redirect(url_for("conventions.index"))
    label = (request.form.get("label") or "").strip()
    start = (request.form.get("start_date") or "").strip()
    end = (request.form.get("end_date") or "").strip()
    close_current = request.form.get("close_current") == "on"
    try:
        plafond = parse_optional_amount(request.form.get("plafond"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("conventions.index", category=cat["name"]))
    try:
        db.create_exercice(
            cat["name"], label, start, end, plafond, close_current=close_current
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Exercice « {label} » ouvert pour « {cat['name']} ».", "success")
    return redirect(url_for("conventions.index", category=cat["name"]))


@blueprint.post("/conventions/exercices/<int:ex_id>/close")
def close_exercice(ex_id: int):
    db = get_db()
    row = db.get_exercice_by_id(ex_id)
    if not row:
        flash("Exercice introuvable.", "error")
        return redirect(url_for("conventions.index"))
    try:
        result = db.close_exercice(row["category"], row["label"])
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        remaining = result["remaining"]
        flash(
            f"Exercice « {result['label']} » clôturé — consommé "
            f"{result['consumed'] or 0:,.2f} DA, reste "
            + ("illimité." if remaining is None else f"{remaining:,.2f} DA."),
            "success",
        )
    return redirect(url_for("conventions.index", category=row["category"]))


@blueprint.post("/conventions/exercices/<int:ex_id>/update")
def update_exercice(ex_id: int):
    db = get_db()
    row = db.get_exercice_by_id(ex_id)
    if not row:
        flash("Exercice introuvable.", "error")
        return redirect(url_for("conventions.index"))
    start = (request.form.get("start_date") or "").strip() or None
    end = (request.form.get("end_date") or "").strip() or None
    try:
        plafond = parse_optional_amount(request.form.get("plafond"))
    except ValueError as exc:
        flash(str(exc), "error")
        return redirect(url_for("conventions.index", category=row["category"]))
    keep = request.form.get("keep_plafond") == "on"
    try:
        db.update_exercice(
            row["category"], row["label"], start, end, plafond, keep_plafond=keep
        )
    except ValueError as exc:
        flash(str(exc), "error")
    else:
        flash(f"Exercice « {row['label']} » mis à jour.", "success")
    return redirect(url_for("conventions.index", category=row["category"]))


# ---------------------------------------------------------------------- import

@blueprint.post("/conventions/import")
def import_upload():
    file = request.files.get("file")
    if not file or not file.filename:
        flash("Choisissez un classeur Excel (.xlsx).", "error")
        return redirect(url_for("conventions.index"))
    filename = (file.filename or "").lower()
    if not filename.endswith(".xlsx"):
        flash("Seuls les fichiers .xlsx sont acceptés.", "error")
        return redirect(url_for("conventions.index"))

    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stored = cfg.UPLOAD_DIR / f"import-{uuid.uuid4().hex}.xlsx"
    file.save(stored)
    try:
        sheets = read_sheet_names(stored)
    except Exception as exc:  # noqa: BLE001 - message affiché à l'utilisateur
        stored.unlink(missing_ok=True)
        flash(f"Classeur illisible : {exc}", "error")
        return redirect(url_for("conventions.index"))
    if not sheets:
        stored.unlink(missing_ok=True)
        flash("Ce classeur ne contient aucune feuille.", "error")
        return redirect(url_for("conventions.index"))

    session["import_path"] = str(stored)
    db = get_db()
    existing = {name.casefold(): name for name in db.category_names()}
    suggestions = [
        {
            "sheet": name,
            "target": existing.get(name.casefold(), name),
            "exists": existing.get(name.casefold(), name).casefold() in existing,
        }
        for name in sheets
    ]
    return render_template(
        "import_preview.html",
        suggestions=suggestions,
        categories=sorted(existing.values(), key=str.casefold),
        filename=Path(file.filename).name,
    )


@blueprint.post("/conventions/import/commit")
def import_commit():
    path = session.get("import_path")
    if not path or not Path(path).is_file():
        flash("Session d'import expirée : recommencez.", "error")
        return redirect(url_for("conventions.index"))
    sheets = request.form.getlist("sheet_name") or request.form.getlist("selected")
    if sheets and sheets[0].isdigit():
        # Formulaire indexé : une case cochée par feuille, cible associée.
        # La table est {convention de destination: feuille source}
        # (convention d'import_articles).
        indices = [int(value) for value in sheets]
        sheet_map = {}
        for index in indices:
            sheet = request.form.get(f"sheet_{index}", "").strip()
            target = request.form.get(f"target_{index}", "").strip()
            if sheet and target:
                sheet_map[target] = sheet
    else:
        targets = request.form.getlist("sheet_target")
        sheet_map = {}
        for sheet, target in zip(sheets, targets):
            target = (target or "").strip()
            if target:
                sheet_map[target] = sheet
    if not sheet_map:
        flash("Aucune feuille sélectionnée pour l'import.", "error")
        return redirect(url_for("conventions.index"))
    try:
        rows = import_articles(path, sheet_map)
        result = get_db().replace_articles_by_category(rows)
    except ValueError as exc:
        flash(f"Import refusé : {exc}", "error")
        return redirect(url_for("conventions.index"))
    finally:
        Path(path).unlink(missing_ok=True)
        session.pop("import_path", None)

    flash(
        f"{result['imported']} articles importés dans "
        f"{len(sheet_map)} liste(s). Les prix sont figés pour l'exercice.",
        "success",
    )
    return redirect(url_for("conventions.index"))


@blueprint.post("/conventions/import/seed")
def import_seed():
    source = cfg.seed_xlsx()
    if source is None:
        flash("Aucun classeur source trouvé (source_listes.xlsx).", "error")
        return redirect(url_for("conventions.index"))
    try:
        rows = import_articles(source)
        result = get_db().replace_articles_by_category(rows)
    except ValueError as exc:
        flash(f"Import refusé : {exc}", "error")
        return redirect(url_for("conventions.index"))
    flash(
        f"{result['imported']} articles importés depuis {source.name}.", "success"
    )
    return redirect(url_for("conventions.index"))


@blueprint.get("/conventions/template")
def template():
    db = get_db()
    payload, name = documents_service.export_template(db.category_names() or ["Liste"])
    return send_file(
        io.BytesIO(payload),
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=name,
    )
