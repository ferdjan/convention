from db import Database
from xlsx_importer import extract_articles
from pathlib import Path
here=Path(__file__).resolve().parent
rows=extract_articles(here/'source_listes.xlsx')
db=Database(here/'gestion_articles.db')
print('Imported', db.replace_articles(rows), 'articles')
