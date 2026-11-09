@echo off
REM scripts/start.bat - dev (lokalnie, debug ON, logowanie haslem)
cd /d "%~dp0\.."
title PolCRM - DEV
echo ============================================
echo   PolCRM - tryb DEV (Flask + debug)
echo   Lokalnie, logowanie haslem (pierwsze uruchomienie: /setup)
echo ============================================
echo.

set FLASK_ENV=development
set APP_HOST=127.0.0.1
set APP_PORT=4666
set AUTH_MODE=password
set SESSION_COOKIE_SECURE=false

echo  Serwer DEV: http://127.0.0.1:4666
echo  Ctrl+C aby zatrzymac.
echo.

REM Uzyj .venv, jesli istnieje (scripts\install_requirements.bat), inaczej systemowego Pythona.
if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app.py
) else (
    py app.py
)
pause
