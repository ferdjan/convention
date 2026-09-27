from __future__ import annotations

import math
import re
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

class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.init_schema()

    @contextmanager
    def connect(self):
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    # ------------------------------------------------------------ schéma/migration

    def init_schema(self) -> None:
        is_new_database = not self.path.exists() or self.path.stat().st_size == 0
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.execute("BEGIN IMMEDIATE")
            self._execute_script(conn, SCHEMA)
            self._migrate(conn)
            self._repair_orphan_document_items(conn)
            violations = conn.execute("PRAGMA foreign_key_check").fetchall()
            if violations:
                raise sqlite3.IntegrityError(self._format_fk_violations(violations))
            conn.execute("COMMIT")
        except Exception:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            raise
        finally:
            conn.close()
        with self.connect() as conn:
            category_count = int(
                conn.execute("SELECT COUNT(*) FROM categories").fetchone()[0]
            )
            marker = conn.execute(
                "SELECT value FROM app_meta WHERE key = 'defaults_seeded'"
            ).fetchone()
        include_defaults = is_new_database or (category_count == 0 and not marker)
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
    def _repair_orphan_document_items(conn: sqlite3.Connection) -> None:
        conn.execute(
            "UPDATE document_items SET article_id = NULL "
            "WHERE article_id IS NOT NULL "
            "AND article_id NOT IN (SELECT id FROM articles)"
        )

    @staticmethod
    def _format_fk_violations(violations: Iterable[sqlite3.Row]) -> str:
        details = []
        for row in violations:
            values = list(row)
            while len(values) < 4:
                values.append(None)
            table, rowid, parent, fkid = values[:4]
            details.append(
                f"table {table}, ligne {rowid}, table parente {parent} (clé {fkid})"
            )
        shown = details[:10]
        if len(details) > len(shown):
            shown.append(f"… et {len(details) - len(shown)} autre(s)")
        return (
            "Échec du contrôle des clés étrangères : "
            + "; ".join(shown)
            + "."
        )

    def _table_exists(self, conn: sqlite3.Connection, name: str) -> bool:
        return (
            conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
                (name,),
            ).fetchone()
            is not None
        )

    def _migrate(self, conn: sqlite3.Connection) -> None:
        # --- étape 1 : colonnes historiques des tables conservées ----------------
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
        ):
            if not self._column_exists(conn, "documents", column):
                conn.execute(f"ALTER TABLE documents ADD COLUMN {column} {definition}")

        # --- étape 2 : normalisation anciennes bases (avant v2) ------------------
        self._merge_case_duplicate_categories(conn)

        # Le trigger de verrouillage des prix, les tables audit_log / price_history /
        # budgets / budget_archives sont supprimés (refonte v2) ; s'ils existent
        # encore, ils sont retirés ici, puis l'exercice est introduit.
        self._migrate_to_exercices(conn)

        # Normalisation des montants TVA sur les documents anciens.
        conn.execute("UPDATE documents SET tva_rate = ? WHERE tva_rate IS NULL", (TVA_RATE,))
        conn.execute(
            "UPDATE documents SET tva_amount = ROUND(total_ht * tva_rate, 2) "
            "WHERE tva_amount IS NULL"
        )
        conn.execute(
            "UPDATE documents SET total_ttc = ROUND(total_ht + tva_amount, 2) "
            "WHERE total_ttc IS NULL"
        )
        conn.execute("UPDATE categories SET status = 'active' WHERE status IS NULL OR status = ''")

    # ------------------------------------------------ migration vers exercices

    def _migrate_to_exercices(self, conn: sqlite3.Connection) -> None:
        """Introduit la table ``exercices`` et démonte l'ancien modèle budget_*.

        L'opération est idempotente : sur une base v2 elle ne fait rien.
        """
        has_exercices = self._table_exists(conn, "exercices")
        has_old_budgets = self._table_exists(conn, "budgets") or self._table_exists(
            conn, "budget_archives"
        )
        has_old_documents = self._column_exists(conn, "documents", "budget_year")

        if has_exercices and not has_old_budgets and not has_old_documents:
            # Base déjà en v2 : s'assurer simplement que l'index existe.
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_exercice "
                "ON documents(category, exercice_label)"
            )
            return

        # Recréer la table exercices si elle venait à manquer (cas d'une base
        # créée avec le schéma v2 mais jamais migrée).
        self._execute_script(
            conn,
            """
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
            """,
        )

        label_of_doc: dict[int, str] = {}

        def ensure_exercice(category: str, label: str) -> None:
            if not label:
                return
            row = conn.execute(
                "SELECT id, status FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()
            if row:
                return
            # L'année de référence sert aux dates provisoires : premier nombre
            # à 4 chiffres du libellé, sinon année courante (modifiable ensuite).
            match = re.search(r"\d{4}", label)
            year = int(match.group(0)) if match else datetime.now().year
            conn.execute(
                """
                INSERT INTO exercices(category, label, start_date, end_date, plafond, status)
                VALUES (?, ?, ?, ?, NULL, 'active')
                """,
                (category, label, f"{year:04d}-01-01", f"{year:04d}-12-31"),
            )

        # 1) budgets actifs -> exercices actifs (dates provisoires année civile)
        if self._table_exists(conn, "budgets"):
            for row in conn.execute(
                "SELECT category, year, amount FROM budgets"
            ).fetchall():
                label = str(int(row["year"]))
                start, end = f"{int(row['year']):04d}-01-01", f"{int(row['year']):04d}-12-31"
                existing = conn.execute(
                    "SELECT id FROM exercices WHERE category = ? AND label = ?",
                    (row["category"], label),
                ).fetchone()
                if existing:
                    conn.execute(
                        "UPDATE exercices SET plafond = ?, status = 'active' WHERE id = ?",
                        (float(row["amount"]), existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO exercices(category, label, start_date, end_date, plafond, status)
                        VALUES (?, ?, ?, ?, ?, 'active')
                        """,
                        (row["category"], label, start, end, float(row["amount"])),
                    )

        # 2) archives -> exercices clos (l'archive garde la priorité sur budget)
        if self._table_exists(conn, "budget_archives"):
            for row in conn.execute(
                "SELECT category, year, plafond, consumed, remaining, closed_at "
                "FROM budget_archives"
            ).fetchall():
                label = str(int(row["year"]))
                start, end = f"{int(row['year']):04d}-01-01", f"{int(row['year']):04d}-12-31"
                existing = conn.execute(
                    "SELECT id FROM exercices WHERE category = ? AND label = ?",
                    (row["category"], label),
                ).fetchone()
                plafond = None if row["plafond"] is None else float(row["plafond"])
                consumed = round(float(row["consumed"] or 0.0), 2)
                remaining = None if row["remaining"] is None else round(float(row["remaining"]), 2)
                if existing:
                    conn.execute(
                        """
                        UPDATE exercices SET plafond = ?, status = 'closed',
                            consumed_at_close = ?, remaining_at_close = ?, closed_at = ?
                        WHERE id = ?
                        """,
                        (plafond, consumed, remaining, row["closed_at"], existing["id"]),
                    )
                else:
                    conn.execute(
                        """
                        INSERT INTO exercices(
                            category, label, start_date, end_date, plafond, status,
                            consumed_at_close, remaining_at_close, closed_at
                        )
                        VALUES (?, ?, ?, ?, ?, 'closed', ?, ?, ?)
                        """,
                        (row["category"], label, start, end, plafond, consumed, remaining, row["closed_at"]),
                    )

        # 3) documents : budget_year -> exercice_label (avant rebuild de la table)
        if has_old_documents:
            for row in conn.execute("SELECT id, budget_year, created_at FROM documents").fetchall():
                label = None
                if row["budget_year"] is not None:
                    label = str(int(row["budget_year"]))
                else:
                    try:
                        label = str(datetime.fromisoformat(row["created_at"]).year)
                    except (TypeError, ValueError):
                        label = str(datetime.now().year)
                label_of_doc[int(row["id"])] = label

        # 4) rebuild de documents sans budget_year / overrun_justification
        doc_cols = [r[1] for r in conn.execute("PRAGMA table_info(documents)")]
        if (
            "budget_year" in doc_cols
            or "overrun_justification" in doc_cols
            or "exercice_label" not in doc_cols
        ):
            # Le SELECT doit s'adapter aux colonnes réellement présentes :
            # - base v1 : budget_year (parfois NULL) et pas d'exercice_label ;
            # - base v2 partielle : exercice_label déjà là.
            label_expr = "exercice_label"
            if "exercice_label" not in doc_cols:
                label_expr = (
                    "CAST(budget_year AS TEXT)"
                    if "budget_year" in doc_cols
                    else "NULL"
                )
            elif "budget_year" in doc_cols:
                label_expr = "COALESCE(CAST(budget_year AS TEXT), exercice_label)"
            self._execute_script(
                conn,
                """
                CREATE TABLE documents_new (
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
                """,
            )
            conn.execute(
                f"""
                INSERT INTO documents_new(
                    id, number, created_at, category, total_ht, tva_rate,
                    tva_amount, total_ttc, pdf_path, excel_path, exercice_label
                )
                SELECT id, number, created_at, category, total_ht, tva_rate,
                       tva_amount, total_ttc, pdf_path, excel_path,
                       {label_expr}
                FROM documents
                """,
            )
            conn.execute("DROP TABLE documents")
            conn.execute("ALTER TABLE documents_new RENAME TO documents")
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_documents_exercice "
                "ON documents(category, exercice_label)"
            )
            # Les documents sans label héritent du label calculé plus haut
            # (budget_year ou année de created_at).
            for doc_id, label in label_of_doc.items():
                conn.execute(
                    "UPDATE documents SET exercice_label = ? WHERE id = ? "
                    "AND (exercice_label IS NULL OR exercice_label = '')",
                    (label, doc_id),
                )

        # 5) chaque document doit pointer sur un exercice existant
        for row in conn.execute(
            "SELECT DISTINCT category, exercice_label FROM documents "
            "WHERE exercice_label IS NOT NULL AND exercice_label <> ''"
        ).fetchall():
            ensure_exercice(row["category"], row["exercice_label"])

        # 6) chaque convention doit avoir au moins un exercice (hors base vide)
        for row in conn.execute("SELECT name FROM categories").fetchall():
            if not conn.execute(
                "SELECT 1 FROM exercices WHERE category = ? LIMIT 1", (row["name"],)
            ).fetchone():
                current_year = datetime.now().year
                conn.execute(
                    """
                    INSERT INTO exercices(category, label, start_date, end_date, plafond, status)
                    VALUES (?, ?, ?, ?, NULL, 'active')
                    """,
                    (row["name"], str(current_year), f"{current_year}-01-01", f"{current_year}-12-31"),
                )

        # 7) un seul exercice actif par convention : les plus anciens sont clos
        for row in conn.execute(
            "SELECT DISTINCT category FROM exercices WHERE status = 'active'"
        ).fetchall():
            active = conn.execute(
                "SELECT id FROM exercices WHERE category = ? AND status = 'active' ORDER BY id",
                (row["category"],),
            ).fetchall()
            for stale in active[:-1]:
                conn.execute(
                    "UPDATE exercices SET status = 'closed', closed_at = COALESCE(closed_at, ?) "
                    "WHERE id = ?",
                    (datetime.now().isoformat(timespec="seconds"), stale["id"]),
                )

        # 8) suppression des tables et trigger obsolètes
        conn.execute("DROP TRIGGER IF EXISTS trg_articles_price_locked")
        if self._table_exists(conn, "audit_log"):
            conn.execute("DROP TABLE audit_log")
        if self._table_exists(conn, "price_history"):
            conn.execute("DROP TABLE price_history")
        if self._table_exists(conn, "budgets"):
            conn.execute("DROP TABLE budgets")
        if self._table_exists(conn, "budget_archives"):
            conn.execute("DROP TABLE budget_archives")

    def _merge_case_duplicate_categories(self, conn: sqlite3.Connection) -> None:
        rows = conn.execute(
            "SELECT id, name, sheet_name, prefix FROM categories ORDER BY id"
        ).fetchall()
        groups: dict[str, list[sqlite3.Row]] = {}
        for row in rows:
            groups.setdefault((row["name"] or "").strip().casefold(), []).append(row)

        default_names = {name.casefold(): name for name in DEFAULT_CATEGORIES}
        for group in groups.values():
            if len(group) < 2:
                continue
            canonical = next(
                (
                    row
                    for row in group
                    if (row["name"] or "").strip().casefold() in default_names
                ),
                group[0],
            )
            canonical_name = canonical["name"]
            if not canonical["prefix"]:
                for row in group[1:]:
                    if row["prefix"]:
                        conn.execute(
                            "UPDATE categories SET prefix = ? WHERE id = ?",
                            (row["prefix"], canonical["id"]),
                        )
                        break
            for duplicate in group:
                if duplicate["id"] == canonical["id"]:
                    continue
                duplicate_name = duplicate["name"]
                if self._table_exists(conn, "budgets"):
                    conn.execute(
                        "UPDATE OR IGNORE budgets SET category = ? WHERE category = ?",
                        (canonical_name, duplicate_name),
                    )
                    conn.execute(
                        "DELETE FROM budgets WHERE category = ?", (duplicate_name,)
                    )
                if self._table_exists(conn, "budget_archives"):
                    conn.execute(
                        "UPDATE OR IGNORE budget_archives SET category = ? WHERE category = ?",
                        (canonical_name, duplicate_name),
                    )
                    conn.execute(
                        "DELETE FROM budget_archives WHERE category = ?", (duplicate_name,)
                    )
                if self._table_exists(conn, "price_history"):
                    conn.execute(
                        "UPDATE price_history SET category = ? WHERE category = ?",
                        (canonical_name, duplicate_name),
                    )
                conn.execute(
                    "UPDATE documents SET category = ? WHERE category = ?",
                    (canonical_name, duplicate_name),
                )
                duplicate_articles = conn.execute(
                    "SELECT id, code, designation, unit FROM articles WHERE category = ?",
                    (duplicate_name,),
                ).fetchall()
                for article in duplicate_articles:
                    target = conn.execute(
                        """
                        SELECT id FROM articles
                        WHERE category = ? AND code = ? AND designation = ? AND unit = ?
                        """,
                        (
                            canonical_name,
                            article["code"],
                            article["designation"],
                            article["unit"],
                        ),
                    ).fetchone()
                    if target:
                        target_id = int(target["id"])
                        duplicate_id = int(article["id"])
                        if duplicate_id > target_id:
                            conn.execute(
                                "UPDATE document_items SET article_id = ? WHERE article_id = ?",
                                (duplicate_id, target_id),
                            )
                            conn.execute("DELETE FROM articles WHERE id = ?", (target_id,))
                            conn.execute(
                                "UPDATE articles SET category = ? WHERE id = ?",
                                (canonical_name, duplicate_id),
                            )
                        else:
                            conn.execute(
                                "UPDATE document_items SET article_id = ? WHERE article_id = ?",
                                (target_id, duplicate_id),
                            )
                            conn.execute(
                                "DELETE FROM articles WHERE id = ?", (duplicate_id,)
                            )
                    else:
                        conn.execute(
                            "UPDATE articles SET category = ? WHERE id = ?",
                            (canonical_name, article["id"]),
                        )
                if self._table_exists(conn, "exercices"):
                    conn.execute(
                        "UPDATE OR IGNORE exercices SET category = ? WHERE category = ?",
                        (canonical_name, duplicate_name),
                    )
                conn.execute("DELETE FROM categories WHERE id = ?", (duplicate["id"],))

        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_categories_name_nocase "
            "ON categories(name COLLATE NOCASE)"
        )

    @staticmethod
    def _column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
        return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))

    @staticmethod
    def _make_prefix(name: str) -> str:
        letters = "".join(ch for ch in name.upper() if ch.isalnum())
        return letters[:3] or "DOC"

    @staticmethod
    def _unique_prefix(conn: sqlite3.Connection, base: str, exclude_name: str | None = None) -> str:
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
                for row in conn.execute("SELECT DISTINCT category FROM articles ORDER BY category")
            )
            existing = {row["name"].casefold() for row in conn.execute("SELECT name FROM categories")}
            for name in names:
                if not name or name.casefold() in existing:
                    continue
                prefix = DEFAULT_PREFIXES.get(name) or self._make_prefix(name)
                conn.execute(
                    "INSERT OR IGNORE INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
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

    # ------------------------------------------------------------ conventions

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
        """Statut effectif d'une convention : ``active``, ``closed`` ou ``expiree``.

        Une convention est considérée comme expirée lorsque sa date d'échéance
        (``expiry_date``) est dépassée. Une convention clôturée manuellement reste
        clôturée, même si son échéance est dépassée.
        """
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

    def category_status(self, name: str) -> tuple[str, str | None]:
        with self.connect() as conn:
            row = conn.execute(
                "SELECT status, expiry_date FROM categories WHERE name = ?", (name,)
            ).fetchone()
        if not row:
            return "active", None
        return self.effective_status(row["status"], row["expiry_date"]), row["expiry_date"]

    def category_raw(self, name: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT status, expiry_date FROM categories WHERE name = ?", (name,)
            ).fetchone()

    def set_category_status(
        self,
        name: str,
        status: str,
        expiry_date: str | None = None,
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
            row = conn.execute("SELECT prefix FROM categories WHERE name = ?", (name,)).fetchone()
        return (row[0] if row and row[0] else self._make_prefix(name)) or "DOC"

    # ------------------------------------------------------------- exercices

    def list_exercices(self, category: str) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, category, label, start_date, end_date, plafond, status, "
                "consumed_at_close, remaining_at_close, closed_at "
                "FROM exercices WHERE category = ? "
                "ORDER BY start_date DESC, id DESC",
                (category,),
            ).fetchall()

    def list_all_exercices(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, category, label, start_date, end_date, plafond, status, "
                "consumed_at_close, remaining_at_close, closed_at "
                "FROM exercices "
                "ORDER BY category COLLATE NOCASE, start_date DESC, id DESC"
            ).fetchall()

    def get_exercice(self, category: str, label: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, label),
            ).fetchone()

    def get_active_exercice(self, category: str) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND status = 'active' "
                "ORDER BY start_date DESC, id DESC LIMIT 1",
                (category,),
            ).fetchone()

    def exercice_exists(self, category: str, label: str) -> bool:
        return self.get_exercice(category, label) is not None

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
                """
                INSERT INTO exercices(category, label, start_date, end_date, plafond, status)
                VALUES (?, ?, ?, ?, ?, 'active')
                """,
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
    ) -> None:
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
            conn.execute(
                "UPDATE exercices SET start_date = ?, end_date = ?, plafond = ? "
                "WHERE id = ?",
                (new_start, new_end, plafond, row["id"]),
            )

    def _close_active_exercice(self, conn: sqlite3.Connection, category: str) -> None:
        row = conn.execute(
            "SELECT * FROM exercices WHERE category = ? AND status = 'active' "
            "ORDER BY start_date DESC, id DESC LIMIT 1",
            (category,),
        ).fetchone()
        if not row:
            return
        consumed = round(
            float(
                conn.execute(
                    "SELECT COALESCE(SUM(total_ht), 0) FROM documents "
                    "WHERE category = ? AND exercice_label = ?",
                    (category, row["label"]),
                ).fetchone()[0]
                or 0.0
            ),
            2,
        )
        plafond = None if row["plafond"] is None else float(row["plafond"])
        remaining = None if plafond is None else round(plafond - consumed, 2)
        conn.execute(
            """
            UPDATE exercices
            SET status = 'closed', consumed_at_close = ?, remaining_at_close = ?,
                closed_at = ?
            WHERE id = ?
            """,
            (
                consumed,
                remaining,
                datetime.now().isoformat(timespec="seconds"),
                row["id"],
            ),
        )

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
            row = conn.execute(
                "SELECT COALESCE(SUM(total_ht), 0) FROM documents "
                "WHERE category = ? AND exercice_label = ?",
                (category, label),
            ).fetchone()
        return round(float(row[0] or 0.0), 2)

    def exercice_summary(self, category: str, label: str) -> dict:
        """Synthèse budgétaire d'un exercice avec état d'alerte.

        États possibles : ``none`` (pas de plafond), ``ok``, ``warn`` (>= 80 %),
        ``critical`` (>= 90 %), ``over`` (>= 100 %).
        """
        row = self.get_exercice(category, label)
        if not row:
            return {
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
        consumed = self.exercice_consumed(category, label)
        plafond = None if row["plafond"] is None else float(row["plafond"])
        if plafond is None:
            return {
                "category": category,
                "label": label,
                "plafond": None,
                "consumed": consumed,
                "remaining": None,
                "rate": None,
                "state": "none",
                "start_date": row["start_date"],
                "end_date": row["end_date"],
                "status": row["status"],
            }
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
            "category": category,
            "label": label,
            "plafond": plafond,
            "consumed": consumed,
            "remaining": remaining,
            "rate": rate,
            "state": state,
            "start_date": row["start_date"],
            "end_date": row["end_date"],
            "status": row["status"],
        }

    def exercice_would_exceed(self, category: str, label: str, amount: float) -> bool:
        """Blocage ferme : vrai si ``consommé + montant`` atteint le plafond.

        L'égalité exacte bloque aussi (décision produit : ``>=`` plafond).
        Plafond NULL (illimité) : jamais de blocage.
        """
        row = self.get_exercice(category, label)
        if not row or row["plafond"] is None:
            return False
        consumed = self.exercice_consumed(category, label)
        return round(consumed + float(amount), 2) >= round(float(row["plafond"]), 2)

    # ------------------------------------------------------------- articles

    def article_count(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def _ensure_category_row(self, conn: sqlite3.Connection, name: str) -> str:
        name = self._resolve_category_name(conn, name)
        if conn.execute("SELECT 1 FROM categories WHERE name = ?", (name,)).fetchone():
            return name
        prefix = DEFAULT_PREFIXES.get(name) or self._make_prefix(name)
        conn.execute(
            "INSERT INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
            (name, name, self._unique_prefix(conn, prefix)),
        )
        return name

    @staticmethod
    def _prepare_rows(rows: Iterable[tuple[str, str, str, str, float]]) -> list[tuple[str, str, str, str, float]]:
        prepared: list[tuple[str, str, str, str, float]] = []
        seen: dict[tuple[str, str, str, str], float] = {}
        for category, code, designation, unit, price in rows:
            values = (
                str(category or "").strip(),
                str(code or "").strip(),
                str(designation or "").strip(),
                str(unit or "").strip(),
            )
            if not all(values):
                raise ValueError(
                    "Chaque ligne importée doit renseigner la liste, le code, la désignation et l'unité."
                )
            try:
                price = float(price)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Prix invalide pour {values[1] :s}.") from exc
            if not math.isfinite(price) or price < 0:
                raise ValueError(f"Prix invalide pour {values[1] :s}.")
            key = values
            if key in seen:
                if abs(seen[key] - price) > 0.0001:
                    raise ValueError(
                        f"Confusion de prix pour {values[1] :s} / {values[2] :s} / {values[3] :s}."
                    )
                continue
            seen[key] = price
            prepared.append((*values, price))
        return prepared

    def replace_articles(self, rows: Iterable[tuple[str, str, str, str, float]]) -> int:
        prepared = self._prepare_rows(rows)
        with self.connect() as conn:
            conn.execute("DELETE FROM articles")
            conn.executemany(
                """
                INSERT INTO articles(category, code, designation, unit, unit_price_ht)
                VALUES (?, ?, ?, ?, ?)
                """,
                [
                    (self._ensure_category_row(conn, category), code, designation, unit, price)
                    for category, code, designation, unit, price in prepared
                ],
            )
        return len(prepared)

    @staticmethod
    def _existing_article_map(conn: sqlite3.Connection, category: str) -> dict:
        return {
            (r["code"], r["designation"], r["unit"]): {
                "id": int(r["id"]),
                "unit_price_ht": float(r["unit_price_ht"]),
            }
            for r in conn.execute(
                "SELECT id, code, designation, unit, unit_price_ht FROM articles WHERE category = ?",
                (category,),
            )
        }

    def article_map(self, category: str) -> dict:
        with self.connect() as conn:
            return self._existing_article_map(conn, category)

    def replace_articles_by_category(
        self,
        rows: Iterable[tuple[str, str, str, str, float]],
        source: str = "Import Excel",
    ) -> dict:
        """Remplace les articles des listes concernées (prix figés par import).

        Les prix d'une convention sont figés pendant son exercice : l'import
        remplace la liste. Aucun historique de révision n'est conservé.
        """
        prepared = self._prepare_rows(rows)
        with self.connect() as conn:
            canonical: dict[str, str] = {}
            for category in dict.fromkeys(row[0] for row in prepared):
                canonical[category] = self._ensure_category_row(conn, category)
            grouped_rows: dict[str, list[tuple[str, str, str, str, float]]] = {}
            for row_category, code, designation, unit, price in prepared:
                name = canonical[row_category]
                grouped_rows.setdefault(name, []).append(
                    (name, code, designation, unit, price)
                )
            for name, category_rows in list(grouped_rows.items()):
                unique_rows: list[tuple[str, str, str, str, float]] = []
                seen_rows: dict[tuple[str, str, str, str], float] = {}
                for row in category_rows:
                    key = (row[0], row[1], row[2], row[3])
                    if key in seen_rows:
                        if abs(seen_rows[key] - row[4]) > 0.0001:
                            raise ValueError(
                                f"Confusion de prix pour {row[1] :s} / {row[2] :s} / {row[3] :s}."
                            )
                        continue
                    seen_rows[key] = row[4]
                    unique_rows.append(row)
                grouped_rows[name] = unique_rows
                conn.execute("DELETE FROM articles WHERE category = ?", (name,))
                conn.executemany(
                    """
                    INSERT INTO articles(category, code, designation, unit, unit_price_ht)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    unique_rows,
                )
        return {"imported": sum(len(rows) for rows in grouped_rows.values())}

    def search_articles(self, category: str, text: str = "") -> list[sqlite3.Row]:
        text = text.strip()
        with self.connect() as conn:
            if text:
                like = f"%{text}%"
                return conn.execute(
                    """
                    SELECT id, code, designation, unit, unit_price_ht
                    FROM articles
                    WHERE category = ?
                      AND (code LIKE ? OR designation LIKE ? OR unit LIKE ?)
                    ORDER BY CAST(code AS INTEGER), designation
                    """,
                    (category, like, like, like),
                ).fetchall()
            return conn.execute(
                """
                SELECT id, code, designation, unit, unit_price_ht
                FROM articles
                WHERE category = ?
                ORDER BY CAST(code AS INTEGER), designation
                """,
                (category,),
            ).fetchall()

    # ------------------------------------------------------------- documents

    def next_document_number(self, category: str | None = None, exercice_label: str | None = None) -> str:
        """Numéro au format ``PREFIX-LABEL-NNNN`` (ex. ``INF-2026-2027-0001``).

        La séquence est propre au couple (convention, exercice). Sans exercice,
        l'année civile est utilisée comme label (compatibilité).
        """
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
            return conn.execute(
                "SELECT 1 FROM documents WHERE number = ?", (number,)
            ).fetchone() is not None

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
    ) -> tuple[int, float, float, float]:
        if not items:
            raise ValueError("Un document doit contenir au moins une ligne.")
        total_ht, tva_amount, total_ttc = compute_totals(items, tva_rate)

        with self.connect() as conn:
            category = self._resolve_category_name(conn, category)
            if not conn.execute("SELECT 1 FROM categories WHERE name = ?", (category,)).fetchone():
                raise ValueError(f"Convention inconnue : {category}")
            if conn.execute("SELECT 1 FROM documents WHERE number = ?", (number,)).fetchone():
                raise ValueError(f"Le numéro de document {number} existe déjà.")

            # Convention close : aucun nouveau document.
            row = conn.execute(
                "SELECT status FROM categories WHERE name = ?", (category,)
            ).fetchone()
            if row and (row["status"] or "active") != "active":
                raise ValueError(
                    f"La convention « {category} » est clôturée : "
                    "aucun nouveau document ne peut y être enregistré."
                )

            # Exercice : obligatoire, actif, et contrôle du plafond.
            if not exercice_label:
                raise ValueError("Aucun exercice actif pour cette convention.")
            exercice = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, exercice_label),
            ).fetchone()
            if not exercice:
                raise ValueError(
                    f"Exercice « {exercice_label} » introuvable pour « {category} »."
                )
            if exercice["status"] != "active":
                raise ValueError(
                    f"L'exercice « {exercice_label} » est clôturé : "
                    "aucun nouveau document ne peut y être enregistré."
                )
            if exercice["plafond"] is not None:
                consumed = round(
                    float(
                        conn.execute(
                            "SELECT COALESCE(SUM(total_ht), 0) FROM documents "
                            "WHERE category = ? AND exercice_label = ?",
                            (category, exercice_label),
                        ).fetchone()[0]
                        or 0.0
                    ),
                    2,
                )
                projected = round(consumed + total_ht, 2)
                if projected >= round(float(exercice["plafond"]), 2):
                    raise ValueError(
                        "PLAFOND ATTEINT : l'enregistrement est bloqué.\n"
                        f"Consommé : {consumed:.2f} DA + ce document {total_ht:.2f} DA = "
                        f"{projected:.2f} DA pour un plafond de "
                        f"{float(exercice['plafond']):.2f} DA.\n"
                        "Aucun dépassement n'est autorisé sur cette convention."
                    )

            cur = conn.execute(
                """
                INSERT INTO documents(
                    number, created_at, category, total_ht, tva_rate, tva_amount,
                    total_ttc, pdf_path, excel_path, exercice_label
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    number, created_at, category, total_ht, tva_rate, tva_amount,
                    total_ttc, pdf_path, excel_path, exercice_label,
                ),
            )
            document_id = cur.lastrowid
            item_rows: list[tuple] = []
            for item in items:
                if item.get("category") not in (None, category):
                    raise ValueError(
                        f"La ligne {item['code']} n'appartient pas à la liste {category}."
                    )
                article = conn.execute(
                    """
                    SELECT id, unit_price_ht FROM articles
                    WHERE category = ? AND code = ? AND designation = ? AND unit = ?
                    """,
                    (category, item["code"], item["designation"], item["unit"]),
                ).fetchone()
                if article is None:
                    raise ValueError(
                        f"L'article {item['code']} n'existe plus dans la liste {category}."
                    )
                if abs(float(article["unit_price_ht"]) - float(item["unit_price_ht"])) > 0.0001:
                    raise ValueError(
                        f"Le prix de {item['code']} a changé. Importez la liste à jour."
                    )
                quantity = float(item["quantity"])
                item_rows.append(
                    (
                        document_id,
                        int(article["id"]),
                        str(item["code"]),
                        str(item["designation"]),
                        str(item["unit"]),
                        float(item["unit_price_ht"]),
                        quantity,
                        round(quantity * float(item["unit_price_ht"]), 2),
                    )
                )
            conn.executemany(
                """
                INSERT INTO document_items(
                    document_id, article_id, code, designation, unit,
                    unit_price_ht, quantity, total_ht
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                item_rows,
            )
        return int(document_id), total_ht, tva_amount, total_ttc

    def get_document(self, document_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, number, created_at, category, total_ht,
                       tva_rate, tva_amount, total_ttc, pdf_path, excel_path, exercice_label
                FROM documents WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

    def delete_document(self, document_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def document_editable(self, document_id: int) -> tuple[bool, str]:
        """Modifiabilité d'un document : ``(True, "")`` ou ``(False, motif)``.

        Un document n'est modifiable que si sa convention **et** son exercice
        sont encore actifs : les documents d'une convention clôturée/expirée et
        ceux d'un exercice clôturé restent en lecture seule, le cumul archivé
        à la clôture n'étant pas censé bouger.
        """
        with self.connect() as conn:
            doc = conn.execute(
                "SELECT category, exercice_label FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                return False, "Document introuvable."
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
            exercice_label = doc["exercice_label"]
            if not exercice_label:
                return False, "Ce document n'est rattaché à aucun exercice : lecture seule."
            exercice = conn.execute(
                "SELECT status FROM exercices WHERE category = ? AND label = ?",
                (category, exercice_label),
            ).fetchone()
            if not exercice:
                return False, f"L'exercice « {exercice_label} » est introuvable : lecture seule."
            if exercice["status"] != "active":
                return False, f"L'exercice « {exercice_label} » est clôturé : lecture seule."
        return True, ""

    def update_document(
        self,
        document_id: int,
        items: list[dict],
        tva_rate: float = TVA_RATE,
        pdf_path: str | None = None,
        excel_path: str | None = None,
    ) -> tuple[float, float, float]:
        """Remplace les lignes d'un document et recalcule ses totaux.

        Une seule transaction : suppression/insertion des lignes et mise à jour
        des totaux. Une ligne existante garde son prix figé au jour de la
        création (seule la quantité change) ; une ligne ajoutée doit appartenir
        à la liste active avec le même prix. Le contrôle du plafond est ferme :
        ``consommé hors ce document + nouveau total >= plafond`` refuse, égalité
        incluse.
        """
        if not items:
            raise ValueError("Un document doit contenir au moins une ligne.")
        editable, reason = self.document_editable(document_id)
        if not editable:
            raise ValueError(reason)
        total_ht, tva_amount, total_ttc = compute_totals(items, tva_rate)

        with self.connect() as conn:
            doc = conn.execute(
                "SELECT category, exercice_label FROM documents WHERE id = ?",
                (document_id,),
            ).fetchone()
            if not doc:
                raise ValueError("Document introuvable.")
            category = self._resolve_category_name(conn, doc["category"])
            exercice_label = doc["exercice_label"]
            exercice = conn.execute(
                "SELECT * FROM exercices WHERE category = ? AND label = ?",
                (category, exercice_label),
            ).fetchone()
            if not exercice:
                raise ValueError(f"Exercice « {exercice_label} » introuvable pour « {category} ».")
            if exercice["status"] != "active":
                raise ValueError(
                    f"L'exercice « {exercice_label} » est clôturé : "
                    "ce document est en lecture seule."
                )
            if exercice["plafond"] is not None:
                other_consumed = round(
                    float(
                        conn.execute(
                            "SELECT COALESCE(SUM(total_ht), 0) FROM documents "
                            "WHERE category = ? AND exercice_label = ? AND id != ?",
                            (category, exercice_label, document_id),
                        ).fetchone()[0]
                        or 0.0
                    ),
                    2,
                )
                projected = round(other_consumed + total_ht, 2)
                if projected >= round(float(exercice["plafond"]), 2):
                    raise ValueError(
                        "PLAFOND ATTEINT : la modification est bloquée.\n"
                        f"Consommé hors ce document : {other_consumed:.2f} DA + "
                        f"ce document {total_ht:.2f} DA = {projected:.2f} DA pour un "
                        f"plafond de {float(exercice['plafond']):.2f} DA.\n"
                        "Aucun dépassement n'est autorisé sur cette convention."
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
            for item in items:
                quantity = float(item["quantity"])
                if not math.isfinite(quantity) or quantity <= 0:
                    raise ValueError("La quantité doit être un nombre strictement positif.")
                item_id = item.get("item_id")
                if item_id is not None:
                    item_id = int(item_id)
                    if item_id in kept_ids:
                        raise ValueError("Une même ligne du document est listée deux fois.")
                    stored = existing.get(item_id)
                    if stored is None:
                        raise ValueError(
                            f"La ligne {item.get('code', '')} n'appartient plus "
                            "à ce document."
                        )
                    code, designation, unit = stored["code"], stored["designation"], stored["unit"]
                    price = float(stored["unit_price_ht"])
                else:
                    if item.get("category") not in (None, category):
                        raise ValueError(
                            f"La ligne {item['code']} n'appartient pas à la liste {category}."
                        )
                    article = conn.execute(
                        """
                        SELECT id, unit_price_ht FROM articles
                        WHERE category = ? AND code = ? AND designation = ? AND unit = ?
                        """,
                        (category, item["code"], item["designation"], item["unit"]),
                    ).fetchone()
                    if article is None:
                        raise ValueError(
                            f"L'article {item['code']} n'existe plus dans la liste {category}."
                        )
                    if abs(float(article["unit_price_ht"]) - float(item["unit_price_ht"])) > 0.0001:
                        raise ValueError(
                            f"Le prix de {item['code']} a changé. Importez la liste à jour."
                        )
                    code, designation, unit = str(item["code"]), str(item["designation"]), str(item["unit"])
                    price = float(article["unit_price_ht"])
                resolved = conn.execute(
                    "SELECT id FROM articles WHERE category = ? AND code = ? "
                    "AND designation = ? AND unit = ?",
                    (category, code, designation, unit),
                ).fetchone()
                line_total = round(quantity * price, 2)
                if item_id is not None:
                    kept_ids.add(item_id)
                    updates.append(
                        (quantity, line_total, int(resolved["id"]) if resolved else None,
                         item_id, document_id)
                    )
                else:
                    insert_rows.append(
                        (
                            document_id,
                            int(resolved["id"]) if resolved else None,
                            code,
                            designation,
                            unit,
                            price,
                            quantity,
                            line_total,
                        )
                    )
            # Les lignes conservées gardent leur identifiant : seul le reste est
            # remplacé, la réinsertion finissant par les lignes ajoutées.
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
                    "UPDATE document_items SET quantity = ?, total_ht = ?, "
                    "article_id = ? WHERE id = ? AND document_id = ?",
                    updates,
                )
            if insert_rows:
                conn.executemany(
                    """
                    INSERT INTO document_items(
                        document_id, article_id, code, designation, unit,
                        unit_price_ht, quantity, total_ht
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    insert_rows,
                )
            conn.execute(
                """
                UPDATE documents
                SET total_ht = ?, tva_rate = ?, tva_amount = ?, total_ttc = ?,
                    pdf_path = COALESCE(?, pdf_path), excel_path = COALESCE(?, excel_path)
                WHERE id = ?
                """,
                (
                    total_ht, tva_rate, tva_amount, total_ttc,
                    pdf_path, excel_path, document_id,
                ),
            )
        return total_ht, tva_amount, total_ttc

    def list_documents(
        self,
        text: str = "",
        category: str | None = None,
        exercice: str | None = None,
    ) -> list[sqlite3.Row]:
        columns = (
            "id, number, created_at, category, total_ht, "
            "tva_rate, tva_amount, total_ttc, pdf_path, excel_path, exercice_label"
        )
        conditions: list[str] = []
        params: list[object] = []
        if text.strip():
            like = f"%{text.strip()}%"
            conditions.append(
                "(number LIKE ? OR category LIKE ? OR created_at LIKE ?)"
            )
            params.extend((like, like, like))
        if category:
            conditions.append("category = ?")
            params.append(category)
        if exercice:
            conditions.append("exercice_label = ?")
            params.append(exercice)
        where = f" WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.connect() as conn:
            return conn.execute(
                f"SELECT {columns} FROM documents{where} ORDER BY id DESC",
                params,
            ).fetchall()

    def document_items(self, document_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, article_id, code, designation, unit, unit_price_ht,
                       quantity, total_ht
                FROM document_items WHERE document_id = ? ORDER BY id
                """,
                (document_id,),
            ).fetchall()

    # ------------------------------------------------------------- rapports

    def exercice_documents(
        self, exercice_label: str, category: str | None = None
    ) -> list[sqlite3.Row]:
        columns = (
            "id, number, created_at, category, total_ht, tva_rate, tva_amount, "
            "total_ttc, exercice_label"
        )
        with self.connect() as conn:
            if category:
                return conn.execute(
                    f"SELECT {columns} FROM documents "
                    "WHERE exercice_label = ? AND category = ? "
                    "ORDER BY category COLLATE NOCASE, id",
                    (exercice_label, category),
                ).fetchall()
            return conn.execute(
                f"SELECT {columns} FROM documents "
                "WHERE exercice_label = ? ORDER BY category COLLATE NOCASE, id",
                (exercice_label,),
            ).fetchall()

    def exercice_consumption_report(self, exercice_label: str) -> list[dict]:
        """Données du rapport de consommation d'un exercice, par convention.

        Corrige l'incohérence de la ligne TOTAL : les plafonds ne se somment
        que sur les conventions qui en ont un, et le taux global vaut
        ``(Σplafonds - Σrestes) / Σplafonds``.
        """
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
                exercice_row = next(
                    (r for r in rows if r["category"] == name), None
                )
                plafond = (
                    None
                    if exercice_row is None or exercice_row["plafond"] is None
                    else float(exercice_row["plafond"])
                )
                consumed = consumptions.get(name, 0.0)
                doc_count = counts.get(name, 0)
                if plafond is None:
                    summary = {
                        "category": name,
                        "label": exercice_label,
                        "plafond": None,
                        "consumed": consumed,
                        "remaining": None,
                        "rate": None,
                    }
                else:
                    remaining = round(plafond - consumed, 2)
                    summary = {
                        "category": name,
                        "label": exercice_label,
                        "plafond": plafond,
                        "consumed": consumed,
                        "remaining": remaining,
                        "rate": (consumed / plafond) if plafond else None,
                    }
                summary["doc_count"] = doc_count
                out.append(summary)
            return out

    # ------------------------------------------------------------- résolution

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
                "SELECT name FROM categories WHERE name = ? COLLATE NOCASE", (name.strip(),)
            ).fetchone()
        return row[0] if row else None

    def add_category(self, name: str, sheet_name: str | None = None, prefix: str | None = None) -> None:
        with self.connect() as conn:
            name = self._resolve_category_name(conn, name)
            pfx = (prefix or "").strip().upper()[:3]
            if not pfx:
                pfx = self._unique_prefix(conn, self._make_prefix(name))
            conn.execute(
                "INSERT INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
                (name, (sheet_name or name).strip(), pfx),
            )
