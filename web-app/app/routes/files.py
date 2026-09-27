"""Téléchargement des PDF / Excel générés (résolution sécurisée)."""
from __future__ import annotations

from flask import Blueprint, abort, send_file

from app import config as cfg, get_db
from app.security import filename_safe, safe_export_path

blueprint = Blueprint("files", __name__)

KINDS = {"pdf": (".pdf", "application/pdf"), "xlsx": (".xlsx", None)}


@blueprint.get("/files/<int:document_id>/<kind>")
def document_file(document_id: int, kind: str):
    if kind not in KINDS:
        abort(404)
    doc = get_db().get_document(document_id)
    if not doc:
        abort(404)
    relative = doc["pdf_path"] if kind == "pdf" else doc["excel_path"]
    target = safe_export_path(cfg.EXPORT_DIR, relative)
    if target is None or not target.is_file():
        abort(404)

    from flask import request

    inline = request.args.get("inline") == "1" and kind == "pdf"
    _, mimetype = KINDS[kind]
    return send_file(
        target,
        mimetype=mimetype,
        as_attachment=not inline,
        download_name=filename_safe(target.name),
        conditional=False,
    )
