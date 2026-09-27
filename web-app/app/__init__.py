"""Fabrique de l'application Flask (monoposte, hors-ligne)."""
from __future__ import annotations

from flask import Flask, current_app, jsonify, render_template, request

from app import config as cfg
from app.database import (
    ArticlesManquants,
    ConflitPrix,
    Database,
    ExerciceManquant,
    PlafondAtteint,
)
from app.security import csrf_token, install_security, load_secret
from app.services import documents as documents_service
from app.utils import format_date, format_day, money_format, percent_format


def get_db() -> Database:
    return current_app.extensions["db"]


def create_app(test_config: dict | None = None) -> Flask:
    app = Flask(
        __name__,
        template_folder="templates",
        static_folder="static",
        static_url_path="/static",
    )
    app.config.update(
        SECRET_KEY=load_secret(cfg.SECRET_FILE),
        APP_NAME=cfg.APP_NAME,
        APP_SUBTITLE=cfg.APP_SUBTITLE,
        VERSION=cfg.VERSION,
        MAX_CONTENT_LENGTH=cfg.MAX_UPLOAD_BYTES,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_PATH="/",
        SEND_FILE_MAX_AGE_DEFAULT=0,
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    if not app.config.get("SECRET_KEY"):
        app.config["SECRET_KEY"] = load_secret(cfg.SECRET_FILE)

    app.extensions["db"] = Database(app.config.get("DB_PATH", cfg.DB_PATH))

    install_security(app)
    _register_filters(app)
    _register_errors(app)
    _register_commands(app)

    from app.routes.api import blueprint as api_bp
    from app.routes.conventions import blueprint as conventions_bp
    from app.routes.dashboard import blueprint as dashboard_bp
    from app.routes.documents import blueprint as documents_bp
    from app.routes.files import blueprint as files_bp
    from app.routes.history import blueprint as history_bp
    from app.routes.reports import blueprint as reports_bp
    from app.routes.settings import blueprint as settings_bp

    app.register_blueprint(dashboard_bp)
    app.register_blueprint(documents_bp)
    app.register_blueprint(history_bp)
    app.register_blueprint(conventions_bp)
    app.register_blueprint(reports_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(files_bp)
    app.register_blueprint(api_bp)

    @app.before_request
    def _touch_csrf() -> None:
        # Génère le jeton dès la première requête (formulaire ou API).
        if request.method == "GET":
            csrf_token()

    @app.context_processor
    def _navigation_state():
        endpoint = request.endpoint or ""
        return {"current_page": endpoint.split(".")[0]}

    documents_service.cleanup_tmp()
    cfg.EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    cfg.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

    return app


def _register_filters(app: Flask) -> None:
    app.jinja_env.filters["money"] = money_format
    app.jinja_env.filters["money_short"] = lambda v: (
        "—" if v is None else f"{float(v):,.2f}".replace(",", " ").replace(".", ",") + " DA"
    )
    app.jinja_env.filters["day"] = format_day
    app.jinja_env.filters["when"] = format_date
    app.jinja_env.filters["pct"] = percent_format
    app.jinja_env.globals.update(
        APP_NAME=cfg.APP_NAME,
        APP_SUBTITLE=cfg.APP_SUBTITLE,
        VERSION=cfg.VERSION,
        TVA_RATE=cfg.TVA_RATE,
        THEMES=cfg.THEMES,
        DEFAULT_THEME=cfg.DEFAULT_THEME,
        STATUS_LABEL={"active": "Actif", "closed": "Clôturé", "expiree": "Expiré"},
        STATUS_BADGE={"active": "success", "closed": "danger", "expiree": "warn"},
        NAV=(
            ("dashboard", "Tableau de bord", "/", "grid"),
            ("documents", "Nouvelle commande", "/documents/new", "file-plus"),
            ("history", "Historique", "/history", "clock"),
            ("conventions", "Conventions", "/conventions", "briefcase"),
            ("reports", "Rapport de consommation", "/reports", "chart"),
            ("settings", "Paramètres", "/settings", "gear"),
        ),
    )


def _wants_json() -> bool:
    return request.path.startswith("/api/") or request.is_json


def _register_errors(app: Flask) -> None:
    @app.errorhandler(404)
    def _not_found(_error):
        if _wants_json():
            return jsonify(error="not_found", message="Ressource introuvable."), 404
        return render_template("error.html", code=404,
                               title="Page introuvable",
                               message="Cette adresse n'existe pas dans l'application."), 404

    @app.errorhandler(400)
    def _bad_request(error):
        message = getattr(error, "description", None) or "Requête invalide."
        if _wants_json():
            return jsonify(error="bad_request", message=message), 400
        return render_template("error.html", code=400, title="Requête refusée",
                               message=message), 400

    @app.errorhandler(413)
    def _too_large(_error):
        message = "Fichier trop volumineux (20 Mo maximum)."
        if _wants_json():
            return jsonify(error="too_large", message=message), 413
        return render_template("error.html", code=413, title="Fichier trop lourd",
                               message=message), 413

    @app.errorhandler(500)
    def _server_error(_error):
        current_app.logger.exception("Erreur interne")
        if _wants_json():
            return jsonify(error="server_error", message="Erreur interne du serveur."), 500
        return render_template("error.html", code=500, title="Erreur interne",
                               message="L'opération a échoué. Vérifiez puis réessayez."), 500

    @app.errorhandler(PlafondAtteint)
    @app.errorhandler(ConflitPrix)
    @app.errorhandler(ArticlesManquants)
    @app.errorhandler(ExerciceManquant)
    @app.errorhandler(ValueError)
    def _business_error(error):
        payload = {"error": "business", "message": str(error)}
        if isinstance(error, ConflitPrix):
            payload["type"] = "price_conflict"
            payload["conflicts"] = error.conflicts
        elif isinstance(error, ArticlesManquants):
            payload["type"] = "missing_articles"
            payload["missing"] = error.missing
        elif isinstance(error, ExerciceManquant):
            payload["type"] = "missing_exercice"
            payload["category"] = error.category
            payload["exercice_label"] = error.label
        elif isinstance(error, PlafondAtteint):
            payload["type"] = "budget_block"
        if _wants_json():
            return jsonify(payload), 409
        return render_template("error.html", code=400, title="Opération refusée",
                               message=str(error).replace("\n", " ")), 400


def _register_commands(app: Flask) -> None:
    @app.cli.command("init-db")
    def init_db() -> None:
        """Recrée/initialise la base (les données existantes sont conservées)."""
        db: Database = app.extensions["db"]
        db.init_schema()
        print(f"Base prête : {db.path}")

    @app.cli.command("import-seed")
    def import_seed() -> None:
        """Importe le classeur source dans la base."""
        from app.importer import import_articles

        source = cfg.seed_xlsx()
        if source is None:
            print("Aucun classeur source trouvé.")
            return
        db: Database = app.extensions["db"]
        rows = import_articles(source)
        result = db.replace_articles_by_category(rows)
        print(f"{result['imported']} articles importés depuis {source.name}.")

    @app.cli.command("backup")
    def backup() -> None:
        """Copie de sauvegarde de la base."""
        import shutil
        from datetime import datetime

        db: Database = app.extensions["db"]
        target = cfg.BASE_DIR / (
            f"web_app-backup-{datetime.now():%Y%m%d-%H%M%S}.db"
        )
        shutil.copy2(db.path, target)
        print(f"Sauvegarde créée : {target}")
