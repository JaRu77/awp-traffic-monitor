@echo off
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
  echo Brak lokalnego srodowiska .venv.
  echo Najpierw uruchom:
  echo python -m venv .venv
  echo .\.venv\Scripts\python.exe -m pip install -r requirements.txt
  pause
  exit /b 1
)

echo Pobieram najnowszy stan badania z GitHuba...
".venv\Scripts\python.exe" scripts\sync_from_github.py
if errorlevel 1 (
  echo.
  echo Nie udalo sie pobrac najnowszego stanu.
  echo Sprawdz internet, logowanie do GitHuba albo uruchom ponownie za chwile.
  pause
  exit /b 1
)

echo.
echo Gotowe. Jesli pulpit jest otwarty, odswiez strone:
echo http://127.0.0.1:8000/dashboard/
echo.
pause
