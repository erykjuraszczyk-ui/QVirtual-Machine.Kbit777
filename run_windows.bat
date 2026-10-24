@echo off
setlocal
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
  echo Najpierw uruchom install_windows.bat
  pause
  exit /b 1
)
".venv\Scripts\python.exe" -m uvicorn app.server:app --host 127.0.0.1 --port 8000
pause
