#!/usr/bin/env bash
# Start produkcyjny - waitress na 127.0.0.1:4666
set -euo pipefail

# Skrypt zyje w scripts/, projekt jest piętro wyżej
cd "$(dirname "$0")/.."

if [ ! -f ".env" ]; then
    echo "[BLAD] Brak pliku .env. Skopiuj .env.example -> .env"
    echo "       i uzupelnij sekrety: python scripts/generate_keys.py"
    exit 1
fi

# Aktywuj venv jesli istnieje
if [ -d "venv" ]; then
    # shellcheck disable=SC1091
    source venv/bin/activate
fi

echo "[PRODUKCJA] Aplikacja bedzie dostepna LOKALNIE na 127.0.0.1"
echo "[PRODUKCJA] Swiat widzi ja dopiero przez cloudflared tunnel."
echo

exec python app.py
