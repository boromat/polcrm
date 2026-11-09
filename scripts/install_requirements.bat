@echo off
REM scripts/install_requirements.bat - tworzy .venv i instaluje zaleznosci
cd /d "%~dp0\.."
echo ============================================
echo   PolCRM - instalacja zaleznosci
echo ============================================
echo.
if not exist ".venv\Scripts\python.exe" (
    echo [1/2] Tworze srodowisko .venv...
    py -3 -m venv .venv
)
echo [2/2] Instaluje paczki z requirements.txt...
.venv\Scripts\python.exe -m pip install --upgrade pip
.venv\Scripts\python.exe -m pip install -r requirements.txt
echo.
echo Gotowe!
echo.
echo Opcjonalnie: maskowanie danych osobowych dla asystenta AI
echo   .venv\Scripts\python.exe -m pip install polanon
echo.
echo Nastepne kroki:
echo   1. .venv\Scripts\python.exe scripts\seed_test_data.py   -- dane testowe (dev)
echo   2. scripts\start.bat                                    -- http://127.0.0.1:4666
echo.
echo Produkcja: .venv\Scripts\python.exe scripts\generate_keys.py,
echo skopiuj .env.example -^> .env, wklej sekrety i uruchom scripts\start_prod.bat
echo.
pause
