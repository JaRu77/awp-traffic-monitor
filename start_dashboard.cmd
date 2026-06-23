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

echo Uruchamiam pulpit i pobieram najnowszy stan z GitHuba...
echo.
".venv\Scripts\python.exe" scripts\serve_dashboard.py --sync
