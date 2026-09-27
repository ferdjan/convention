"""Enregistrement des documents : fichiers PDF/Excel + base, de façon cohérente.

Séquence retenue (identique à l'édition bureau) :
1. **validation complète** sans écriture (``Database.preview_document``) ;
2. génération des fichiers, puis déplacement vers leur destination ;
3. écriture en base (une seule transaction) ;
4. si l'écriture échoue, les fichiers viennent d'être créés sont supprimés
   (création) ou les anciens sont **restaurés** à partir de sauvegardes
   ``.bak`` (modification) — jamais de divergence fichier / base.
"""
from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

from app.config import EXPORT_DIR, TVA_RATE
from app.database import Database
from app.reports.annual import build_exercice_report
from app.reports.excel import build_excel
from app.reports.pdf import build_pdf
from app.utils import format_date

TMP_DIR = EXPORT_DIR / ".tmp"


def _prepare_dirs() -> None:
    EXPORT_DIR.mkdir(parents=True, exist_ok=True)
    TMP_DIR.mkdir(parents=True, exist_ok=True)


def cleanup_tmp() -> None:
    """Supprime les fichiers de travail laissés par un arrêt brutal."""
    if not TMP_DIR.exists():
        return
    for child in TMP_DIR.iterdir():
        try:
            if child.is_file():
                child.unlink()
            elif child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
        except OSError:
            continue


def _increment(number: str) -> str:
    head, sep, seq = number.rpartition("-")
    if not sep:
        return number
    try:
        return f"{head}-{int(seq) + 1:04d}"
    except ValueError:
        return number


def free_number(db: Database, category: str, exercice_label: str) -> str:
    """Prochain numéro libre : ni en base, ni déjà sur le disque."""
    number = db.next_document_number(category, exercice_label)
    seen = 0
    while seen < 10000:
        if not db.document_number_exists(number) and not _files_exist(number):
            return number
        number = _increment(number)
        seen += 1
    raise ValueError("Impossible de générer un numéro de document libre.")


def _files_exist(number: str) -> bool:
    return (EXPORT_DIR / f"{number}.pdf").exists() or (
        EXPORT_DIR / f"{number}.xlsx"
    ).exists()


def _generate(
    target_pdf: Path,
    target_excel: Path,
    number: str,
    created_at: str,
    category: str,
    lines: list[dict],
    total_ht: float,
    tva_amount: float,
    total_ttc: float,
) -> None:
    date_text = format_date(created_at, "%d/%m/%Y")
    build_pdf(
        target_pdf, number, date_text, category, lines,
        total_ht, TVA_RATE, tva_amount, total_ttc,
    )
    build_excel(
        target_excel, number, date_text, category, lines,
        total_ht, TVA_RATE, tva_amount, total_ttc,
    )


def create_document(
    db: Database,
    *,
    category: str,
    items: list[dict],
    created_at: str | None = None,
    exercice_label: str | None = None,
    accept_new_prices: bool = False,
) -> dict:
    """Valide, génère les fichiers, puis enregistre le document."""
    _prepare_dirs()
    created_at = created_at or datetime.now().isoformat(timespec="seconds")
    preview = db.preview_document(
        category, items, exercice_label, accept_new_prices=accept_new_prices
    )
    number = free_number(db, preview["category"], preview["exercice_label"])

    rel_pdf = f"{number}.pdf"
    rel_excel = f"{number}.xlsx"
    final_pdf = EXPORT_DIR / rel_pdf
    final_excel = EXPORT_DIR / rel_excel
    tmp_pdf = TMP_DIR / f"{number}.pdf"
    tmp_excel = TMP_DIR / f"{number}.xlsx"

    _generate(
        tmp_pdf, tmp_excel, number, created_at, preview["category"],
        preview["lines"], preview["total_ht"], preview["tva_amount"],
        preview["total_ttc"],
    )
    try:
        tmp_pdf.replace(final_pdf)
        tmp_excel.replace(final_excel)
    except OSError:
        _unlink(tmp_pdf, tmp_excel)
        raise

    try:
        document_id, total_ht, tva_amount, total_ttc = db.save_document(
            number,
            created_at,
            preview["category"],
            items,
            TVA_RATE,
            preview["exercice_label"],
            rel_pdf,
            rel_excel,
            accept_new_prices=accept_new_prices,
        )
    except Exception:
        _unlink(final_pdf, final_excel)
        _unlink(tmp_pdf, tmp_excel)
        raise

    return {
        "id": document_id,
        "number": number,
        "created_at": created_at,
        "category": preview["category"],
        "exercice_label": preview["exercice_label"],
        "total_ht": total_ht,
        "tva_amount": tva_amount,
        "total_ttc": total_ttc,
        "pdf": rel_pdf,
        "excel": rel_excel,
    }


