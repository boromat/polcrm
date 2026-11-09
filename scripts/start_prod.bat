@echo off
REM scripts/start_prod.bat - produkcja (waitress na 127.0.0.1, logowanie wg AUTH_MODE z .env)
cd /d "%~dp0\.."
title PolCRM - PRODUKCJA
echo ============================================
echo   PolCRM - PRODUKCJA (waitress)
echo ============================================
echo.

if not exist ".env" (
    echo [BLAD] Brak pliku .env. Skopiuj .env.example -^> .env
    echo        i uzupelnij sekrety: .venv\Scripts\python.exe scripts\generate_keys.py
    pause
    exit /b 1
)

echo  Konfiguracja z .env
echo  Aplikacja bedzie dostepna LOKALNIE na 127.0.0.1
echo  Swiat widzi ja dopiero przez cloudflared tunnel albo reverse proxy z HTTPS.
echo.

if exist .venv\Scripts\python.exe (
    .venv\Scripts\python.exe app.py
) else (
    py app.py
)
pause
