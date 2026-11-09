# PolCRM - wdrożenie

Instrukcja krok po kroku: od czystego serwera do aplikacji dostępnej w internecie tylko dla Twojego zespołu.

Aplikacja ma własne logowanie (e-mail i hasło, role w zespole) i zawsze słucha lokalnie (`127.0.0.1:4666`). Do internetu wychodzi przez **Cloudflare Tunnel** (bez otwartych portów) albo reverse proxy z HTTPS. **Cloudflare Access** z logowaniem Google jest opcjonalną drugą warstwą (`AUTH_MODE=cloudflare` zamiast haseł albo Access przed logowaniem hasłem).

> **Najkrótsza ścieżka (Docker Compose + PostgreSQL)**
>
> 1. `cp .env.example .env`, sekrety z `python scripts/generate_keys.py`, ustaw `POSTGRES_PASSWORD`.
> 2. `docker compose up -d --build`.
> 3. Otwórz `http://127.0.0.1:4666/setup` i załóż konto administratora, potem zespół w Ustawienia → Zespół.
> 4. Wystaw aplikację przez Cloudflare Tunnel (sekcja „Cloudflare”) albo reverse proxy z HTTPS.
>
> **Linux VPS bez Dockera:** `./scripts/deploy_setup.sh` (venv, sekrety, systemd, cloudflared) - sekcja „Linux VPS”.

## Architektura

```
[Przeglądarka]
    ↓ HTTPS
[Cloudflare Edge]  ← opcjonalnie Access: logowanie Google, biała lista e-maili
    ↓
[Cloudflare Tunnel - cloudflared]  ← połączenie wychodzące z serwera
    ↓
[waitress na 127.0.0.1:4666]  ← logowanie hasłem i role (albo tożsamość z Access)
    ↓
[PolCRM - Flask + SQLite albo PostgreSQL]
```

Port 4666 **nigdy** nie jest otwarty na świat. `cloudflared` sam łączy się z Cloudflare, więc serwer nie potrzebuje publicznego portu HTTP ani przekierowań w routerze.

Trzy ścieżki do wyboru:

1. **Docker Compose** z PostgreSQL - najprostsza (sekcja „Docker Compose”).
2. **Linux VPS** z systemd i SQLite albo PostgreSQL (sekcja „Linux VPS”).
3. **Windows** (komputer albo Windows Server) - pliki `.bat` (sekcja „Windows”).

## Zabezpieczenia w kodzie

| Ryzyko | Rozwiązanie |
|---|---|
| Losowy `SECRET_KEY` przy każdym starcie | stały klucz z `.env`; bez niego produkcja nie wystartuje |
| Brak autoryzacji | logowanie hasłem (scrypt) z rolami admin/członek; opcjonalnie Cloudflare Access (`AUTH_MODE=cloudflare`) z `ALLOWED_EMAILS` |
| Zgadywanie haseł | limit nieudanych prób na konto i na IP, minimum 10 znaków, ten sam komunikat dla złego e-maila i hasła |
| Przejęta lub stara sesja | nowa sesja przy logowaniu, odcisk hasła w sesji (zmiana hasła wylogowuje), dezaktywacja działa od razu |
| Członek zespołu zmienia klucze API | ustawienia firmy, integracje i zespół tylko dla admina (sprawdzane na serwerze) |
| CSRF | Flask-WTF `CSRFProtect` + automatyczny token w formularzach i `fetch()` |
| Tryb debug na produkcji | `FLASK_ENV=production` uruchamia waitress, debug wyłączony |
| SSTI w szablonach e-maili | `SandboxedEnvironment` + `autoescape=True` |
| Sekrety w bazie jawnym tekstem | `EncryptedText` (Fernet): klucze API, hasło SMTP, client secret i tokeny OAuth, linki do sejfów |
| Klucz szyfrujący w bazie | `FERNET_KEY` w `.env`, poza bazą |
| Path traversal przy pobieraniu plików | `secure_filename` + kontrola katalogu |
| Podrobiony callback OAuth | parametr `state` porównywany przez `secrets.compare_digest` |
| Open redirect przez `Referer` | `_safe_referrer()` sprawdza host |
| Ciasteczka | HttpOnly, Secure (w produkcji), SameSite=Lax |
| Stored XSS w notatkach, komentarzach i bazie wiedzy | `bleach.clean()` po renderowaniu Markdown; podgląd w edytorze escapuje tekst i przyjmuje tylko linki http(s), mailto i względne |
| Dane w JavaScripcie i `innerHTML` | filtr `tojson` w szablonach, escapowanie nazw, wyników Google Places i nazw użytkowników |
| Ominięcie `ALLOWED_EMAILS` ciasteczkiem profilu | przy `AUTH_MODE=cloudflare` tożsamość pochodzi tylko z nagłówka Cloudflare Access |
| Wylogowanie linkiem z obcej strony | `/wyloguj` przyjmuje tylko POST z tokenem CSRF |
| Podmieniony plik biblioteki na CDN | Tailwind zbudowany lokalnie; hashe SRI (`integrity`) dla wszystkich plików z jsDelivr |
| Klucze API widoczne w HTML ustawień | pola sekretów są puste; puste pole przy zapisie zostawia zapisaną wartość |
| Rosnące kopie bazy | rotacja: 10 ostatnich kopii przy starcie |
| Dane testowe na produkcji | `seed_test_data.py` nie uruchomi się przy `FLASK_ENV=production` |