def update_document(
    db: Database,
    document_id: int,
    *,
    items: list[dict],
    accept_new_prices: bool = False,
) -> dict:
    """Remplace les lignes d'un document et régénère ses fichiers.

    Les anciens fichiers sont sauvegardés en ``.bak`` ; en cas d'échec de
    l'écriture en base, ils sont restaurés et les fichiers neufs supprimés.
    """
    _prepare_dirs()
    editable, reason = db.document_editable(document_id)
    if not editable:
        raise ValueError(reason)
    doc = db.get_document(document_id)
    if not doc:
        raise ValueError("Document introuvable.")

    preview = db.preview_document(
        doc["category"],
        items,
        doc["exercice_label"],
        accept_new_prices=accept_new_prices,
        exclude_document=document_id,
    )
    number = doc["number"]
    rel_pdf = doc["pdf_path"] or f"{number}.pdf"
    rel_excel = doc["excel_path"] or f"{number}.xlsx"
    final_pdf = EXPORT_DIR / rel_pdf
    final_excel = EXPORT_DIR / rel_excel
    tmp_pdf = TMP_DIR / f"{number}.pdf"
    tmp_excel = TMP_DIR / f"{number}.xlsx"
    bak_pdf = final_pdf.with_suffix(final_pdf.suffix + ".bak")
    bak_excel = final_excel.with_suffix(final_excel.suffix + ".bak")

    had_pdf = final_pdf.exists()
    had_excel = final_excel.exists()
    if had_pdf:
        shutil.copy2(final_pdf, bak_pdf)
    if had_excel:
        shutil.copy2(final_excel, bak_excel)

    _generate(
        tmp_pdf, tmp_excel, number, doc["created_at"], preview["category"],
        preview["lines"], preview["total_ht"], preview["tva_amount"],
        preview["total_ttc"],
    )
    try:
        if tmp_pdf.exists():
            tmp_pdf.replace(final_pdf)
        if tmp_excel.exists():
            tmp_excel.replace(final_excel)
    except OSError:
        _restore(bak_pdf, final_pdf, existed=had_pdf)
        _restore(bak_excel, final_excel, existed=had_excel)
        _unlink(tmp_pdf, tmp_excel)
        raise

    try:
        total_ht, tva_amount, total_ttc = db.update_document(
            document_id,
            items,
            TVA_RATE,
            rel_pdf,
            rel_excel,
            accept_new_prices=accept_new_prices,
        )
    except Exception:
        _restore(bak_pdf, final_pdf, existed=had_pdf)
        _restore(bak_excel, final_excel, existed=had_excel)
        _unlink(tmp_pdf, tmp_excel)
        raise
    finally:
        _unlink(bak_pdf, bak_excel)

    return {
        "id": document_id,
        "number": number,
        "total_ht": total_ht,
        "tva_amount": tva_amount,
        "total_ttc": total_ttc,
        "pdf": rel_pdf,
        "excel": rel_excel,
    }


def _restore(bak: Path, target: Path, *, existed: bool) -> None:
    try:
        if bak.exists():
            shutil.copy2(bak, target)
        elif not existed and target.exists():
            target.unlink()
    except OSError:
        # La restauration ne doit jamais masquer l'erreur d'origine.
        pass


def _unlink(*paths: Path) -> None:
    for path in paths:
        try:
            if path.exists():
                path.unlink()
        except OSError:
            continue


# --------------------------------------------------------------- exports

def _tmp_bytes(writer, stem: str) -> tuple[bytes, str]:
    """Exécute un générateur Excel dans le dossier temporaire et renvoie le binaire."""
    _prepare_dirs()
    target = TMP_DIR / f"{stem}.xlsx"
    try:
        writer(target)
        payload = target.read_bytes()
    finally:
        _unlink(target)
    return payload, target.name


def export_document_excel(db: Database, document_id: int) -> tuple[bytes, str] | None:
    doc = db.get_document(document_id)
    if not doc:
        return None
    lines = [
        {
            "code": row["code"],
            "designation": row["designation"],
            "unit": row["unit"],
            "unit_price_ht": row["unit_price_ht"],
            "quantity": row["quantity"],
        }
        for row in db.document_items(document_id)
    ]
    number = doc["number"]
    date_text = format_date(doc["created_at"], "%d/%m/%Y")

    def writer(target: Path) -> None:
        build_excel(
            target, number, date_text, doc["category"], lines,
            float(doc["total_ht"]), float(doc["tva_rate"] or TVA_RATE),
            float(doc["tva_amount"] or 0), float(doc["total_ttc"] or 0),
        )

    return _tmp_bytes(writer, f"export-{number}")


def export_exercice_report(db: Database, label: str) -> tuple[bytes, str]:
    rows = db.exercice_consumption_report(label)
    documents = db.exercice_documents(label)

    def writer(target: Path) -> None:
        build_exercice_report(target, label, rows, documents)

    return _tmp_bytes(writer, f"rapport-{label}")


def export_civil_report(db: Database, year: str) -> tuple[bytes, str]:
    rows = db.civil_year_report(year)
    documents = db.civil_year_documents(year)

    def writer(target: Path) -> None:
        build_exercice_report(target, year, rows, documents, kind="ANNÉE CIVILE")

    return _tmp_bytes(writer, f"rapport-civil-{year}")


def export_template(categories: list[str]) -> tuple[bytes, str]:
    """Modèle Excel vierge (en-têtes seuls) : une feuille par liste."""
    from app.importer import write_template

    def writer(target: Path) -> None:
        write_template(target, categories)

    return _tmp_bytes(writer, "modele-listes")
