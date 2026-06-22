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

echo Odswiezam pulpit z lokalnej bazy...
".venv\Scripts\python.exe" scripts\make_dashboard.py
if errorlevel 1 (
  echo.
  echo Nie udalo sie wygenerowac pulpitu.
  pause
  exit /b 1
)

echo.
echo Pulpit monitoringu:
echo http://127.0.0.1:8000/dashboard/
echo.
echo Zostaw to okno otwarte. Zamkniecie okna zatrzyma panel.
start "" "http://127.0.0.1:8000/dashboard/"
".venv\Scripts\python.exe" -m http.server 8000 --bind 127.0.0.1 --directory reports
