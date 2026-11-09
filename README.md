# PolCRM

**Polski** · [English](README.en.md)

[![CI](https://github.com/boromat/polcrm/actions/workflows/ci.yml/badge.svg)](https://github.com/boromat/polcrm/actions/workflows/ci.yml)
[![Licencja: MIT](https://img.shields.io/badge/licencja-MIT-blue.svg)](LICENSE)

**Self-hosted CRM, lejek sprzedaży i finanse dla małej agencji WWW/SEO, po polsku i po angielsku.** Jedna aplikacja zamiast arkuszy i kilku narzędzi: leady z Google Maps, audyt strony z oceną PageSpeed, pipeline, zadania, umowy i raporty w PDF, płatności i abonamenty, zespół z rolami, a do tego asystent AI, który przez tool calling czyta i zmienia dane w CRM. Dane osobowe klientów mogą być maskowane przez [polanon](https://github.com/boromat/polanon), zanim cokolwiek trafi do modelu.

![PolCRM: logowanie, dashboard zespołu, lista firm, karta klienta, pipeline, zadania, raport z audytu, tablica, finanse, zespół z rolami, ustawienia maskowania danych osobowych i asystent AI odpowiadający na pytanie o zaległe płatności](docs/demo.gif)

<sub>Demo na fikcyjnych danych ze `scripts/seed_test_data.py`: firmy z prefiksem [TEST], osoby i adresy nie istnieją. Wersja angielska interfejsu: [README.en.md](README.en.md). W scenie z asystentem model to lokalna atrapa podpięta przez `OPENROUTER_URL` (bez klucza API), a maskowanie robi prawdziwy polanon: atrapa dostała tylko `<FIRMA_1>`, a nazwę klienta w odpowiedzi odtworzyła aplikacja.</sub>

## Funkcje

**Sprzedaż i klienci**

- **Leady z Google Maps** - wyszukiwanie firm przez Google Places po frazach i lokalizacji, eksport do CSV, dodawanie do CRM jednym kliknięciem.
- **Audyt strony** - automatyczna ocena w 5 obszarach (widoczność, oferta, zaufanie, konwersja, analityka) na podstawie danych z Google i Google PageSpeed Insights, porównanie z konkurencją, raport PDF dla klienta.
- **Pipeline** - tablica kanban od leada do klienta (przeciąganie kart), następna akcja i termin przy każdej firmie.
- **Karta klienta** - kontakt, historia, notatki, pliki z wersjami, dostępy (tylko linki do menedżera haseł, bez haseł w bazie), projekty, płatności, analityka GSC/GA4.
- **Kalendarz wizyt** i scenariusz rozmowy sprzedażowej.
- **Oferty i pakiety usług**, szablony e-maili z wysyłką przez SMTP i historią.
- **Umowy** - szablony z polami klienta, generowanie PDF z polskimi znakami.

**Realizacja i zespół**

- **Zespół dowolnej wielkości z rolami** - administrator zarządza zespołem, kluczami API i integracjami, członek pracuje na danych. Konta, role, dezaktywacja i reset hasła w Ustawienia → Zespół.
- **Zadania** - lista, kanban, podzadania, komentarze z @wzmiankami i skrzynką powiadomień, „Dziś”, „Po terminie”, „Ten tydzień”, puls zespołu na dashboardzie.
- **Projekty WWW**, **plan contentu** z kalendarzem publikacji, **tablica** do szkiców (rysowanie, tekst, obrazy).
- **Notatnik** i **baza wiedzy / SOP**, wyszukiwarka globalna (Ctrl+K), dziennik aktywności.

**Finanse**

- Płatności (z VAT), koszty, subskrypcje, bilans miesięczny, MRR, zaległości.
- Generowanie płatności abonamentowych dla klientów na retainerze (stawka VAT z Ustawień, także 0% dla zwolnionych), raport wewnętrzny z podziałem kosztów stałych na klientów.

**Polski i angielski**

- Cały interfejs, komunikaty, raporty PDF z audytu i odpowiedzi asystenta w języku wybranym w profilu. Przełącznik PL/EN w górnym pasku i na stronie logowania.
- Dokumenty dla klientów (umowy, tytuły płatności abonamentowych) w języku instalacji (`DEFAULT_LANGUAGE`), a treść umowy pochodzi z jej szablonu. Dane wpisane przez zespół zostają w języku, w którym je wpisano.
- Domyślne szablony e-maili, umów i artykuły bazy wiedzy po angielsku, gdy instalacja startuje z `DEFAULT_LANGUAGE=en`.

**Asystent AI z tool calling**

Okno czatu w aplikacji. Model (przez OpenRouter, do wyboru np. Gemini Flash, Claude Haiku, GPT-4o mini, albo dowolny endpoint zgodny z OpenAI ustawiony w `OPENROUTER_URL`, także lokalny) dostaje 12 narzędzi działających na prawdziwej bazie i sam decyduje, które wywołać, w pętli do 6 kroków:

| Obszar | Narzędzia |
|---|---|
| Zadania | `list_tasks`, `create_task`, `move_task` |
| CRM | `list_companies`, `get_company`, `update_pipeline_stage` |
| Finanse | `get_finances_summary`, `list_overdue_payments`, `create_payment` |
| Inne | `add_note`, `search_global`, `list_calendar` |

Przykład: „znajdź klientów z zaległymi fakturami i dodaj każdemu zadanie follow-up na piątek” to kilka wywołań narzędzi wykonanych po kolei. Asystent nie ma narzędzi do usuwania danych.

## Ochrona danych osobowych (polanon) - opcjonalnie

[polanon](https://github.com/boromat/polanon) to moja biblioteka Pythona (`pip install polanon`) do odwracalnego maskowania polskich danych osobowych przed wysłaniem tekstu do modelu językowego. W PolCRM włącza się ją w **Ustawienia → AI Asystent**.

W asystencie z tool calling dane osobowe są nie tylko w pytaniu użytkownika, ale też w wynikach narzędzi (nazwy firm, osoby kontaktowe, e-maile, telefony). Dlatego maskowanie obejmuje cały obieg:

1. pytanie, historia rozmowy i **wyniki narzędzi** są maskowane: `Jan Kowalski` → `<OSOBA_1>`, `kontakt@...` → `<EMAIL_1>`; nazwy firm z bazy klientów są maskowane zawsze (`<FIRMA_1>`), bo w krótkim polu wyniku narzędzia, bez kontekstu zdania, reguły polanonu nie rozpoznałyby np. „Auto Serwis Nowak”,
2. model widzi tylko tokeny i może przekazać je do narzędzia, np. `add_note(content="Oddzwonić do <OSOBA_1>")`,
3. zanim narzędzie dotknie bazy, **argumenty są odtwarzane** do prawdziwych wartości,
4. w odpowiedzi dla użytkownika tokeny wracają do prawdziwych wartości.

Mapowanie token → wartość istnieje tylko w pamięci, na czas jednego zapytania. Bez zainstalowanego polanonu i z wyłączonym maskowaniem asystent działa tak jak wcześniej. Gdy maskowanie jest **włączone**, a polanon nie działa, aplikacja **nic nie wysyła** do modelu i zwraca błąd. To pseudonimizacja, nie pełna anonimizacja: dokładniej działa z modelem spaCy (`pip install "polanon[ner]"` i `python -m spacy download pl_core_news_md`).

Kod: [`privacy.py`](privacy.py), pętla asystenta: [`ai_assistant.py`](ai_assistant.py), testy: [`tests/test_privacy.py`](tests/test_privacy.py), [`tests/test_polanon_real.py`](tests/test_polanon_real.py). Ten sam wzorzec stosuje [PolCV](https://github.com/boromat/polcv).

## Gdzie zajrzeć w kodzie

Jeśli masz 10 minut, te miejsca najlepiej pokazują, jak projekt jest zbudowany:

1. [`ai_assistant.py`](ai_assistant.py) - definicje 12 narzędzi (JSON Schema) i pętla tool calling w `run_conversation`, z wstrzykiwanym modelem, żeby dało się ją testować bez API.
2. [`privacy.py`](privacy.py) - maskowanie danych osobowych: jedna mapa tokenów na zapytanie, maskowanie wyników narzędzi, odtwarzanie argumentów, zasada „fail closed”.
3. [`auth.py`](auth.py) i [`routes/auth.py`](routes/auth.py) - tryby logowania, limit prób, sesja powiązana z hasłem, pierwsze uruchomienie.
4. [`i18n.py`](i18n.py) - dwujęzyczny interfejs bez dodatkowych zależności; [`scripts/i18n_check.py`](scripts/i18n_check.py) wyszukuje polskie resztki w wersji angielskiej.
5. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - diagram wdrożenia, moduły i sekwencja zapytania z maskowaniem.

## Stack

- **Backend:** Python 3.12+, Flask 3, SQLAlchemy 2 (SQLite albo PostgreSQL), waitress
- **Frontend:** szablony Jinja2, Tailwind budowany lokalnie (`tailwind.config.js`) + własny CSS (dwa motywy), JavaScript bez frameworka, PWA (manifest + service worker)
- **AI:** OpenRouter (API zgodne z OpenAI, tool calling), opcjonalnie polanon
- **Google:** Places API, PageSpeed Insights, Search Console i GA4 (OAuth 2.0)
- **PDF:** fpdf2 z fontem DejaVu (polskie znaki)
- **Bezpieczeństwo:** hasła scrypt, Flask-WTF (CSRF), Fernet (sekrety w bazie), SRI dla bibliotek z CDN, opcjonalnie Cloudflare Tunnel + Access
- **Uruchomienie:** Docker + docker-compose (z PostgreSQL) albo systemd / Windows
- **Testy:** pytest na SQLite i PostgreSQL, GitHub Actions (Linux i Windows)

## Uruchomienie lokalnie

Wymagany Python 3.12 lub nowszy.

**Windows**

```bat
scripts\install_requirements.bat
.venv\Scripts\python.exe scripts\seed_test_data.py
scripts\start.bat
```

**Linux / macOS**

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_test_data.py
FLASK_ENV=development python app.py
```

Aplikacja działa pod <http://127.0.0.1:4666>. Dane testowe zakładają trzy konta demo: `anna@example.com` (administrator), `tomasz@example.com` i `ola@example.com` (członkowie), wszystkie z hasłem `demo-polcrm`. Bez danych testowych pierwsze wejście prowadzi do strony `/setup`, która zakłada konto administratora. Dane testowe usuniesz poleceniem `python scripts/seed_test_data.py --clean`.

Do pełnego działania potrzebne są klucze, które admin wpisuje w **Ustawieniach** (aplikacja działa też bez nich):

- **Google Maps API** - wyszukiwanie leadów, audyty, PageSpeed,
- **OpenRouter** - asystent AI (<https://openrouter.ai/settings/keys>),
- **SMTP** - wysyłka e-maili,
- **Google OAuth** - Search Console i GA4.

Opcjonalne maskowanie: `pip install polanon`, potem **Ustawienia → AI Asystent → Maskuj dane osobowe**.

## Docker (z PostgreSQL)

```bash
cp .env.example .env    # uzupełnij FLASK_SECRET_KEY, FERNET_KEY i POSTGRES_PASSWORD
docker compose up -d --build
```

Compose uruchamia aplikację i PostgreSQL 16; aplikacja słucha tylko na `127.0.0.1:4666`. Pierwsze wejście prowadzi do `/setup`. Do internetu wystaw ją przez Cloudflare Tunnel albo reverse proxy z HTTPS ([docs/DEPLOY.md](docs/DEPLOY.md)).

## Konfiguracja

Plik `.env` (wzór: [`.env.example`](.env.example)). Sekrety wygenerujesz poleceniem `python scripts/generate_keys.py`.

| Zmienna | Opis |
|---|---|
| `FLASK_SECRET_KEY` | podpis sesji i tokenów CSRF; w produkcji wymagany |
| `FERNET_KEY` | szyfrowanie kluczy API, hasła SMTP i tokenów Google w bazie; w produkcji wymagany |
| `FLASK_ENV` | `development` (serwer Flask z debugiem) albo `production` (waitress) |
| `AUTH_MODE` | `password` (domyślnie), `cloudflare` (tożsamość z Cloudflare Access) albo `profile` (demo bez haseł, zablokowany w produkcji) |
| `ALLOWED_EMAILS` | dla `cloudflare`: dodatkowa biała lista e-maili po stronie aplikacji |
| `DEFAULT_LANGUAGE` | `pl` albo `en`: język przed zalogowaniem i domyślnych szablonów przy pierwszym starcie |
| `DATABASE_URL` | domyślnie SQLite w `instance/hub.db`; PostgreSQL: `postgresql+psycopg://...` |
| `POSTGRES_PASSWORD` | hasło bazy dla `docker-compose.yml` |
| `APP_HOST`, `APP_PORT` | domyślnie `127.0.0.1:4666` |
| `SESSION_COOKIE_SECURE` | `true` za HTTPS |
| `OPENROUTER_API_KEY`, `ASSISTANT_MODEL` | alternatywa dla ustawień asystenta w UI |
| `OPENROUTER_URL` | inny endpoint zgodny z OpenAI (np. LiteLLM albo lokalny model) zamiast OpenRouter |

## Wdrożenie

Trzy sprawdzone drogi: **Docker Compose** z PostgreSQL, **VPS z systemd** (gotowy skrypt `scripts/deploy_setup.sh` i usługa `scripts/polcrm.service`) albo **Windows** (`scripts\start_prod.bat`). Aplikacja zawsze słucha lokalnie, a do internetu wychodzi przez Cloudflare Tunnel (opcjonalnie z Cloudflare Access) albo reverse proxy z HTTPS. Instrukcja krok po kroku: [docs/DEPLOY.md](docs/DEPLOY.md).

## Bezpieczeństwo

- **Logowanie:** hasła hashowane scrypt, limit nieudanych prób (na konto i na adres IP), nowa sesja przy logowaniu, sesja powiązana z hasłem (zmiana hasła wylogowuje pozostałe sesje), dezaktywacja konta działa natychmiast. Strona `/setup` działa tylko, dopóki nie ma żadnego administratora.
- **Role:** zmiany ustawień firmy, kluczy API, integracji i zespołu tylko dla administratora (sprawdzane po stronie serwera); ostatniego administratora nie da się zdegradować ani wyłączyć.
- **Cloudflare Access (opcjonalnie):** przy `AUTH_MODE=cloudflare` tożsamość pochodzi wyłącznie z nagłówka `Cf-Access-Authenticated-User-Email`, sprawdzanego dodatkowo z `ALLOWED_EMAILS`.
- CSRF w każdym formularzu i zapytaniu `fetch()` (Flask-WTF), wylogowanie tylko przez POST, szablony e-maili renderowane w sandboxie Jinja2 (ochrona przed SSTI), sanityzacja Markdown (bleach), escapowanie danych w JavaScripcie, bezpieczne nazwy plików i kontrola ścieżek przy pobieraniu.
- Tailwind zbudowany lokalnie, a biblioteki z jsDelivr przypięte do wersji z hashami SRI (`integrity`).
- Klucze API (Google Maps, OpenRouter), hasło SMTP, client secret i tokeny OAuth są zapisane w bazie zaszyfrowane Fernetem; klucz szyfrujący jest poza bazą (`FERNET_KEY`). Dostępy klientów to tylko linki do menedżera haseł.
- Opcjonalne maskowanie danych osobowych przed wysłaniem do AI (polanon), z zasadą „błąd zamiast wysyłki jawnym tekstem”.

Zgłaszanie problemów: [SECURITY.md](SECURITY.md).

## Testy

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .      # lint: reguły pyflakes
# ten sam zestaw na PostgreSQL:
TEST_DATABASE_URL=postgresql+psycopg://user:haslo@127.0.0.1:5432/polcrm_test python -m pytest
```

Testy obejmują:
- maskowanie w pętli asystenta (atrapa i prawdziwy polanon),
- endpoint asystenta od zapytania HTTP do zapisu w bazie,
- logowanie, limity prób, role, zespół i pierwsze uruchomienie,
- tłumaczenia: kompletność katalogu i brak polskich tekstów w wersji angielskiej na każdej stronie,
- szyfrowanie kluczy w bazie i tryb Cloudflare Access,
- umowy z PDF, pliki z wersjami, tablice,
- audyty: formularz, raport HTML i PDF w obu językach,
- usuwanie firmy i tablicy razem z powiązanymi danymi (ważne na PostgreSQL, który pilnuje kluczy obcych),
- logikę finansów i oceny audytu oraz główne formularze,
- przejście po każdej trasie GET bez błędu serwera i bez dostępu do sieci.

Razem 114 testów, ten sam zestaw na SQLite i PostgreSQL 16. CI uruchamia je na Linuksie (Python 3.12 i 3.13) i Windowsie, osobno na PostgreSQL 16, buduje obraz Dockera i sprawdza, czy zbudowany Tailwind jest aktualny.

Po zmianie klas Tailwinda w szablonach przebuduj CSS (Node.js potrzebny tylko do tego kroku):

```bash
npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.input.css -o static/css/tailwind.css --minify
```

## Struktura projektu

```
app.py               punkt wejścia: aplikacja z core.py + trasy z routes/
core.py              konfiguracja, logowanie i role, hooki, wspólne helpery
routes/              trasy według obszarów (firmy, zadania, finanse, zespół, asystent...)
auth.py              tryby logowania, polityka haseł, limit prób
i18n.py              język interfejsu (pl/en); tłumaczenia w translations/en/*.json
models.py            modele SQLAlchemy + migracje kolumn starszych baz SQLite + indeksy
ai_assistant.py      asystent AI: 12 narzędzi, pętla tool calling, OpenRouter
privacy.py           opcjonalne maskowanie danych osobowych (polanon)
scoring.py           ocena audytu (5 obszarów) + Google PageSpeed Insights
google_sync.py       OAuth 2.0 + Search Console + GA4
finance_helpers.py   bilans, MRR, zaległości, płatności abonamentowe
email_sender.py      SMTP + szablony e-maili w sandboxie Jinja2
crypto_utils.py      Fernet + typ kolumny EncryptedText
contract_pdf.py      PDF umów
pdf_report.py        PDF raportów z audytu
templates/           widoki Jinja2 według modułów
static/              CSS (w tym zbudowany Tailwind), JS (UI, asystent, edytor Markdown), PWA
scripts/             start, instalacja, admin, klucze, dane testowe, kontrola tłumaczeń, deploy
tests/               pytest
docs/                DEPLOY.md, ARCHITECTURE.md, demo.gif (PL), demo-en.gif (EN)
Dockerfile, docker-compose.yml   obraz produkcyjny i zestaw z PostgreSQL
```

Więcej o budowie aplikacji i przepływie danych w asystencie (po angielsku): [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Zmiany: [CHANGELOG.md](CHANGELOG.md).

## Znane ograniczenia

- **Brak użytkowników produkcyjnych.** Aplikacja nie była używana na co dzień, więc nie przeszła testu prawdziwej pracy.
- **Integracje bez weryfikacji na żywo.** SMTP i Google Search Console / GA4 nie były skonfigurowane z prawdziwymi kontami; testy sprawdzają je bez połączenia z siecią.
- **Migracje schematu:** starsze bazy SQLite dostają brakujące kolumny automatycznie przy starcie; PostgreSQL startuje od pełnego schematu wersji 1.0, a kolejne zmiany schematu będą wymagały migracji (np. Alembic).
- **Opisy narzędzi asystenta** dla modelu są po polsku; odpowiedź przychodzi w języku użytkownika.
- **Odzyskiwanie hasła** robi administrator (nowe hasło w Ustawienia → Zespół) albo `scripts/create_admin.py`; nie ma resetu przez e-mail.

## Licencja

[MIT](LICENSE) © 2026 BoroMat