## Docker Compose (z PostgreSQL)

```bash
git clone https://github.com/boromat/polcrm.git && cd polcrm
cp .env.example .env
python3 scripts/generate_keys.py     # wklej FLASK_SECRET_KEY i FERNET_KEY do .env
nano .env                            # ustaw POSTGRES_PASSWORD (długie, losowe)
docker compose up -d --build
docker compose logs -f app           # "[PRODUKCJA] waitress na http://0.0.0.0:4666"
```

- Compose uruchamia PostgreSQL 16 (dane w wolumenie `pgdata`) i aplikację (pliki w wolumenach `instance` i `output`). Aplikacja w kontenerze działa jako zwykły użytkownik.
- Port jest wystawiony tylko na `127.0.0.1:4666` hosta. Pierwsze konto: `http://127.0.0.1:4666/setup` (z serwera przez tunel SSH: `ssh -L 4666:127.0.0.1:4666 serwer`).
- Kopie zapasowe: `docker compose exec db pg_dump -U polcrm polcrm > polcrm-$(date +%F).sql`.
- Aktualizacja: `git pull && docker compose up -d --build`.

## Linux VPS (zalecane bez Dockera)

Sprawdzone na Ubuntu 24.04, działa też na Debianie 12.

### 1. Serwer i aktualizacja systemu

Wystarczy najmniejszy VPS (1 vCPU, 1-2 GB RAM). Po utworzeniu masz adres IP i dostęp SSH.

```bash
ssh root@TWOJE_IP

apt update && apt upgrade -y
apt install -y python3 python3-pip python3-venv git curl ufw

# Firewall: tylko SSH (cloudflared nie potrzebuje otwartych portów)
ufw default deny incoming
ufw default allow outgoing
ufw allow OpenSSH
ufw enable
```

### 2. Użytkownik aplikacji (nie uruchamiaj jej jako root)

```bash
useradd -m -s /bin/bash polcrm
passwd polcrm

# Logowanie kluczem SSH
mkdir -p /home/polcrm/.ssh
cp ~/.ssh/authorized_keys /home/polcrm/.ssh/
chown -R polcrm:polcrm /home/polcrm/.ssh
chmod 700 /home/polcrm/.ssh
chmod 600 /home/polcrm/.ssh/authorized_keys

# Uprawnienia sudo potrzebne tylko do instalacji usługi
usermod -aG sudo polcrm
```

### 3. Kod na serwerze

```bash
ssh polcrm@TWOJE_IP
git clone https://github.com/boromat/polcrm.git
cd polcrm
```

Albo z własnego komputera: `scp -r polcrm polcrm@TWOJE_IP:~/`.

### 4. Automatyczna konfiguracja

```bash
chmod +x scripts/*.sh
./scripts/deploy_setup.sh
```

Skrypt:

1. tworzy `venv` i instaluje `requirements.txt`,
2. generuje `FLASK_SECRET_KEY` i `FERNET_KEY` i zapisuje je w nowym `.env` (`chmod 600`),
3. instaluje usługę systemd z bieżącym użytkownikiem i katalogiem,
4. pobiera i instaluje `cloudflared`,
5. wypisuje, co zostało do zrobienia ręcznie.

Potem uzupełnij `.env`:

```bash
nano .env
# ALLOWED_EMAILS=anna@example.com,tomasz@example.com
# APP_URL=https://crm.example.com
# OPENROUTER_API_KEY=...   (opcjonalnie, można też w Ustawieniach)
# OPENROUTER_URL=...       (opcjonalnie: inna bramka zgodna z OpenAI, np. LiteLLM albo lokalny model)
```

Opcjonalne maskowanie danych osobowych dla asystenta AI:

```bash
source venv/bin/activate
pip install polanon
```

<details>
<summary>Ten sam krok ręcznie (bez skryptu)</summary>

```bash
./scripts/install_requirements.sh
source venv/bin/activate
python scripts/generate_keys.py      # wypisze FLASK_SECRET_KEY i FERNET_KEY
cp .env.example .env && nano .env    # wklej sekrety, ustaw ALLOWED_EMAILS
chmod 600 .env
./scripts/start_prod.sh              # szybki test, Ctrl+C po "waitress na http://..."
sudo cp scripts/polcrm.service /etc/systemd/system/   # ścieżki w pliku zakładają /home/polcrm/polcrm
sudo systemctl daemon-reload
```

