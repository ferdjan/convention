"""Couche SQLite de l'application web.

Robustesse :
- schéma versionné (``app_meta.schema_version``), migration transactionnelle ;
- ``WAL`` + ``foreign_keys`` + ``busy_timeout`` : écritures sûres, lecture
  possible même si un autre processus lit la base ;
- toutes les requêtes sont paramétrées (aucune interpolation utilisateur) ;
- chemins de fichiers **relatifs** à ``EXPORT_DIR`` (aucun chemin absolu en base).

Règles métier identiques à l'édition bureau, avec deux corrections :
- la convention **expirée** est aussi refusée par la base (pas seulement par
  l'interface) ;
- le contrôle de plafond est écrit **une seule fois** (``_assert_within_plafond``)
  et réutilisé pour la création et la modification.
"""
from __future__ import annotations

import math
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

from app.config import (
    BUDGET_BLOCK,
    BUDGET_CRITICAL,
    BUDGET_WARN,
    DEFAULT_CATEGORIES,
    DEFAULT_PREFIXES,
    TVA_RATE,
)
from app.utils import compute_totals

SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL COLLATE NOCASE UNIQUE,
    sheet_name TEXT,
    prefix TEXT,
    status TEXT NOT NULL DEFAULT 'active',
    expiry_date TEXT
);

CREATE TABLE IF NOT EXISTS app_meta (
    key TEXT PRIMARY KEY,
    value TEXT
);

CREATE TABLE IF NOT EXISTS exercices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    label TEXT NOT NULL,
    start_date TEXT NOT NULL,
    end_date TEXT NOT NULL,
    plafond REAL,
    status TEXT NOT NULL DEFAULT 'active',
    consumed_at_close REAL,
    remaining_at_close REAL,
    closed_at TEXT,
    UNIQUE(category, label)
);

CREATE INDEX IF NOT EXISTS idx_exercices_category ON exercices(category);
CREATE INDEX IF NOT EXISTS idx_exercices_status ON exercices(category, status);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    designation TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_ht REAL NOT NULL CHECK(unit_price_ht >= 0),
    UNIQUE(category, code, designation, unit)
);

CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
CREATE INDEX IF NOT EXISTS idx_articles_search ON articles(category, code, designation);

CREATE TABLE IF NOT EXISTS documents (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    number TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL,
    category TEXT NOT NULL,
    total_ht REAL NOT NULL,
    tva_rate REAL,
    tva_amount REAL,
    total_ttc REAL,
    pdf_path TEXT,
    excel_path TEXT,
    exercice_label TEXT
);

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_documents_exercice ON documents(category, exercice_label);

CREATE TABLE IF NOT EXISTS document_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    document_id INTEGER NOT NULL,
    article_id INTEGER,
    code TEXT NOT NULL,
    designation TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_ht REAL NOT NULL,
    quantity REAL NOT NULL CHECK(quantity > 0),
    total_ht REAL NOT NULL,
    FOREIGN KEY(document_id) REFERENCES documents(id) ON DELETE CASCADE,
    FOREIGN KEY(article_id) REFERENCES articles(id) ON DELETE SET NULL
);

