from app.config import DB_PATH, SEED_XLSX
from app.database import Database
from app.services.importer import import_articles


def main() -> None:
    rows = import_articles(SEED_XLSX)
    database = Database(DB_PATH)
    grouped: dict[str, list[tuple[str, str, str, str, float]]] = {}
    for category, code, designation, unit, price in rows:
        grouped.setdefault(category, []).append(
            (category, code, designation, unit, price)
        )

    imported = 0
    for category in grouped:
        result = database.replace_articles_by_category(
            grouped[category], source="Import initial"
        )
        imported += result["imported"]

    print(f"{imported} articles importés dans {len(grouped)} liste(s).")


if __name__ == "__main__":
    main()
