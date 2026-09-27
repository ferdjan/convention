@echo off
rem ====================================================================
rem  Gestion Articles (web) - demarrage local, hors-ligne
rem  Lance le serveur sur http://127.0.0.1:8765
rem ====================================================================
setlocal EnableExtensions
chcp 65001 >nul
cd /d "%~dp0"

rem ---------------------------------------------------------- Python
set "PY="
if exist "C:\Python314\python.exe" set "PY=C:\Python314\python.exe"
if not defined PY for /f "delims=" %%I in ('where python 2^>nul') do if not defined PY set "PY=%%I"
if not defined PY for /f "delims=" %%I in ('py -3 -c "import sys;print(sys.executable)" 2^>nul') do if not defined PY set "PY=%%I"
if not defined PY (
  echo [ERREUR] Python 3.10+ introuvable sur cette machine.
  echo Installez Python depuis https://www.python.org/downloads/ puis relancez.
  pause
  exit /b 1
)
echo [1/4] Python : %PY%

rem ------------------------------------------------------ dependances
"%PY%" -c "import flask, openpyxl, reportlab" >nul 2>nul
if errorlevel 1 (
  echo [2/4] Installation des dependances locales...
  "%PY%" -m pip install -r requirements.txt --disable-pip-version-check
  if errorlevel 1 (
    echo [ERREUR] Installation impossible : verifiez votre connexion puis reessayez.
    pause
    exit /b 1
  )
) else (
  echo [2/4] Dependances deja installees.
)

rem ------------------------------------------------------ base de donnees
set "FIRST=0"
if not exist "web_app.db" set "FIRST=1"
if not exist ".session.key" set "FIRST=1"
if "%FIRST%"=="1" (
  echo [3/4] Premiere execution : initialisation de la base...
  "%PY%" -m flask --app app init-db
  "%PY%" -m flask --app app import-seed
) else (
  echo [3/4] Base prete.
)

rem ---------------------------------------------------------- serveur
echo [4/4] Demarrage du serveur sur http://127.0.0.1:8765
start "" "http://127.0.0.1:8765"
"%PY%" serve.py %*
if errorlevel 1 (
  echo.
  echo [ERREUR] Le serveur s'est arrete avec une erreur - voir le message ci-dessus.
  pause
)
endlocal