CREATE INDEX IF NOT EXISTS idx_document_items_document ON document_items(document_id);
"""


class PlafondAtteint(ValueError):
    """Blocage ferme du plafond (message prêt pour l'interface)."""


class ConflitPrix(ValueError):
    """Les prix envoyés ne correspondent plus à la liste active."""

    def __init__(self, conflicts: list[dict]):
        super().__init__("Les prix de certains articles ont changé.")
        self.conflicts = conflicts


class ArticlesManquants(ValueError):
    """Des articles du panier n'existent plus dans la liste."""

    def __init__(self, missing: list[dict]):
        super().__init__("Certains articles n'existent plus dans la liste.")
        self.missing = missing


class ExerciceManquant(ValueError):
    """Aucun exercice actif exploitable pour la convention.

    Porte la convention (et le libellé éventuel) : l'interface peut alors
    proposer directement l'ouverture d'un exercice.
    """

    def __init__(self, message: str, category: str, label: str | None = None):
        super().__init__(message)
        self.category = category
        self.label = label


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    # --------------------------------------------------------------- connexion

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path, timeout=15)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ---------------------------------------------------------- schéma/version

    def init_schema(self) -> None:
        is_new = not self.path.exists() or self.path.stat().st_size == 0
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN IMMEDIATE")
            self._execute_script(conn, SCHEMA)
            self._migrate(conn)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise sqlite3.IntegrityError(self._format_fk_violations(violations))
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES ('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (str(SCHEMA_VERSION),),
            )
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()

        include_defaults = is_new
        with self.connect() as conn:
            count = int(conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0])
            marker = conn.execute(
                "SELECT value FROM app_meta WHERE key = 'defaults_seeded'"
            ).fetchone()
        if count == 0 and not marker:
            include_defaults = True
        self._ensure_categories(include_defaults=include_defaults)
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES ('defaults_seeded', '1') "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value"
            )

    @staticmethod
    def _execute_script(conn: sqlite3.Connection, script: str) -> None:
        statement = ""
        for line in script.splitlines(keepends=True):
            statement += line
            if sqlite3.complete_statement(statement):
                if statement.strip():
                    conn.execute(statement)
                statement = ""
        if statement.strip():
            conn.execute(statement)

    @staticmethod
    def _format_fk_violations(violations: Iterable[sqlite3.Row]) -> str:
        details = []
        for row in violations:
            values = list(row)
            while len(values) < 4:
                values.append(None)
            table, rowid, parent, fkid = values[:4]
            details.append(f"table {table}, ligne {rowid}, table parente {parent}")
        return "Échec du contrôle des clés étrangères : " + "; ".join(details[:10]) + "."

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))

    def _migrate(self, conn: sqlite3.Connection) -> None:
        """Migration idempotente (bases venues de l'édition bureau)."""
        for column, definition in (
            ("sheet_name", "TEXT"),
            ("prefix", "TEXT"),
            ("status", "TEXT NOT NULL DEFAULT 'active'"),
            ("expiry_date", "TEXT"),
        ):
            if not self._column_exists(conn, "categories", column):
                conn.execute(f"ALTER TABLE categories ADD COLUMN {column} {definition}")

        for column, definition in (
            ("pdf_path", "TEXT"),
            ("excel_path", "TEXT"),
            ("tva_rate", "REAL"),
            ("tva_amount", "REAL"),
            ("total_ttc", "REAL"),
            ("exercice_label", "TEXT"),
        ):
            if not self._column_exists(conn, "documents", column):
                conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")

        conn.execute("UPDATE documents SET tva_rate = ? WHERE tva_rate IS NULL", (TVA_RATE,))
        conn.execute(
            "UPDATE documents SET tva_amount = ROUND(total_ht * tva_rate, 2) "
            "WHERE tva_amount IS NULL"
        )
        conn.execute(
            "UPDATE documents SET total_ttc = ROUND(total_ht + tva_amount, 2) "
            "WHERE total_ttc IS NULL"
        )
        conn.execute(
            "UPDATE categories SET status = 'active' WHERE status IS NULL OR status = ''"
        )

    # ------------------------------------------------------------- conventions

    def list_categories(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, name, sheet_name, prefix, status, expiry_date "
                "FROM categories ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def category_names(self) -> list[str]:
        return [row["name"] for row in self.list_categories()]

    @staticmethod
    def effective_status(status: str | None, expiry_date: str | None) -> str:
        """``active``, ``closed`` (clôturée) ou ``expiree`` (échéance dépassée)."""
        if (status or "active") != "active":
            return "closed"
        if expiry_date and expiry_date < date.today().isoformat():
            return "expiree"
        return "active"

    def active_category_names(self) -> list[str]:
        return [
            row["name"]
            for row in self.list_categories()
            if self.effective_status(row["status"], row["expiry_date"]) == "active"
        ]

    def category_row(self, name: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, name, sheet_name, prefix, status, expiry_date "
                "FROM categories WHERE name = ? COLLATE NOCASE",
                ((name or "").strip(),),
            ).fetchone()

    def set_category_status(
        self, name: str, status: str, expiry_date: str | None = None
    ) -> None:
        normalized = "active" if status == "active" else "closed"
        with self.connect() as conn:
            cursor = conn.execute(
                "UPDATE categories SET status = ?, expiry_date = ? WHERE name = ?",
                (normalized, expiry_date, name),
            )
            if cursor.rowcount == 0:
                raise ValueError(f"Convention inconnue : {name}")

    def delete_category(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM articles WHERE category = ?", (name,))
            conn.execute("DELETE FROM exercices WHERE category = ?", (name,))
            conn.execute("DELETE FROM categories WHERE name = ?", (name,))

    def category_prefix(self, name: str) -> str:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT prefix FROM categories WHERE name = ? COLLATE NOCASE",
                ((name or "").strip(),),
            ).fetchone()
        return (row[0] if row and row[0] else self._make_prefix(name)) or "DOC"

    @staticmethod
    def _make_prefix(name: str) -> str:
        letters = "".join(ch for ch in name.upper() if ch.isalnum())
        return letters[:3] or "DOC"

    @staticmethod
    def _unique_prefix(
        conn: sqlite3.Connection, base: str, exclude_name: str | None = None
    ) -> str:
        base = (base or "DOC")[:3].upper()
        rows = conn.execute(
            "SELECT name, prefix FROM categories WHERE prefix IS NOT NULL AND prefix <> ''"
        ).fetchall()
        used = {r["prefix"] for r in rows if r["name"] != exclude_name}
        if base not in used:
            return base
        for index in range(1, 10000):
            candidate = f"{base[:2]}{index}" if index < 10 else f"{base[0]}{index:02d}"
            if candidate not in used:
                return candidate[:3]
        raise ValueError("Impossible de générer un préfixe unique.")

    def _ensure_categories(self, include_defaults: bool = False) -> None:
        with self.connect() as conn:
            names = list(DEFAULT_CATEGORIES) if include_defaults else []
            names.extend(
                row[0]
                for row in conn.execute(
                    "SELECT DISTINCT category FROM articles ORDER BY category"
                )
            )
            existing = {
                row["name"].casefold()
                for row in conn.execute("SELECT name FROM categories")
            }
            for name in names:
                if not name or name.casefold() in existing:
                    continue
                prefix = DEFAULT_PREFIXES.get(name) or self._make_prefix(name)
                conn.execute(
                    "INSERT OR IGNORE INTO categories(name, sheet_name, prefix) "
                    "VALUES (?, ?, ?)",
                    (name, name, self._unique_prefix(conn, prefix)),
                )
                existing.add(name.casefold())
            for row in conn.execute("SELECT name, prefix FROM categories").fetchall():
                if row["prefix"]:
                    continue
                conn.execute(
                    "UPDATE categories SET prefix = ? WHERE name = ?",
                    (
                        self._unique_prefix(
                            conn,
                            self._make_prefix(row["name"]),
                            exclude_name=row["name"],
                        ),
                        row["name"],
                    ),
                )

    def _ensure_category_row(self, conn: sqlite3.Connection, name: str) -> str:
        name = self._resolve_category_name(conn, name)
        if conn.execute(
            "SELECT 1 FROM categories WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone():
            return name
        prefix = DEFAULT_PREFIXES.get(name) or self._make_prefix(name)
        conn.execute(
            "INSERT INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
            (name, name, self._unique_prefix(conn, prefix)),
        )
        return name

    # -------------------------------------------------------------- exercices

    def list_exercices(self, category: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, category, label, start_date, end_date, plafond, status, "
                "consumed_at_close, remaining_at_close, closed_at "
                "FROM exercices WHERE category = ? COLLATE NOCASE "
                "ORDER BY start_date DESC, id DESC",
                (category,),
            ).fetchall()

    def list_all_exercices(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, category, label, start_date, end_date, plafond, status, "
                "consumed_at_close, remaining_at_close, closed_at FROM exercices "
                "ORDER BY category COLLATE NOCASE, start_date DESC, id DESC"
            ).fetchall()

    def exercice_labels(self) -> list[str]:
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT label FROM exercices ORDER BY label DESC"
            ).fetchall()
        return [row["label"] for row in rows]

    def get_exercice(self, category: str, label: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM exercices WHERE category = ? COLLATE NOCASE AND label = ?",
                (category, label),
            ).fetchone()

    def get_exercice_by_id(self, exercice_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM exercices WHERE id = ?", (exercice_id,)
            ).fetchone()

    def get_active_exercice(self, category: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM exercices WHERE category = ? COLLATE NOCASE "
                "AND status = 'active' ORDER BY start_date DESC, id DESC LIMIT 1",
                (category,),
            ).fetchone()

    @staticmethod
    def _validate_exercice_dates(label: str, start_date: str, end_date: str) -> None:
        try:
            start = date.fromisoformat(start_date)
            end = date.fromisoformat(end_date)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Dates d'exercice invalides (format attendu AAAA-MM-JJ)."
            ) from exc
        if start >= end:
            raise ValueError("La date de début doit précéder la date de fin.")
        if not label or not label.strip():
            raise ValueError("Le libellé d'exercice ne peut pas être vide.")

    def create_exercice(
        self,
        category: str,
        label: str,
        start_date: str,
        end_date: str,
        plafond: float | None = None,
        close_current: bool = False,
    ) -> int:
        label = (label or "").strip()
        self._validate_exercice_dates(label, start_date, end_date)
        with self.connect() as conn:
            category = self._resolve_category_name(conn, category)
            if conn.execute(
                "SELECT 1 FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone():
                raise ValueError(
                    f"L'exercice « {label} » existe déjà pour la convention « {category} »."
                )
            if close_current:
                self._close_active_exercice(conn, category)
            elif conn.execute(
                "SELECT 1 FROM exercices WHERE category = ? AND status = 'active'",
                (category,),
            ).fetchone():
                raise ValueError(
                    f"La convention « {category} » a déjà un exercice actif. "
                    "Clôturez-le avant d'en ouvrir un autre."
                )
            cursor = conn.execute(
                "INSERT INTO exercices(category, label, start_date, end_date, plafond, status) "
                "VALUES (?, ?, ?, ?, ?, 'active')",
                (category, label, start_date, end_date, plafond),
            )
            return int(cursor.lastrowid)

    def update_exercice(
        self,
        category: str,
        label: str,
        start_date: str | None = None,
        end_date: str | None = None,
        plafond: float | None = None,
        keep_plafond: bool = False,
    ) -> None:
        """Mise à jour des dates/plafond d'un exercice.

        ``keep_plafond=True`` conserve le plafond existant (utile pour un
        exercice clos dont l'instantané doit rester cohérent).
        """
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()
            if not row:
                raise ValueError(
                    f"Exercice « {label} » introuvable pour la convention « {category} »."
                )
            new_start = start_date or row["start_date"]
            new_end = end_date or row["end_date"]
            self._validate_exercice_dates(label, new_start, new_end)
            new_plafond = row["plafond"] if keep_plafond else plafond
            if row["status"] == "closed" and not keep_plafond and new_plafond is not None:
                # Un exercice clos garde son instantané : on recalcule le reste.
                consumed = float(row["consumed_at_close"] or 0.0)
                conn.execute(
                    "UPDATE exercices SET start_date = ?, end_date = ?, plafond = ?, "
                    "remaining_at_close = ROUND(? - ?, 2) WHERE id = ?",
                    (new_start, new_end, new_plafond, new_plafond, consumed, row["id"]),
                )
            else:
                conn.execute(
                    "UPDATE exercices SET start_date = ?, end_date = ?, plafond = ? "
                    "WHERE id = ?",
                    (new_start, new_end, new_plafond, row["id"]),
                )

    def _close_active_exercice(self, conn: sqlite3.Connection, category: str) -> None:
        row = conn.execute(
            "SELECT * FROM exercices WHERE category = ? AND status = 'active' "
            "ORDER BY start_date DESC, id DESC LIMIT 1",
            (category,),
        ).fetchone()
        if not row:
            return
        consumed = self._consumed_in(conn, category, row["label"])
        plafond = None if row["plafond"] is None else float(row["plafond"])
        remaining = None if plafond is None else round(plafond - consumed, 2)
        conn.execute(
            "UPDATE exercices SET status = 'closed', consumed_at_close = ?, "
            "remaining_at_close = ?, closed_at = ? WHERE id = ?",
            (
                consumed,
                remaining,
                datetime.now().isoformat(timespec="seconds"),
                row["id"],
            ),
        )

    @staticmethod
    def _consumed_in(
        conn: sqlite3.Connection, category: str, label: str, exclude_id=None
    ) -> float:
        sql = (
            "SELECT COALESCE(SUM(total_ht), 0) FROM documents "
            "WHERE category = ? COLLATE NOCASE AND exercice_label = ?"
        )
        params: list[object] = [category, label]
        if exclude_id is not None:
            sql += " AND id != ?"
            params.append(exclude_id)
        return round(float(conn.execute(sql, params).fetchone()[0] or 0.0), 2)

    def close_exercice(self, category: str, label: str) -> dict:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()
            if not row:
                raise ValueError(
                    f"Exercice « {label} » introuvable pour la convention « {category} »."
                )
            if row["status"] != "active":
                raise ValueError("Cet exercice est déjà clôturé.")
            self._close_active_exercice(conn, category)
            refreshed = conn.execute(
                "SELECT * FROM exercices WHERE id = ?", (row["id"],)
            ).fetchone()
            return {
                "category": category,
                "label": label,
                "plafond": refreshed["plafond"],
                "consumed": refreshed["consumed_at_close"],
                "remaining": refreshed["remaining_at_close"],
                "closed_at": refreshed["closed_at"],
            }

    def exercice_consumed(self, category: str, label: str) -> float:
        with self.connect() as conn:
            return self._consumed_in(conn, category, label)

    def exercice_summary(self, category: str, label: str) -> dict:
        """Synthèse budgétaire : ``none`` / ``ok`` / ``warn`` / ``critical`` / ``over``."""
        row = self.get_exercice(category, label)
        base = {
            "category": category,
            "label": label,
            "plafond": None,
            "consumed": 0.0,
            "remaining": None,
            "rate": None,
            "state": "none",
            "start_date": None,
            "end_date": None,
            "status": None,
        }
        if not row:
            return base
        consumed = self.exercice_consumed(category, label)
        base.update(
            consumed=consumed,
            start_date=row["start_date"],
            end_date=row["end_date"],
            status=row["status"],
        )
        if row["plafond"] is None:
            return base
        plafond = float(row["plafond"])
        rate = (consumed / plafond) if plafond else 0.0
        if plafond and rate >= BUDGET_BLOCK:
            state = "over"
        elif plafond and rate >= BUDGET_CRITICAL:
            state = "critical"
        elif plafond and rate >= BUDGET_WARN:
            state = "warn"
        else:
            state = "ok"
        base.update(
            plafond=plafond,
            remaining=round(plafond - consumed, 2),
            rate=rate,
            state=state,
        )
        return base

    def budget_status(
        self, category: str, amount: float = 0.0, exclude_document: int | None = None
    ) -> dict:
        """Plafond / consommé / projection pour l'interface et le contrôle serveur.

        ``exclude_document`` retire un document du consommé (mode modification).
        """
        exercice = self.get_active_exercice(category)
        if not exercice:
            return {
                "has_exercice": False,
                "exercice": None,
                "plafond": None,
                "consumed": 0.0,
                "document": round(float(amount or 0.0), 2),
                "projected": round(float(amount or 0.0), 2),
                "remaining": None,
                "rate": None,
                "state": "none",
                "blocked": False,
            }
        with self.connect() as conn:
            consumed = self._consumed_in(
                conn, category, exercice["label"], exclude_id=exclude_document
            )
        document_amount = round(float(amount or 0.0), 2)
        projected = round(consumed + document_amount, 2)
        plafond = None if exercice["plafond"] is None else float(exercice["plafond"])
        blocked = False
        state = "none"
        rate = None
        remaining = None
        if plafond is not None:
            blocked = projected >= round(plafond, 2)
            rate = (consumed / plafond) if plafond else 0.0
            remaining = round(plafond - consumed, 2)
            if rate >= BUDGET_BLOCK:
                state = "over"
            elif rate >= BUDGET_CRITICAL:
                state = "critical"
            elif rate >= BUDGET_WARN:
                state = "warn"
            else:
                state = "ok"
        return {
            "has_exercice": True,
            "exercice": {
                "label": exercice["label"],
                "start_date": exercice["start_date"],
                "end_date": exercice["end_date"],
                "status": exercice["status"],
            },
            "plafond": plafond,
            "consumed": consumed,
            "document": document_amount,
            "projected": projected,
            "remaining": remaining,
            "rate": rate,
            "state": state,
            "blocked": blocked,
        }

    def exercice_would_exceed(
        self, category: str, amount: float, exclude_document: int | None = None
    ) -> bool:
        return bool(
            self.budget_status(category, amount, exclude_document)["blocked"]
        )

    # --------------------------------------------------------------- articles

    def article_count(self, category: str | None = None) -> int:
        with self.connect() as conn:
            if category:
                return int(
                    conn.execute(
                        "SELECT COUNT(*) FROM articles WHERE category = ? COLLATE NOCASE",
                        (category,),
                    ).fetchone()[0]
                )
            return int(conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0])

    def search_articles(self, category: str, text: str = "", limit: int = 300):
        text = (text or "").strip()
        with self.connect() as conn:
            if text:
                like = f"%{text}%"
                return conn.execute(
                    """
                    SELECT id, code, designation, unit, unit_price_ht
                    FROM articles
                    WHERE category = ? COLLATE NOCASE
                      AND (code LIKE ? OR designation LIKE ? OR unit LIKE ?)
                    ORDER BY CAST(code AS INTEGER), designation
                    LIMIT ?
                    """,
                    (category, like, like, like, limit),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, code, designation, unit, unit_price_ht
                FROM articles
                WHERE category = ? COLLATE NOCASE
                ORDER BY CAST(code AS INTEGER), designation
                LIMIT ?
                """,
                (category, limit),
            ).fetchall()

    def get_article(self, article_id: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, category, code, designation, unit, unit_price_ht "
                "FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()

    @staticmethod
    def _prepare_rows(rows):
        prepared = []
        seen: dict[tuple, float] = {}
        for category, code, designation, unit, price in rows:
            values = (
                str(category or "").strip(),
                str(code or "").strip(),
                str(designation or "").strip(),
                str(unit or "").strip(),
            )
            if not all(values):
                raise ValueError(
                    "Chaque ligne importée doit renseigner la liste, le code, "
                    "la désignation et l'unité."
                )
            try:
                price = float(price)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Prix invalide pour {values[1]}.") from exc
            if not math.isfinite(price) or price < 0:
                raise ValueError(f"Prix invalide pour {values[1]}.")
            if values in seen:
                if abs(seen[values] - price) > 0.0001:
                    raise ValueError(
                        f"Confusion de prix pour {values[1]} / {values[2]} / {values[3]}."
                    )
                continue
            seen[values] = price
            prepared.append((*values, price))
        return prepared

    def replace_articles_by_category(self, rows) -> dict:
        """Remplace la liste des articles des conventions concernées (prix figés)."""
        prepared = self._prepare_rows(rows)
        with self.connect() as conn:
            canonical: dict[str, str] = {}
            for category in dict.fromkeys(row[0] for row in prepared):
                canonical[category] = self._ensure_category_row(conn, category)
            grouped: dict[str, list[tuple]] = {}
            for row_category, code, designation, unit, price in prepared:
                name = canonical[row_category]
                grouped.setdefault(name, []).append((name, code, designation, unit, price))
            total = 0
            for name, category_rows in grouped.items():
                unique: list[tuple] = []
                seen: dict[tuple, float] = {}
                for row in category_rows:
                    key = row[:4]
                    if key in seen:
                        if abs(seen[key] - row[4]) > 0.0001:
                            raise ValueError(f"Confusion de prix pour {row[1]}.")
                        continue
                    seen[key] = row[4]
                    unique.append(row)
                conn.execute("DELETE FROM articles WHERE category = ?", (name,))
                conn.executemany(
                    "INSERT INTO articles(category, code, designation, unit, unit_price_ht) "
                    "VALUES (?, ?, ?, ?, ?)",
                    unique,
                )
                total += len(unique)
        return {"imported": total}

    def replace_articles(self, rows) -> int:
        """Remplace **toutes** les listes (réservé à une base vide)."""
        prepared = self._prepare_rows(rows)
        with self.connect() as conn:
            conn.execute("DELETE FROM articles")
            conn.executemany(
                "INSERT INTO articles(category, code, designation, unit, unit_price_ht) "
                "VALUES (?, ?, ?, ?, ?)",
                [
                    (self._ensure_category_row(conn, category), code, designation, unit, price)
                    for category, code, designation, unit, price in prepared
                ],
            )
        return len(prepared)

    # -------------------------------------------------------------- documents

    def next_document_number(
        self, category: str | None = None, exercice_label: str | None = None
    ) -> str:
        if not exercice_label:
            exercice_label = str(datetime.now().year)
        prefix = self.category_prefix(category) if category else "DOC"
        number_prefix = f"{prefix}-{exercice_label}-"
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT number FROM documents WHERE number LIKE ?",
                (f"{number_prefix}%",),
            ).fetchall()
        seq = 0
        for row in rows:
            try:
                seq = max(seq, int(str(row[0]).rsplit("-", 1)[-1]))
            except (ValueError, IndexError):
                continue
        return f"{number_prefix}{seq + 1:04d}"

    def document_number_exists(self, number: str) -> bool:
        with self.connect() as conn:
            return (
                conn.execute(
                    "SELECT 1 FROM documents WHERE number = ?", (number,)
                ).fetchone()
                is not None
            )

    @staticmethod
    def _assert_within_plafond(
        conn: sqlite3.Connection,
        category: str,
        exercice: sqlite3.Row,
        total_ht: float,
        exclude_id: int | None = None,
    ) -> None:
        """Blocage ferme : ``consommé (+ projection) >= plafond`` refuse l'écriture."""
        if exercice["plafond"] is None:
            return
        other = Database._consumed_in(
            conn, category, exercice["label"], exclude_id=exclude_id
        )
        projected = round(other + total_ht, 2)
        plafond = round(float(exercice["plafond"]), 2)
        if projected >= plafond:
            raise PlafondAtteint(
                "PLAFOND ATTEINT : l'enregistrement est bloqué.\n"
                f"Consommé{' hors cette commande' if exclude_id else ''} : {other:.2f} DA "
                f"+ cette commande {total_ht:.2f} DA = {projected:.2f} DA pour un plafond "
                f"de {plafond:.2f} DA.\n"
                "Aucun dépassement n'est autorisé sur cette convention."
            )

    @staticmethod
    def _validate_category_open(conn: sqlite3.Connection, category: str) -> None:
        row = conn.execute(
            "SELECT status, expiry_date FROM categories WHERE name = ? COLLATE NOCASE",
            (category,),
        ).fetchone()
        if not row:
            raise ValueError(f"Convention inconnue : {category}")
        status = Database.effective_status(row["status"], row["expiry_date"])
        if status == "closed":
            raise ValueError(
                f"La convention « {category} » est clôturée : "
                "aucune nouvelle commande ne peut y être enregistrée."
            )
        if status == "expiree":
            raise ValueError(
                f"La convention « {category} » est expirée : "
                "aucune nouvelle commande ne peut y être enregistrée."
            )

    def _resolve_items(
        self,
        conn: sqlite3.Connection,
        category: str,
        items: list[dict],
        accept_new_prices: bool,
    ) -> tuple[list[dict], list[dict]]:
        """Valide les lignes et renvoie ``(lignes résolues, conflits de prix)``.

        Une ligne est envoyée par ``article_id`` ; le prix est **toujours** repris
        en base (jamais fait confiance au client). Si le prix a changé et que
        ``accept_new_prices`` est faux, un conflit est remonté à l'interface.
        """
        resolved: list[dict] = []
        conflicts: list[dict] = []
        missing: list[dict] = []
        seen_ids: set[int] = set()
        for raw in items:
            article_id = raw.get("article_id")
            try:
                article_id = int(article_id)
            except (TypeError, ValueError):
                raise ValueError("Ligne de panier invalide.")
            if article_id in seen_ids:
                continue
            seen_ids.add(article_id)
            article = conn.execute(
                "SELECT id, category, code, designation, unit, unit_price_ht "
                "FROM articles WHERE id = ?",
                (article_id,),
            ).fetchone()
            if article is None or article["category"].casefold() != category.casefold():
                missing.append(
                    {
                        "article_id": article_id,
                        "code": str(raw.get("code") or ""),
                        "designation": str(raw.get("designation") or ""),
                    }
                )
                continue
            sent_price = raw.get("unit_price_ht")
            if sent_price is not None:
                try:
                    sent_price = float(sent_price)
                except (TypeError, ValueError):
                    sent_price = None
            if sent_price is not None and abs(sent_price - float(article["unit_price_ht"])) > 0.0001:
                conflicts.append(
                    {
                        "article_id": int(article["id"]),
                        "code": article["code"],
                        "designation": article["designation"],
                        "unit": article["unit"],
                        "old_price": round(sent_price, 2),
                        "new_price": float(article["unit_price_ht"]),
                    }
                )
                if not accept_new_prices:
                    continue
            resolved.append(
                {
                    "article_id": int(article["id"]),
                    "code": article["code"],
                    "designation": article["designation"],
                    "unit": article["unit"],
                    "unit_price_ht": float(article["unit_price_ht"]),
                    "quantity": float(raw.get("quantity") or 0),
                }
            )
        if missing:
            raise ArticlesManquants(missing)
        if conflicts and not accept_new_prices:
            raise ConflitPrix(conflicts)
        for line in resolved:
            if not math.isfinite(line["quantity"]) or line["quantity"] <= 0:
                raise ValueError(
                    f"La quantité de {line['code']} doit être strictement positive."
                )
        if not resolved:
            raise ValueError("Une commande doit contenir au moins une ligne.")
        return resolved, conflicts

    def save_document(
        self,
        number: str,
        created_at: str,
        category: str,
        items: list[dict],
        tva_rate: float = TVA_RATE,
        exercice_label: str | None = None,
        pdf_path: str | None = None,
        excel_path: str | None = None,
        accept_new_prices: bool = False,
    ) -> tuple[int, float, float, float]:
        if not items:
            raise ValueError("Une commande doit contenir au moins une ligne.")
        with self.connect() as conn:
            category = self._resolve_category_name(conn, category)
            self._validate_category_open(conn, category)
            if conn.execute(
                "SELECT 1 FROM documents WHERE number = ?", (number,)
            ).fetchone():
                raise ValueError(f"Le numéro de commande {number} existe déjà.")
            if not exercice_label:
                raise ExerciceManquant(
                    "Aucun exercice actif pour cette convention : "
                    "ouvrez un exercice depuis l'écran Conventions.",
                    category,
                )
            exercice = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, exercice_label),
            ).fetchone()
            if not exercice:
                raise ExerciceManquant(
                    f"Exercice « {exercice_label} » introuvable pour « {category} ».",
                    category,
                    exercice_label,
                )
            if exercice["status"] != "active":
                raise ExerciceManquant(
                    f"L'exercice « {exercice_label} » est clôturé : "
                    "aucune nouvelle commande ne peut y être enregistrée.",
                    category,
                    exercice_label,
                )
            lines, _ = self._resolve_items(conn, category, items, accept_new_prices)
            total_ht, tva_amount, total_ttc = compute_totals(lines, tva_rate)
            self._assert_within_plafond(conn, category, exercice, total_ht)

            cur = conn.execute(
                "INSERT INTO documents(number, created_at, category, total_ht, tva_rate, "
                "tva_amount, total_ttc, pdf_path, excel_path, exercice_label) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    number, created_at, category, total_ht, tva_rate, tva_amount,
                    total_ttc, pdf_path, excel_path, exercice_label,
                ),
            )
            document_id = int(cur.lastrowid)
            conn.executemany(
                "INSERT INTO document_items(document_id, article_id, code, designation, "
                "unit, unit_price_ht, quantity, total_ht) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                [
                    (
                        document_id,
                        line["article_id"],
                        line["code"],
                        line["designation"],
                        line["unit"],
                        line["unit_price_ht"],
                        line["quantity"],
                        round(line["quantity"] * line["unit_price_ht"], 2),
                    )
                    for line in lines
                ],
            )
        return document_id, total_ht, tva_amount, total_ttc

    def preview_document(
        self,
        category: str,
        items: list[dict],
        exercice_label: str | None = None,
        accept_new_prices: bool = False,
        exclude_document: int | None = None,
    ) -> dict:
        """Valide un document **sans rien écrire** et renvoie les lignes résolues.

        Lève ``ConflitPrix`` / ``ArticlesManquants`` / ``PlafondAtteint`` et les
        erreurs de convention/exercice. Sert à la prévisualisation du
        récapitulatif et à la génération des fichiers avant l'écriture finale.
        """
        with self.connect() as conn:
            category = self._resolve_category_name(conn, category)
            self._validate_category_open(conn, category)
            if exercice_label:
                exercice = conn.execute(
                    "SELECT * FROM exercices WHERE category = ? AND label = ?",
                    (category, exercice_label),
                ).fetchone()
            else:
                exercice = conn.execute(
                    "SELECT * FROM exercices WHERE category = ? AND status = 'active' "
                    "ORDER BY start_date DESC, id DESC LIMIT 1",
                    (category,),
                ).fetchone()
            if not exercice:
                raise ExerciceManquant(
                    (
                        f"L'exercice « {exercice_label} » est introuvable pour "
                        f"« {category} »."
                        if exercice_label
                        else "Aucun exercice actif pour cette convention : "
                        "ouvrez un exercice depuis l'écran Conventions."
                    ),
                    category,
                    exercice_label,
                )
            if exercice["status"] != "active":
                raise ExerciceManquant(
                    f"L'exercice « {exercice['label']} » est clôturé : "
                    "aucune nouvelle commande ne peut y être enregistrée.",
                    category,
                    exercice["label"],
                )
            lines, _ = self._resolve_items(conn, category, items, accept_new_prices)
            total_ht, tva_amount, total_ttc = compute_totals(lines, TVA_RATE)
            self._assert_within_plafond(
                conn, category, exercice, total_ht, exclude_id=exclude_document
            )
            return {
                "category": category,
                "exercice_label": exercice["label"],
                "exercice": {
                    "label": exercice["label"],
                    "start_date": exercice["start_date"],
                    "end_date": exercice["end_date"],
                    "plafond": exercice["plafond"],
                },
                "lines": lines,
                "total_ht": total_ht,
                "tva_amount": tva_amount,
                "total_ttc": total_ttc,
                "tva_rate": TVA_RATE,
            }

    def get_document(self, document_id: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, number, created_at, category, total_ht, tva_rate, tva_amount, "
                "total_ttc, pdf_path, excel_path, exercice_label "
                "FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()

    def delete_document(self, document_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def document_editable(self, document_id: int) -> tuple[bool, str]:
        with self.connect() as conn:
            doc = conn.execute(
                "SELECT category, exercice_label FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                return False, "Commande introuvable."
            category = self._resolve_category_name(conn, doc["category"])
            cat = conn.execute(
                "SELECT status, expiry_date FROM categories WHERE name = ?",
                (category,),
            ).fetchone()
            if not cat:
                return False, f"La convention « {category} » n'existe plus : lecture seule."
            status = self.effective_status(cat["status"], cat["expiry_date"])
            if status != "active":
                word = {"closed": "clôturée", "expiree": "expirée"}.get(status, status)
                return False, f"La convention « {category} » est {word} : lecture seule."
            label = doc["exercice_label"]
            if not label:
                return False, "Cette commande n'est rattachée à aucun exercice : lecture seule."
            exercice = conn.execute(
                "SELECT status FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()
            if not exercice:
                return False, f"L'exercice « {label} » est introuvable : lecture seule."
            if exercice["status"] != "active":
                return False, f"L'exercice « {label} » est clôturé : lecture seule."
        return True, ""

    def update_document(
        self,
        document_id: int,
        items: list[dict],
        tva_rate: float = TVA_RATE,
        pdf_path: str | None = None,
        excel_path: str | None = None,
        accept_new_prices: bool = False,
    ) -> tuple[float, float, float]:
        """Remplace les lignes d'un document (une seule transaction).

        Les lignes conservées gardent leur identifiant et leur prix figé ; les
        lignes ajoutées sont validées contre la liste active. Le plafond est
        recontrôlé hors ce document (égalité incluse).
        """
        if not items:
            raise ValueError("Une commande doit contenir au moins une ligne.")
        editable, reason = self.document_editable(document_id)
        if not editable:
            raise ValueError(reason)

        with self.connect() as conn:
            doc = conn.execute(
                "SELECT category, exercice_label FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                raise ValueError("Commande introuvable.")
            category = self._resolve_category_name(conn, doc["category"])
            label = doc["exercice_label"]
            exercice = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()
            if not exercice:
                raise ValueError(f"Exercice « {label} » introuvable pour « {category} ».")
            if exercice["status"] != "active":
                raise ValueError(
                    f"L'exercice « {label} » est clôturé : cette commande est en lecture seule."
                )

            existing = {
                int(row["id"]): row
                for row in conn.execute(
                    "SELECT id, code, designation, unit, unit_price_ht "
                    "FROM document_items WHERE document_id = ?",
                    (document_id,),
                ).fetchall()
            }
            kept_ids: set[int] = set()
            updates: list[tuple] = []
            insert_rows: list[tuple] = []
            totals: list[dict] = []

            for raw in items:
                quantity = float(raw.get("quantity") or 0)
                if not math.isfinite(quantity) or quantity <= 0:
                    raise ValueError("La quantité doit être un nombre strictement positif.")
                item_id = raw.get("item_id")
                if item_id is not None:
                    item_id = int(item_id)
                    if item_id in kept_ids:
                        raise ValueError("Une même ligne de la commande est listée deux fois.")
                    stored = existing.get(item_id)
                    if stored is None:
                        raise ValueError("Cette ligne n'appartient plus à cette commande.")
                    code, designation, unit = (
                        stored["code"], stored["designation"], stored["unit"],
                    )
                    price = float(stored["unit_price_ht"])
                    article_id = None
                else:
                    resolved_lines, _ = self._resolve_items(
                        conn, category, [raw], accept_new_prices=True
                    )
                    entry = resolved_lines[0]
                    code = entry["code"]
                    designation = entry["designation"]
                    unit = entry["unit"]
                    price = float(entry["unit_price_ht"])
                    article_id = int(entry["article_id"])
                    if raw.get("unit_price_ht") is not None:
                        try:
                            sent = float(raw["unit_price_ht"])
                        except (TypeError, ValueError):
                            sent = None
                        if sent is not None and abs(sent - price) > 0.0001:
                            if not accept_new_prices:
                                raise ConflitPrix(
                                    [
                                        {
                                            "article_id": entry["article_id"],
                                            "code": code,
                                            "designation": designation,
                                            "unit": unit,
                                            "old_price": round(sent, 2),
                                            "new_price": price,
                                        }
                                    ]
                                )
                if article_id is None:
                    # Ligne conservée : on relit l'article pour garder le lien.
                    resolved = conn.execute(
                        "SELECT id FROM articles WHERE category = ? AND code = ? "
                        "AND designation = ? AND unit = ?",
                        (category, code, designation, unit),
                    ).fetchone()
                    article_id = int(resolved["id"]) if resolved else None

                line_total = round(quantity * price, 2)
                totals.append({"quantity": quantity, "unit_price_ht": price})
                if item_id is not None:
                    kept_ids.add(item_id)
                    updates.append(
                        (
                            quantity, line_total, article_id,
                            item_id, document_id,
                        )
                    )
                else:
                    insert_rows.append(
                        (
                            document_id,
                            article_id,
                            code, designation, unit, price, quantity, line_total,
                        )
                    )

            total_ht, tva_amount, total_ttc = compute_totals(totals, tva_rate)
            self._assert_within_plafond(
                conn, category, exercice, total_ht, exclude_id=document_id
            )

            removed = sorted(set(existing) - kept_ids)
            if removed:
                placeholders = ",".join("?" for _ in removed)
                conn.execute(
                    f"DELETE FROM document_items WHERE document_id = ? "
                    f"AND id IN ({placeholders})",
                    (document_id, *removed),
                )
            if updates:
                conn.executemany(
                    "UPDATE document_items SET quantity = ?, total_ht = ?, article_id = ? "
                    "WHERE id = ? AND document_id = ?",
                    updates,
                )
            if insert_rows:
                conn.executemany(
                    "INSERT INTO document_items(document_id, article_id, code, designation, "
                    "unit, unit_price_ht, quantity, total_ht) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    insert_rows,
                )
            conn.execute(
                "UPDATE documents SET total_ht = ?, tva_rate = ?, tva_amount = ?, "
                "total_ttc = ?, pdf_path = COALESCE(?, pdf_path), "
                "excel_path = COALESCE(?, excel_path) WHERE id = ?",
                (total_ht, tva_rate, tva_amount, total_ttc, pdf_path, excel_path, document_id),
            )
        return total_ht, tva_amount, total_ttc

    def list_documents(
        self, text: str = "", category: str | None = None, exercice: str | None = None
    ):
        conditions: list[str] = []
        params: list[object] = []
        text = (text or "").strip()
        if text:
            like = f"%{text}%"
            conditions.append("(number LIKE ? OR category LIKE ? OR created_at LIKE ?)")
            params.extend((like, like, like))
        if category:
            conditions.append("category = ? COLLATE NOCASE")
            params.append(category)
        if exercice:
            conditions.append("exercice_label = ?")
            params.append(exercice)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, number, created_at, category, total_ht, tva_rate, "
                "tva_amount, total_ttc, pdf_path, excel_path, exercice_label "
                f"FROM documents{where} ORDER BY id DESC",
                params,
            ).fetchall()

    def document_items(self, document_id: int):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, article_id, code, designation, unit, unit_price_ht, "
                "quantity, total_ht FROM document_items WHERE document_id = ? ORDER BY id",
                (document_id,),
            ).fetchall()

    # --------------------------------------------------------------- rapports

    def exercice_documents(self, exercice_label: str, category: str | None = None):
        with self.connect() as conn:
            if category:
                return conn.execute(
                    "SELECT id, number, created_at, category, total_ht, tva_rate, "
                    "tva_amount, total_ttc, exercice_label FROM documents "
                    "WHERE exercice_label = ? AND category = ? "
                    "ORDER BY category COLLATE NOCASE, id",
                    (exercice_label, category),
                ).fetchall()
            return conn.execute(
                "SELECT id, number, created_at, category, total_ht, tva_rate, "
                "tva_amount, total_ttc, exercice_label FROM documents "
                "WHERE exercice_label = ? ORDER BY category COLLATE NOCASE, id",
                (exercice_label,),
            ).fetchall()

    def exercice_consumption_report(self, exercice_label: str) -> list[dict]:
        """Rapport de consommation par convention pour un libellé d'exercice."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT category, plafond, status, consumed_at_close, remaining_at_close "
                "FROM exercices WHERE label = ?",
                (exercice_label,),
            ).fetchall()
            categories_meta = {
                row["name"]: row for row in conn.execute("SELECT name FROM categories")
            }
            consumptions: dict[str, float] = {}
            counts: dict[str, int] = {}
            for row in conn.execute(
                "SELECT category, SUM(total_ht) AS total, COUNT(*) AS docs "
                "FROM documents WHERE exercice_label = ? GROUP BY category",
                (exercice_label,),
            ):
                consumptions[row["category"]] = round(float(row["total"] or 0.0), 2)
                counts[row["category"]] = int(row["docs"])

        names: set[str] = {row["category"] for row in rows}
        names.update(consumptions)
        names.update(categories_meta)

        out: list[dict] = []
        for name in sorted(names, key=str.casefold):
            exercice_row = next((r for r in rows if r["category"] == name), None)
            plafond = (
                None
                if exercice_row is None or exercice_row["plafond"] is None
                else float(exercice_row["plafond"])
            )
            consumed = consumptions.get(name, 0.0)
            doc_count = counts.get(name, 0)
            if plafond is None:
                summary = {
                    "category": name, "label": exercice_label, "plafond": None,
                    "consumed": consumed, "remaining": None, "rate": None,
                }
            else:
                summary = {
                    "category": name, "label": exercice_label, "plafond": plafond,
                    "consumed": consumed, "remaining": round(plafond - consumed, 2),
                    "rate": (consumed / plafond) if plafond else None,
                }
            summary["doc_count"] = doc_count
            out.append(summary)
        return out

    def civil_years(self) -> list[str]:
        """Années civiles des documents (plus l'année en cours)."""
        with self.connect() as conn:
            rows = conn.execute(
                "SELECT DISTINCT substr(created_at, 1, 4) AS year FROM documents "
                "ORDER BY year DESC"
            ).fetchall()
        years = [r["year"] for r in rows if r["year"] and str(r["year"]).isdigit()]
        current = date.today().strftime("%Y")
        if current not in years:
            years.insert(0, current)
        return years

    def civil_year_documents(self, year: str):
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, number, created_at, category, total_ht, tva_rate, "
                "tva_amount, total_ttc, exercice_label FROM documents "
                "WHERE substr(created_at, 1, 4) = ? "
                "ORDER BY category COLLATE NOCASE, id",
                (year,),
            ).fetchall()

    def civil_year_report(self, year: str) -> list[dict]:
        """Consommation par convention pour une année civile.

        Le plafond de référence est celui de l'exercice couvrant le 1er
        janvier de l'année (simple repère, le contrôle reste annuel).
        """
        with self.connect() as conn:
            consumptions: dict[str, float] = {}
            counts: dict[str, int] = {}
            for row in conn.execute(
                "SELECT category, SUM(total_ht) AS total, COUNT(*) AS docs "
                "FROM documents WHERE substr(created_at, 1, 4) = ? GROUP BY category",
                (year,),
            ):
                consumptions[row["category"]] = round(float(row["total"] or 0.0), 2)
                counts[row["category"]] = int(row["docs"])
            jan1 = f"{year}-01-01"
            refs: dict[str, dict] = {}
            for row in conn.execute(
                "SELECT category, label, plafond FROM exercices "
                "WHERE start_date <= ? AND end_date >= ?",
                (jan1, jan1),
            ):
                refs[row["category"]] = {
                    "label": row["label"], "plafond": row["plafond"]
                }
            cats = {r[0] for r in conn.execute("SELECT name FROM categories")}
        out: list[dict] = []
        for name in sorted(set(consumptions) | cats, key=str.casefold):
            consumed = consumptions.get(name, 0.0)
            ref = refs.get(name)
            plafond = (
                None
                if ref is None or ref["plafond"] is None
                else float(ref["plafond"])
            )
            out.append(
                {
                    "category": name,
                    "label": year,
                    "plafond": plafond,
                    "consumed": consumed,
                    "remaining": (
                        None if plafond is None else round(plafond - consumed, 2)
                    ),
                    "rate": None if not plafond else consumed / plafond,
                    "doc_count": counts.get(name, 0),
                    "reference": ref["label"] if ref else None,
                }
            )
        return out

    # ------------------------------------------------------- métadonnées / divers

    def get_meta(self, key: str, default: str | None = None) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT value FROM app_meta WHERE key = ?", (key,)
            ).fetchone()
        return row["value"] if row else default

    def set_meta(self, key: str, value: str) -> None:
        with self.connect() as conn:
            conn.execute(
                "INSERT INTO app_meta(key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )

    @staticmethod
    def _resolve_category_name(conn: sqlite3.Connection, name: str) -> str:
        name = (name or "").strip()
        if not name:
            raise ValueError("Le nom de la liste ne peut pas être vide.")
        row = conn.execute(
            "SELECT name FROM categories WHERE name = ? COLLATE NOCASE", (name,)
        ).fetchone()
        return row[0] if row else name

    def resolve_category_name(self, name: str) -> str | None:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT name FROM categories WHERE name = ? COLLATE NOCASE",
                ((name or "").strip(),),
            ).fetchone()
        return row[0] if row else None
