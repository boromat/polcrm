#!/usr/bin/env bash
# Instalacja zaleznosci PolCRM na Linux (Ubuntu/Debian)
set -euo pipefail

echo "============================================"
echo "  PolCRM - instalacja zaleznosci (Linux)"
echo "============================================"

# Skrypt zyje w scripts/, projekt jest piętro wyżej
cd "$(dirname "$0")/.."

# Utworz venv jesli nie ma
if [ ! -d "venv" ]; then
    echo "[1/3] Tworze virtualenv..."
    python3 -m venv venv
fi

# Aktywuj venv i zainstaluj
echo "[2/3] Aktywuje venv i instaluje paczki..."
# shellcheck disable=SC1091
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

echo "[3/3] Gotowe."
echo
echo "Nastepne kroki:"
echo "  1. source venv/bin/activate"
echo "  2. python scripts/generate_keys.py   -- wygeneruj sekrety"
echo "  3. cp .env.example .env  +  wklej sekrety"
echo "  4. ./scripts/start_prod.sh (produkcja) lub python app.py (dev)"
