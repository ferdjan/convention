from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS categories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    sheet_name TEXT,
    prefix TEXT
);

CREATE TABLE IF NOT EXISTS articles (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    category TEXT NOT NULL,
    code TEXT NOT NULL,
    designation TEXT NOT NULL,
    unit TEXT NOT NULL,
    unit_price_ht REAL NOT NULL,
    UNIQUE(category, code, designation, unit, unit_price_ht)
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
    excel_path TEXT
);

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

CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
CREATE INDEX IF NOT EXISTS idx_document_items_document ON document_items(document_id);
"""

DEFAULT_CATEGORIES = ("Informatique", "Bureautique")
DEFAULT_PREFIXES = {"Informatique": "INF", "Bureautique": "BUR"}

TVA_RATE = 0.19


def compute_totals(items: Iterable[dict], rate: float = TVA_RATE) -> tuple[float, float, float]:
    """Retourne (total HT, montant TVA, total TTC)."""
    total_ht = round(sum(float(i["quantity"]) * float(i["unit_price_ht"]) for i in items), 2)
    tva_amount = round(total_ht * rate, 2)
    total_ttc = round(total_ht + tva_amount, 2)
    return total_ht, tva_amount, total_ttc


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
        finally:
            conn.close()

    def init_schema(self) -> None:
        conn = sqlite3.connect(self.path)
        conn.row_factory = sqlite3.Row
        conn.isolation_level = None
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            conn.executescript(SCHEMA)
            self._migrate(conn)
            conn.execute("PRAGMA foreign_keys = ON")
        finally:
            conn.close()
        self._ensure_categories()

    def _migrate(self, conn: sqlite3.Connection) -> None:
        row = conn.execute(
            "SELECT group_concat(sql, ' ') FROM sqlite_master "
            "WHERE type = 'table' AND name IN ('articles', 'documents')"
        ).fetchone()
        legacy_sql = row[0] if row and row[0] else ""
        if "CHECK(category IN" in legacy_sql:
            conn.executescript(
                """
                CREATE TABLE articles_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    category TEXT NOT NULL,
                    code TEXT NOT NULL,
                    designation TEXT NOT NULL,
                    unit TEXT NOT NULL,
                    unit_price_ht REAL NOT NULL,
                    UNIQUE(category, code, designation, unit, unit_price_ht)
                );
                INSERT INTO articles_new(id, category, code, designation, unit, unit_price_ht)
                    SELECT id, category, code, designation, unit, unit_price_ht FROM articles;
                DROP TABLE articles;
                ALTER TABLE articles_new RENAME TO articles;

                CREATE TABLE documents_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    number TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    category TEXT NOT NULL,
                    total_ht REAL NOT NULL,
                    pdf_path TEXT,
                    excel_path TEXT
                );
                INSERT INTO documents_new(id, number, created_at, category, total_ht, pdf_path)
                    SELECT id, number, created_at, category, total_ht, pdf_path FROM documents;
                DROP TABLE documents;
                ALTER TABLE documents_new RENAME TO documents;

                CREATE INDEX IF NOT EXISTS idx_articles_category ON articles(category);
                CREATE INDEX IF NOT EXISTS idx_articles_search ON articles(category, code, designation);
                CREATE INDEX IF NOT EXISTS idx_documents_created_at ON documents(created_at);
                CREATE INDEX IF NOT EXISTS idx_document_items_document ON document_items(document_id);
                """
            )
        if not self._column_exists(conn, "documents", "excel_path"):
            conn.execute("ALTER TABLE documents ADD COLUMN excel_path TEXT")
        if not self._column_exists(conn, "categories", "prefix"):
            conn.execute("ALTER TABLE categories ADD COLUMN prefix TEXT")

        for column in ("tva_rate", "tva_amount", "total_ttc"):
            if not self._column_exists(conn, "documents", column):
                conn.execute(f"ALTER TABLE documents ADD COLUMN {column} REAL")
        conn.execute("UPDATE documents SET tva_rate = ? WHERE tva_rate IS NULL", (TVA_RATE,))
        conn.execute(
            "UPDATE documents SET tva_amount = ROUND(total_ht * tva_rate, 2) WHERE tva_amount IS NULL"
        )
        conn.execute(
            "UPDATE documents SET total_ttc = ROUND(total_ht + tva_amount, 2) WHERE total_ttc IS NULL"
        )

        items_row = conn.execute(
            "SELECT sql FROM sqlite_master WHERE type = 'table' AND name = 'document_items'"
        ).fetchone()
        items_sql = items_row[0] if items_row and items_row[0] else ""
        if items_sql and "ON DELETE SET NULL" not in items_sql:
            conn.executescript(
                """
                CREATE TABLE document_items_new (
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
                INSERT INTO document_items_new(
                    id, document_id, article_id, code, designation, unit,
                    unit_price_ht, quantity, total_ht
                )
                    SELECT id, document_id, article_id, code, designation, unit,
                           unit_price_ht, quantity, total_ht
                    FROM document_items;
                DROP TABLE document_items;
                ALTER TABLE document_items_new RENAME TO document_items;
                CREATE INDEX IF NOT EXISTS idx_document_items_document ON document_items(document_id);
                """
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
        for i in range(2, 100):
            candidate = (base[:2] + str(i % 10)) if len(base) >= 2 else (base + str(i))[:3]
            candidate = candidate[:3]
            if candidate not in used:
                return candidate
        return base

    def _ensure_categories(self) -> None:
        with self.connect() as conn:
            rows = conn.execute("SELECT name, prefix FROM categories").fetchall()
            if not rows:
                for name in DEFAULT_CATEGORIES:
                    conn.execute(
                        "INSERT INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
                        (name, name, DEFAULT_PREFIXES.get(name, self._make_prefix(name))),
                    )
                rows = conn.execute("SELECT name, prefix FROM categories").fetchall()
            existing = {r["name"] for r in rows}
            used = {r[0] for r in conn.execute("SELECT DISTINCT category FROM articles")}
            for name in sorted(used - existing):
                conn.execute(
                    "INSERT OR IGNORE INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
                    (name, name, self._unique_prefix(conn, self._make_prefix(name))),
                )
            for name, prefix in conn.execute("SELECT name, prefix FROM categories").fetchall():
                if not prefix:
                    conn.execute(
                        "UPDATE categories SET prefix = ? WHERE name = ?",
                        (self._unique_prefix(conn, self._make_prefix(name), exclude_name=name), name),
                    )

    def list_categories(self) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                "SELECT id, name, sheet_name, prefix FROM categories ORDER BY name COLLATE NOCASE"
            ).fetchall()

    def category_names(self) -> list[str]:
        return [row["name"] for row in self.list_categories()]

    def category_prefix(self, name: str) -> str:
        with self.connect() as conn:
            row = conn.execute("SELECT prefix FROM categories WHERE name = ?", (name,)).fetchone()
        return (row[0] if row and row[0] else self._make_prefix(name)) or "DOC"

    def add_category(self, name: str, sheet_name: str | None = None, prefix: str | None = None) -> None:
        name = name.strip()
        if not name:
            raise ValueError("Le nom de la liste ne peut pas être vide.")
        with self.connect() as conn:
            pfx = (prefix or "").strip().upper()[:3]
            if not pfx:
                pfx = self._unique_prefix(conn, self._make_prefix(name))
            conn.execute(
                "INSERT INTO categories(name, sheet_name, prefix) VALUES (?, ?, ?)",
                (name, (sheet_name or name).strip(), pfx),
            )

    def delete_category(self, name: str) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM articles WHERE category = ?", (name,))
            conn.execute("DELETE FROM categories WHERE name = ?", (name,))

    def article_count(self) -> int:
        with self.connect() as conn:
            return conn.execute("SELECT COUNT(*) FROM articles").fetchone()[0]

    def clear_articles(self) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM articles")

    def replace_articles(self, rows: Iterable[tuple[str, str, str, str, float]]) -> int:
        rows = list(rows)
        with self.connect() as conn:
            conn.execute("DELETE FROM articles")
            conn.executemany(
                """
                INSERT INTO articles(category, code, designation, unit, unit_price_ht)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

    def replace_articles_by_category(self, rows: Iterable[tuple[str, str, str, str, float]]) -> int:
        rows = list(rows)
        categories = sorted({row[0] for row in rows})
        with self.connect() as conn:
            for category in categories:
                conn.execute("DELETE FROM articles WHERE category = ?", (category,))
            conn.executemany(
                """
                INSERT INTO articles(category, code, designation, unit, unit_price_ht)
                VALUES (?, ?, ?, ?, ?)
                """,
                rows,
            )
        return len(rows)

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

    def next_document_number(self, category: str | None = None) -> str:
        from datetime import datetime
        year = datetime.now().year
        prefix = self.category_prefix(category) if category else "DOC"
        number_prefix = f"{prefix}-{year}-"
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

    def save_document(
        self,
        number: str,
        created_at: str,
        category: str,
        items: list[dict],
        tva_rate: float = TVA_RATE,
    ) -> tuple[int, float, float, float]:
        total_ht, tva_amount, total_ttc = compute_totals(items, tva_rate)
        with self.connect() as conn:
            cur = conn.execute(
                """
                INSERT INTO documents(number, created_at, category, total_ht, tva_rate, tva_amount, total_ttc)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (number, created_at, category, total_ht, tva_rate, tva_amount, total_ttc),
            )
            document_id = cur.lastrowid
            conn.executemany(
                """
                INSERT INTO document_items(
                    document_id, article_id, code, designation, unit,
                    unit_price_ht, quantity, total_ht
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                [
                    (
                        document_id,
                        int(i["article_id"]),
                        i["code"],
                        i["designation"],
                        i["unit"],
                        float(i["unit_price_ht"]),
                        float(i["quantity"]),
                        round(float(i["quantity"]) * float(i["unit_price_ht"]), 2),
                    )
                    for i in items
                ],
            )
        return int(document_id), total_ht, tva_amount, total_ttc

    def set_paths(self, document_id: int, pdf_path: str | None = None, excel_path: str | None = None) -> None:
        with self.connect() as conn:
            if pdf_path is not None:
                conn.execute("UPDATE documents SET pdf_path = ? WHERE id = ?", (pdf_path, document_id))
            if excel_path is not None:
                conn.execute("UPDATE documents SET excel_path = ? WHERE id = ?", (excel_path, document_id))

    def get_document(self, document_id: int) -> sqlite3.Row | None:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT id, number, created_at, category, total_ht,
                       tva_rate, tva_amount, total_ttc, pdf_path, excel_path
                FROM documents WHERE id = ?
                """,
                (document_id,),
            ).fetchone()

    def delete_document(self, document_id: int) -> None:
        with self.connect() as conn:
            conn.execute("DELETE FROM documents WHERE id = ?", (document_id,))

    def list_documents(self, text: str = "") -> list[sqlite3.Row]:
        columns = (
            "id, number, created_at, category, total_ht, "
            "tva_rate, tva_amount, total_ttc, pdf_path, excel_path"
        )
        with self.connect() as conn:
            if text.strip():
                like = f"%{text.strip()}%"
                return conn.execute(
                    f"""
                    SELECT {columns}
                    FROM documents
                    WHERE number LIKE ? OR category LIKE ? OR created_at LIKE ?
                    ORDER BY id DESC
                    """,
                    (like, like, like),
                ).fetchall()
            return conn.execute(
                f"""
                SELECT {columns}
                FROM documents ORDER BY id DESC
                """
            ).fetchall()

    def document_items(self, document_id: int) -> list[sqlite3.Row]:
        with self.connect() as conn:
            return conn.execute(
                """
                SELECT article_id, code, designation, unit, unit_price_ht, quantity, total_ht
                FROM document_items WHERE document_id = ? ORDER BY id
                """,
                (document_id,),
            ).fetchall()
