@echo off
setlocal
python -m pip install --upgrade pyinstaller reportlab
pyinstaller --noconfirm --clean --windowed --name GestionArticles --add-data "source_listes.xlsx;." main.py
pause
