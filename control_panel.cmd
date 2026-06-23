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

echo Uruchamiam lokalna appke kontrolna AWP...
echo.
".venv\Scripts\python.exe" scripts\control_panel.py
