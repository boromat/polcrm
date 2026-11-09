#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# PolCRM - automatyczny setup na Linux VPS (Ubuntu/Debian)
# ──────────────────────────────────────────────────────────────
# Uruchom JEDEN raz po wgraniu kodu na serwer:
#
#     cd ~/polcrm
#     chmod +x scripts/deploy_setup.sh
#     ./scripts/deploy_setup.sh
#
# Skrypt:
#   1. Stworzy venv + zainstaluje zaleznosci
#   2. Wygeneruje sekrety i utworzy .env (jesli nie istnieje)
#   3. Zainstaluje uslugę systemd
#   4. Wypisze co jeszcze trzeba zrobic recznie
#
# Skrypt NIE startuje aplikacji - chce zebys najpierw uzupelnil
# ALLOWED_EMAILS w .env. Po tym uruchom:
#     sudo systemctl enable --now polcrm
# ──────────────────────────────────────────────────────────────
set -euo pipefail

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { echo -e "${BLUE}[$(date +%H:%M:%S)]${NC} $*"; }
ok()   { echo -e "${GREEN}✓${NC} $*"; }
warn() { echo -e "${YELLOW}⚠${NC}  $*"; }
err()  { echo -e "${RED}✗${NC} $*" >&2; }

# Skrypt zyje w scripts/, projekt jest piętro wyżej
cd "$(dirname "$0")/.."
APP_DIR="$(pwd)"

echo "════════════════════════════════════════════════════════"
echo "  PolCRM - auto-setup"
echo "  Katalog: $APP_DIR"
echo "════════════════════════════════════════════════════════"
echo

# ─── 0. Sanity check ─────────────────────────────────────────
if [ "$(id -u)" -eq 0 ]; then
    err "Nie uruchamiaj jako root. Zaloguj sie jako uzytkownik aplikacji"
    err "(np. 'polcrm') i zostaw root-a tylko do 'sudo systemctl ...'."
    exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
    err "Brak python3. Zainstaluj: sudo apt install -y python3 python3-venv python3-pip"
    exit 1
fi

# Minimalne obrazy Ubuntu czasem nie maja python3-venv mimo python3
if ! python3 -c "import venv" 2>/dev/null; then
    warn "Brak python3-venv. Probuje doinstalowac przez sudo apt..."
    if sudo apt-get install -y python3-venv python3-pip curl >/dev/null 2>&1; then
        ok "Doinstalowano python3-venv"
    else
        err "Nie udalo sie. Uruchom recznie: sudo apt update && sudo apt install -y python3-venv python3-pip curl"
        exit 1
    fi
fi

if ! command -v curl >/dev/null 2>&1; then
    sudo apt-get install -y curl >/dev/null 2>&1 || {
        err "Brak curl. Zainstaluj: sudo apt install -y curl"
        exit 1
    }
fi

# ─── 1. Virtualenv + zaleznosci ──────────────────────────────
log "Krok 1/4: virtualenv + zaleznosci"

if [ ! -d "venv" ]; then
    python3 -m venv venv
    ok "Utworzono venv"
else
    ok "venv juz istnieje"
fi

# shellcheck disable=SC1091
source venv/bin/activate

pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
ok "Zaleznosci zainstalowane ($(pip list 2>/dev/null | wc -l) paczek)"

# ─── 2. .env z sekretami ────────────────────────────────────
log "Krok 2/4: konfiguracja .env"

if [ -f ".env" ]; then
    ok ".env juz istnieje - nie nadpisuje"
    NEW_ENV=false
else
    if [ ! -f ".env.example" ]; then
        err "Brak .env.example. Cos jest nie tak z paczka aplikacji."
        exit 1
    fi

    # Wygeneruj sekrety. WAZNE: nie uzywaj cut -d= bo Fernet key konczy sie na "="
    # i cut by je ucial. sed -n 's|prefix||p' jest bezpieczne.
    KEYS=$(python scripts/generate_keys.py)
    SECRET_KEY=$(echo "$KEYS" | sed -n 's|^FLASK_SECRET_KEY=||p' | head -1)
    FERNET_KEY=$(echo "$KEYS" | sed -n 's|^FERNET_KEY=||p' | head -1)

    if [ -z "$SECRET_KEY" ] || [ -z "$FERNET_KEY" ]; then
        err "Nie udalo sie wygenerowac kluczy. Sprawdz: python scripts/generate_keys.py"
        exit 1
    fi

    # Skopiuj template i wstrzyknij sekrety
    cp .env.example .env

    # Sed in-place - kompatybilnie z BSD/GNU
    if sed --version >/dev/null 2>&1; then
        SED_INPLACE=(sed -i)
    else
        SED_INPLACE=(sed -i '')
    fi

    "${SED_INPLACE[@]}" "s|^FLASK_SECRET_KEY=.*|FLASK_SECRET_KEY=$SECRET_KEY|" .env
    "${SED_INPLACE[@]}" "s|^FERNET_KEY=.*|FERNET_KEY=$FERNET_KEY|" .env

    chmod 600 .env
    ok "Stworzono .env z wygenerowanymi sekretami (chmod 600)"
    NEW_ENV=true
fi

# ─── 3. Systemd unit ────────────────────────────────────────
log "Krok 3/4: usluga systemd"

