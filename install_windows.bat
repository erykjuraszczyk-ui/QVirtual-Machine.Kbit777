@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  echo Nie znaleziono launchera py. Zainstaluj Python 3.12 64-bit z python.org i zaznacz Add Python to PATH.
  pause
  exit /b 1
)
py -3.12 -m venv .venv
if errorlevel 1 (
  echo Nie udalo sie utworzyc venv dla Python 3.12.
  echo Sprawdz instalacje Python 3.12 64-bit.
  pause
  exit /b 1
)
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
if errorlevel 1 (
  echo Instalacja zaleznosci nie powiodla sie.
  pause
  exit /b 1
)
echo Instalacja zakonczona.
pause
