"""Génère ``app/static/css/themes.css`` à partir de ``app.config.THEMES``.

Relancer après avoir modifié les thèmes :
    python tools/gen_themes.py
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.config import DEFAULT_THEME, THEMES  # noqa: E402

HEADER = """/* Fichier généré par tools/gen_themes.py — ne pas éditer à la main. */
:root {
  color-scheme: light;
}
"""

VAR_NAMES = {
    "primary": "--c-primary",
    "primary_dark": "--c-primary-dark",
    "bg": "--c-bg",
    "surface": "--c-surface",
    "card": "--c-card",
    "stripe": "--c-stripe",
    "text": "--c-text",
    "muted": "--c-muted",
    "border": "--c-border",
    "border_strong": "--c-border-strong",
    "accent": "--c-accent",
    "accent_hover": "--c-accent-hover",
    "accent_light": "--c-accent-light",
    "on_accent": "--c-on-accent",
    "on_primary": "--c-on-primary",
    "on_primary_muted": "--c-on-primary-muted",
    "success": "--c-success",
    "warn": "--c-warn",
    "danger": "--c-danger",
    "sidebar": "--c-sidebar",
    "sidebar_hover": "--c-sidebar-hover",
    "shadow": "--shadow",
    "shadow_lg": "--shadow-lg",
}

BUDGET_NAMES = {
    "ok": "--b-ok",
    "warn": "--b-warn",
    "critical": "--b-critical",
    "over": "--b-over",
    "none": "--b-none",
}


DARK_THEMES = {"sombre"}


def main() -> None:
    parts = [HEADER]
    for name, theme in THEMES.items():
        # Un seul bloc par thème : couleurs + budget + color-scheme.
        if name != DEFAULT_THEME:
            selector = f'[data-theme="{name}"]'
        else:
            selector = f'[data-theme="{name}"],\n:root'
        merged = dict(theme["colors"])
        for key, value in theme["budget"].items():
            merged[f"budget_{key}"] = value
        mapping = dict(VAR_NAMES)
        mapping.update({f"budget_{key}": css_var for key, css_var in BUDGET_NAMES.items()})
        lines = [selector, " {"]
        for source, css_var in mapping.items():
            if source in merged:
                lines.append(f"  {css_var}: {merged[source]};")
        lines.append(
            f"  color-scheme: {'dark' if name in DARK_THEMES else 'light'};"
        )
        lines.append("}")
        parts.append("\n".join(lines))
    target = ROOT / "app" / "static" / "css" / "themes.css"
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text("\n\n".join(parts) + "\n", encoding="utf-8")
    print(f"{target} ({len(THEMES)} thèmes)")


if __name__ == "__main__":
    main()
