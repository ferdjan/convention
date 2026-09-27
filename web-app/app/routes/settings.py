"""Écran : paramètres (thème, TVA, sauvegarde, à propos)."""
from __future__ import annotations

import sqlite3
import uuid
from datetime import datetime
from pathlib import Path

from flask import Blueprint, after_this_request, render_template, send_file

from app import config as cfg, get_db

blueprint = Blueprint("settings", __name__)


@blueprint.get("/settings")
def index():
    db = get_db()
    with db.connect() as conn:
        counts = {
            "categories": int(conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]),
            "exercices": int(conn.execute("SELECT COUNT(*) FROM exercices").fetchone()[0]),
            "articles": int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]),
            "documents": int(conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]),
        }
        version = conn.execute(
            "SELECT value FROM app_meta WHERE key = 'schema_version'"
        ).fetchone()
    try:
        export_dir = str(cfg.EXPORT_DIR.relative_to(cfg.BASE_DIR))
    except ValueError:
        export_dir = str(cfg.EXPORT_DIR)
    return render_template(
        "settings.html",
        counts=counts,
        schema_version=version[0] if version else "—",
        db_name=Path(cfg.DB_PATH).name,
        export_dir=export_dir,
        seed=cfg.seed_xlsx(),
    )


@blueprint.get("/settings/backup")
def backup():
    """Copie cohérente de la base (API ``VACUUM INTO`` de SQLite)."""
    db = get_db()
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = cfg.UPLOAD_DIR / f"web_app-backup-{stamp}-{uuid.uuid4().hex[:6]}.db"

    conn = sqlite3.connect(db.path)
    try:
        conn.execute("VACUUM INTO ?", (str(target),))
    finally:
        conn.close()

    @after_this_request
    def _cleanup(response):
        try:
            target.unlink()
        except OSError:
            pass
        return response

    return send_file(
        target,
        mimetype="application/x-sqlite3",
        as_attachment=True,
        download_name=f"web_app-backup-{stamp}.db",
    )
