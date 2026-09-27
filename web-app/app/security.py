"""Garde-fous de sécurité de l'application (monoposte, hors-ligne).

- liaisons uniquement sur ``127.0.0.1`` (voir ``serve.py``) ;
- jeton **CSRF** obligatoire sur toute requête de mutation (formulaires et API) ;
- en-têtes HTTP durcis (CSP, anti-clickjacking, nosniff) ;
- résolution de fichiers **sécurisée** : chemin relatif normalisé vérifié contre
  le dossier d'export (aucune traversée ``../`` possible) ;
- clé de signature de session générée localement, jamais versionnée.
"""
from __future__ import annotations

import hmac
import secrets
from pathlib import Path

from flask import Flask, abort, g, request, session

SAFE_METHODS = frozenset({"GET", "HEAD", "OPTIONS"})
CSRF_HEADER = "X-CSRF-Token"
# Script inline d'initialisation du thème (base.html, avant les CSS) : autorisé
# par hash CSP. En cas de modification du script, recalculer avec :
#   python -c "import base64,hashlib,re,pathlib; h=pathlib.Path('app/templates/base.html').read_text(); ..." \
#   et mettre à jour le test de fumée (section en-têtes de sécurité).
THEME_INIT_HASH = "sha256-HfkPbVOIlmPS3ZQMeSlzI9WLkhDNqto9CCKGMYe84BA="


def load_secret(path: Path) -> str:
    """Charge (ou crée) la clé de signature des sessions, à côté de l'application."""
    try:
        if path.is_file():
            value = path.read_text(encoding="utf-8").strip()
            if len(value) >= 32:
                return value
    except OSError:
        pass
    value = secrets.token_hex(32)
    try:
        path.write_text(value, encoding="utf-8")
    except OSError as exc:  # pragma: no cover - dossier en lecture seule
        raise RuntimeError(
            f"Impossible d'écrire la clé de session dans {path}."
        ) from exc
    return value


def csrf_token() -> str:
    token = session.get("csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["csrf_token"] = token
    g.csrf_token = token
    return token


def _request_token() -> str | None:
    token = request.headers.get(CSRF_HEADER)
    if token:
        return token
    if request.is_json:
        payload = request.get_json(silent=True)
        if isinstance(payload, dict):
            token = payload.get("csrf_token")
            if isinstance(token, str):
                return token
    form_token = request.form.get("csrf_token")
    return form_token if isinstance(form_token, str) else None


def _valid_token(token: str | None) -> bool:
    expected = session.get("csrf_token")
    if not expected or not token:
        return False
    return hmac.compare_digest(expected, token)


def install_security(app: Flask) -> None:
    @app.before_request
    def _check_csrf() -> None:
        if request.method in SAFE_METHODS:
            return
        if not _valid_token(_request_token()):
            if request.path.startswith("/api/") or request.is_json:
                return _json_csrf_error()
            abort(400, description="Jeton CSRF invalide ou manquant.")

    @app.after_request
    def _security_headers(response):
        response.headers.setdefault(
            "Content-Security-Policy",
            "default-src 'self'; "
            f"script-src 'self' '{THEME_INIT_HASH}'; "
            "style-src 'self' 'unsafe-inline'; "
            "img-src 'self' data:; "
            "font-src 'self'; "
            "connect-src 'self'; "
            "frame-ancestors 'none'; "
            "base-uri 'self'; "
            "form-action 'self'",
        )
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("Referrer-Policy", "no-referrer")
        response.headers.setdefault(
            "Permissions-Policy", "geolocation=(), microphone=(), camera=()"
        )
        response.headers.setdefault("Cross-Origin-Opener-Policy", "same-origin")
        if request.path.startswith("/api/") or request.is_json:
            response.headers.setdefault("Cache-Control", "no-store")
        return response

    @app.context_processor
    def _inject_csrf():
        return {"csrf_token": csrf_token()}

    def _json_csrf_error():
        from flask import jsonify

        response = jsonify({"error": "csrf", "message": "Jeton de sécurité invalide."})
        response.status_code = 400
        return response


def safe_export_path(base: Path, relative: str | None) -> Path | None:
    """Résout un chemin relatif stocké en base dans le dossier d'export.

    Renvoie ``None`` si le chemin est vide, absolu, ou s'il sort de ``base``.
    """
    if not relative:
        return None
    candidate = Path(str(relative))
    if candidate.is_absolute() or candidate.drive or ".." in candidate.parts:
        return None
    base_resolved = base.resolve()
    target = (base_resolved / candidate).resolve()
    try:
        target.relative_to(base_resolved)
    except ValueError:
        return None
    return target


def filename_safe(value: str, fallback: str = "fichier") -> str:
    """Nettoie un nom de fichier pour l'en-tête ``Content-Disposition``."""
    cleaned = "".join(
        ch for ch in str(value) if ch.isalnum() or ch in ("-", "_", ".", " ")
    ).strip()
    cleaned = cleaned.replace("..", "_")
    return cleaned or fallback