</details>

### 5. Pierwsze konto administratora i zespół

Przy `AUTH_MODE=password` (domyślnie) pierwsze wejście na aplikację prowadzi do `/setup`, która zakłada konto administratora i działa tylko do tego momentu. Na serwerze bez przeglądarki to samo zrobisz poleceniem (hasło podajesz w ukrytym polu, nie trafia do historii powłoki):

```bash
source venv/bin/activate
python scripts/create_admin.py --name "Anna Nowak" --email anna@example.com
```

Resztę zespołu admin dodaje w **Ustawienia → Zespół** (rola, hasło startowe; każdy zmienia je potem w swoim profilu). Ten sam skrypt przywraca dostęp, gdy ktoś zgubi hasło admina.

Przy `AUTH_MODE=cloudflare` haseł nie ma: pierwsza osoba z listy `ALLOWED_EMAILS`, która wejdzie przez Access, zostaje administratorem, a kolejne dostają konta członków.

### 6. Cloudflare

Skonfiguruj Tunnel (i opcjonalnie Access) według sekcji [Cloudflare](#cloudflare) poniżej. Komendę `sudo cloudflared service install <token>` z panelu uruchom na serwerze.

### 7. Start

```bash
sudo systemctl enable --now polcrm
sudo systemctl status polcrm

# Aplikacja ma słuchać tylko lokalnie: 127.0.0.1:4666 (nie 0.0.0.0)
ss -tlnp | grep 4666

# Logi na żywo
sudo journalctl -u polcrm -f
```

Usługa restartuje się po awarii i startuje razem z serwerem. Ma utwardzenie systemd (`ProtectSystem=strict`, `NoNewPrivileges`, zapis tylko do `instance/` i `output/`).

### 8. Test

- `https://crm.example.com` → ekran logowania PolCRM (z Cloudflare Access najpierw logowanie Google) → dashboard.
- Okno prywatne bez logowania → formularz logowania (z Access: 403 od Cloudflare); żadna strona aplikacji nie jest widoczna bez konta.
- `sudo systemctl status polcrm cloudflared` → oba `active (running)` (przy reverse proxy zamiast tunelu: `polcrm` i usługa proxy).

### 9. Aktualizacje

```bash
cd ~/polcrm
git pull
source venv/bin/activate
pip install -r requirements.txt
sudo systemctl restart polcrm
```

Na SQLite aplikacja przy starcie robi kopię bazy i sama dodaje nowe kolumny (bez ręcznych migracji). Na PostgreSQL zrób przed aktualizacją `pg_dump`; wersja 1.0 nie ma jeszcze migracji schematu dla PostgreSQL (zob. „Znane ograniczenia” w README).

## Cloudflare

Tunnel to zalecany sposób wystawienia aplikacji, bo nie wymaga otwartych portów; zamiast niego może to robić reverse proxy z HTTPS. Aplikacja Access z logowaniem Google jest opcjonalna przy `AUTH_MODE=password` (dodatkowa warstwa przed formularzem logowania) i wymagana przy `AUTH_MODE=cloudflare` (wtedy jedyną drogą do aplikacji musi być tunel).

### Domena

1. Zaloguj się na <https://dash.cloudflare.com>, **Add site**, plan **Free**.
2. Ustaw u rejestratora domeny dwa nameservery, które poda Cloudflare. Propagacja trwa zwykle 5-30 minut.

### Zero Trust i logowanie Google

1. **Zero Trust** (menu po lewej) → wybierz nazwę zespołu, plan **Free**.
2. **Settings → Authentication → Login methods → Add new → Google**.
3. W [Google Cloud Console](https://console.cloud.google.com) utwórz OAuth Client ID (typ: Web application) z adresem przekierowania, który poda Cloudflare (`https://<zespół>.cloudflareaccess.com/cdn-cgi/access/callback`).
4. Wklej Client ID i Client secret do Cloudflare, **Save**, sprawdź przyciskiem **Test**.

### Aplikacja Access

1. **Access → Applications → Add an application → Self-hosted**.
2. Nazwa: `PolCRM`, czas sesji np. 24 h, domena: `crm.example.com`.
3. Dostawca tożsamości: **Google**.
4. Polityka: **Allow → Include → Emails** → e-maile osób z zespołu (przy `AUTH_MODE=cloudflare` te same co w `ALLOWED_EMAILS`).

### Tunnel

1. **Networks → Tunnels → Create a tunnel → Cloudflared**, nazwa np. `polcrm-tunnel`.
2. Uruchom na serwerze komendę instalacyjną z panelu (`cloudflared service install <token>`).
3. **Public Hostname → Add**: subdomena `crm`, domena `example.com`, typ `HTTP`, URL `localhost:4666`.
4. Status tunelu powinien być **Healthy**.

### Weryfikacja JWT (zalecana przy innym sposobie wystawienia)

Cloudflare Access dodaje też podpisany nagłówek `Cf-Access-Jwt-Assertion`. PolCRM ufa nagłówkowi `Cf-Access-Authenticated-User-Email`, co jest bezpieczne, dopóki aplikacja słucha **tylko na 127.0.0.1**, a jedyną drogą do niej jest `cloudflared`. Jeśli wystawisz ją w sieci lokalnej albo przez inne proxy, dodaj weryfikację JWT (np. `PyJWT` i klucze z `https://<zespół>.cloudflareaccess.com/cdn-cgi/access/certs`).

## Windows

1. `scripts\install_requirements.bat` - tworzy `.venv` i instaluje zależności.
2. `.venv\Scripts\python.exe scripts\generate_keys.py` → skopiuj `.env.example` jako `.env` i wklej klucze, ustaw `FLASK_ENV=production` i tryb logowania: `AUTH_MODE=password` (domyślnie) albo `AUTH_MODE=cloudflare` z `ALLOWED_EMAILS`.
3. Pierwsze konto administratora: `.venv\Scripts\python.exe scripts\create_admin.py` albo strona `/setup` po pierwszym uruchomieniu.
4. `scripts\start_prod.bat` - waitress na `127.0.0.1:4666`.
5. Cloudflare jak wyżej; `cloudflared` dla Windows to plik `cloudflared-windows-amd64.msi` z <https://github.com/cloudflare/cloudflared/releases>, komendę instalacyjną z panelu uruchom w PowerShellu jako administrator.
6. Opcjonalnie usługa Windows przez [NSSM](https://nssm.cc): `nssm install PolCRM "C:\polcrm\scripts\start_prod.bat"`.

## Utrzymanie

- **Kopie zapasowe:** na SQLite `instance/backup_*.db` powstają przy każdym starcie (10 ostatnich); dodatkowo kopiuj regularnie `instance/hub.db` poza serwer (np. `rsync` albo timer systemd). Na PostgreSQL rób `pg_dump` (np. z timera systemd) i też trzymaj kopie poza serwerem. W obu przypadkach kopiuj `output/` (umowy, załączniki) i trzymaj `FERNET_KEY` osobno: bez niego zaszyfrowanych sekretów z kopii nie odczytasz.
- **Logi:** waitress pisze na stdout, w systemd: `journalctl -u polcrm`.
- **Podatności w zależnościach:** `pip install pip-audit && pip-audit -r requirements.txt`.

### Gdy coś pójdzie nie tak

- **Zgubiony `FERNET_KEY`** - zapisanych w bazie kluczy API, hasła SMTP i tokenów OAuth nie da się odszyfrować. Wygeneruj nowy klucz i wpisz te dane ponownie w Ustawieniach.
- **Zgubiony `FLASK_SECRET_KEY`** - wszyscy zostaną wylogowani, dane w bazie są bezpieczne. Wygeneruj nowy, wklej do `.env`, zrestartuj usługę.
- **403 od PolCRM** („Brak autoryzacji Cloudflare Access”) - e-mail z Cloudflare nie jest na liście `ALLOWED_EMAILS`.
- **403 od Cloudflare** - e-mail nie jest w polityce aplikacji Access.

## Czego nie załatwia Cloudflare

- **Content Security Policy** - aplikacja nie wysyła nagłówka CSP; można go dodać w `@app.after_request`.
- **Przejęcie serwera** - kto ma serwer i `.env`, ma też klucz Fernet, a więc i sekrety z bazy. Wyższy poziom ochrony wymagałby zewnętrznego sejfu na sekrety.
- **Weryfikacja JWT** - zob. wyżej; wymagana, jeśli aplikacja ma być dostępna inną drogą niż tunel.

## Lista kontrolna przed pierwszym uruchomieniem

- [ ] `FLASK_SECRET_KEY` i `FERNET_KEY` w `.env`, plik ma `chmod 600`
- [ ] `.env` nie trafił do żadnego repozytorium (jest w `.gitignore`)
- [ ] Konto administratora założone (`/setup` albo `scripts/create_admin.py`), `/setup` zwraca już 404
- [ ] `ss -tlnp | grep 4666` pokazuje `127.0.0.1`, nie `0.0.0.0` (w Dockerze: port opublikowany na 127.0.0.1)
- [ ] Tunnel ma status **Healthy**, `SESSION_COOKIE_SECURE=true` za HTTPS
- [ ] `https://crm.example.com` → logowanie → dashboard; okno prywatne bez logowania nie widzi danych
- [ ] Przy Cloudflare Access: `ALLOWED_EMAILS` zgadza się z polityką aplikacji w Access