CURRENT_USER=$(whoami)
SERVICE_FILE="/etc/systemd/system/polcrm.service"

# Wygeneruj unit z aktualnym userem i pathem
TMP_UNIT=$(mktemp)
cat > "$TMP_UNIT" <<UNIT
[Unit]
Description=PolCRM (Flask + waitress)
After=network.target

[Service]
Type=simple
User=$CURRENT_USER
Group=$CURRENT_USER
WorkingDirectory=$APP_DIR
EnvironmentFile=$APP_DIR/.env
ExecStart=$APP_DIR/venv/bin/python app.py
Restart=on-failure
RestartSec=5

# Hardening
NoNewPrivileges=true
PrivateTmp=true
ProtectSystem=strict
ProtectHome=read-only
ReadWritePaths=$APP_DIR/instance $APP_DIR/output
ProtectKernelTunables=true
ProtectKernelModules=true
ProtectControlGroups=true
RestrictNamespaces=true
RestrictRealtime=true
LockPersonality=true

[Install]
WantedBy=multi-user.target
UNIT

if sudo cp "$TMP_UNIT" "$SERVICE_FILE"; then
    sudo systemctl daemon-reload
    ok "Zainstalowano $SERVICE_FILE (user=$CURRENT_USER, dir=$APP_DIR)"
else
    err "Nie udalo sie zainstalowac uslugi systemd"
    rm "$TMP_UNIT"
    exit 1
fi
rm "$TMP_UNIT"

# ─── 4. Cloudflared (instalacja paczki) ─────────────────────
log "Krok 4/4: cloudflared (sciagam paczke)"

if command -v cloudflared >/dev/null 2>&1; then
    ok "cloudflared juz zainstalowany ($(cloudflared --version 2>&1 | head -1))"
else
    if [ "$(uname -m)" = "x86_64" ]; then
        ARCH="amd64"
    elif [ "$(uname -m)" = "aarch64" ]; then
        ARCH="arm64"
    else
        warn "Nieznana architektura $(uname -m) - pobierz cloudflared recznie z github.com/cloudflare/cloudflared"
        ARCH=""
    fi

    if [ -n "$ARCH" ]; then
        TMP_DEB=$(mktemp --suffix=.deb)
        if curl -fsSL "https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-$ARCH.deb" -o "$TMP_DEB"; then
            sudo dpkg -i "$TMP_DEB" >/dev/null
            rm "$TMP_DEB"
            ok "cloudflared zainstalowany"
        else
            warn "Nie udalo sie pobrac cloudflared. Zainstaluj recznie."
            rm -f "$TMP_DEB"
        fi
    fi
fi

# ─── PODSUMOWANIE ───────────────────────────────────────────
echo
echo "════════════════════════════════════════════════════════"
echo "  GOTOWE - co dalej?"
echo "════════════════════════════════════════════════════════"
echo

if [ "$NEW_ENV" = "true" ]; then
    cat <<EOF
${YELLOW}1. UZUPELNIJ .env${NC}

   nano .env

   Ustaw:
     AUTH_MODE=password      (albo cloudflare - wtedy tez ALLOWED_EMAILS=...)
     APP_URL=https://crm.example.com
     OPENROUTER_API_KEY=...   (opcjonalne, dla asystenta AI)

EOF
fi

cat <<'EOF'
2. ZALOZ KONTO ADMINISTRATORA (haslo podasz w ukrytym polu)

   source venv/bin/activate
   python scripts/create_admin.py --name "Imie Nazwisko" --email adres@example.com

   (albo otworz /setup w przegladarce przy pierwszym wejsciu)
   Reszte zespolu dodasz w aplikacji: Ustawienia -> Zespol.

3. SKONFIGURUJ CLOUDFLARE (panel cloudflare.com → Zero Trust)
   a-c opcjonalnie (Access z logowaniem Google), d - Tunnel - zawsze:

   a) Zaloz konto Zero Trust (Free) → wybierz nazwe teamu
   b) Settings → Authentication → Login methods → Add → Google
      (postepuj wg instrukcji - utworzysz OAuth client w Google Cloud Console)
   c) Access → Applications → Add → Self-hosted
      - Domain: crm.example.com
      - Identity provider: Google
      - Policy: Allow → Emails → wpisz e-maile zespolu
   d) Networks → Tunnels → Create tunnel → Cloudflared
      - Cloudflare poda komende: 'sudo cloudflared service install eyJh...'
      - Wklej ja TUTAJ na serwerze
      - Public Hostname:
          Subdomain: crm
          Domain: example.com
          Service: HTTP, URL: localhost:4666

4. WYSTARTUJ APLIKACJE:

   sudo systemctl enable --now polcrm
   sudo systemctl status polcrm

   # Sprawdz czy slucha:
   ss -tlnp | grep 4666
   # Powinno byc: 127.0.0.1:4666 (NIE 0.0.0.0!)

   # Logi na zywo:
   sudo journalctl -u polcrm -f

5. TEST W PRZEGLADARCE:

   https://crm.example.com
   → ekran loginu Google
   → po zalogowaniu Twoim emailem → dashboard

   Z incognito (bez logowania) → 403 od Cloudflare = OK

EOF

echo "════════════════════════════════════════════════════════"
echo "  Pelna instrukcja: docs/DEPLOY.md"
echo "════════════════════════════════════════════════════════"
