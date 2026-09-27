"""Point d'entrée local : http://127.0.0.1:8765

Usage :
    python serve.py            # serveur standard (recommandé hors-ligne)
    python serve.py --dev      # rechargement automatique (développement)
    python serve.py --port 8080
"""
from __future__ import annotations

import argparse
import sys

from app import create_app
from app import config as cfg


def main(argv: list[str] | None = None) -> int:
    # Console Windows : évite l'erreur d'encodage sur les caractères UTF-8.
    for stream in (sys.stdout, sys.stderr):
        if hasattr(stream, "reconfigure"):
            try:
                stream.reconfigure(encoding="utf-8", errors="replace")
            except (OSError, ValueError):  # pragma: no cover - flux spécial
                pass

    parser = argparse.ArgumentParser(description="Serveur local Gestion Articles (web)")
    parser.add_argument("--host", default=cfg.HOST, help="adresse d'écoute (127.0.0.1)")
    parser.add_argument("--port", type=int, default=cfg.PORT, help="port d'écoute")
    parser.add_argument("--dev", action="store_true", help="mode développement (debug)")
    args = parser.parse_args(argv)

    if args.host not in ("127.0.0.1", "localhost", "::1"):
        print(
            "Refus : l'application est conçue pour rester sur la machine locale "
            f"(host={args.host}).",
            file=sys.stderr,
        )
        return 2

    app = create_app()
    app.config["DEBUG"] = bool(args.dev)
    if args.dev:
        app.config["TEMPLATES_AUTO_RELOAD"] = True

    print(f"Gestion Articles (web) → http://{args.host}:{args.port}")
    print("Appuyez sur Ctrl+C pour arrêter.")
    app.run(host=args.host, port=args.port, debug=bool(args.dev), use_reloader=bool(args.dev))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
