# PolCRM

[Polski](README.md) · **English**

[![CI](https://github.com/boromat/polcrm/actions/workflows/ci.yml/badge.svg)](https://github.com/boromat/polcrm/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

**Self-hosted CRM, sales pipeline and finances for a small web/SEO agency, in Polish and English.** One app instead of spreadsheets and a handful of tools: leads from Google Maps, website audits with PageSpeed scoring, a pipeline, tasks, PDF contracts and audit reports, payments and retainers, a team with roles, plus an AI assistant that reads and updates CRM data through tool calling. Clients' personal data can be masked with [polanon](https://github.com/boromat/polanon) before anything reaches the model.

![PolCRM in English: login, team dashboard, company list, client card, pipeline, tasks, audit report, whiteboard, finances, team with roles, personal data masking settings and the AI assistant answering a question about overdue payments](docs/demo-en.gif)

<sub>Demo on fictional data from `scripts/seed_test_data.py`: companies prefixed with [TEST], people and addresses do not exist. The interface is in English; the sample data describes a Polish agency, so it stays in Polish (data is never translated). In the assistant scene the model is a local stand-in connected through `OPENROUTER_URL` (no API key) while masking is done by the real polanon: the stand-in received only `<FIRMA_1>`, and the app restored the client name in the answer.</sub>

## Features

**Sales and clients**

- **Leads from Google Maps** - search businesses with Google Places by keyword and location, export to CSV, add to the CRM in one click.
- **Website audit** - automatic score in 5 areas (visibility, offer, trust, conversion, analytics) from Google data and Google PageSpeed Insights, comparison with competitors, a PDF report for the client.
- **Pipeline** - a drag-and-drop kanban from lead to client, with the next action and its date on every company.
- **Client card** - contact, history, notes, versioned files, access links (links to a password manager only, no passwords in the database), projects, payments, GSC/GA4 analytics.
- **Visit calendar** and a sales call script.
- **Offers and service packages**, e-mail templates sent over SMTP with a sent log.
- **Contracts** - templates with client fields, PDF generation with Polish characters.

**Delivery and team**

- **A team of any size, with roles** - administrators manage the team, API keys and integrations, members work on the data. Accounts, roles, deactivation and password resets in Settings → Team.
- **Tasks** - list, kanban, subtasks, comments with @mentions and an inbox, "Today", "Overdue", "This week", the team pulse on the dashboard.
- **Web projects**, a **content plan** with a publishing calendar, a **whiteboard** for sketches (drawing, text, images).
- **Notebook** and a **knowledge base / SOPs**, global search (Ctrl+K), activity log.

**Finances**

- Payments (with VAT), expenses, subscriptions, monthly balance, MRR, overdue invoices.
- Retainer payment generation (VAT rate from Settings, including 0% for VAT-exempt agencies) and an internal report that splits fixed costs across clients.

**Polish and English**

- The whole interface, messages, audit PDF reports and the assistant's answers follow the language chosen in the profile. A PL/EN switch in the top bar and on the login page.
- Documents for clients (contracts, retainer payment titles) use the installation language (`DEFAULT_LANGUAGE`), and a contract's text comes from its template. Data entered by the team stays in the language it was written in.
- Default e-mail and contract templates and knowledge base articles in English when an installation starts with `DEFAULT_LANGUAGE=en`.

**AI assistant with tool calling**

A chat window inside the app. The model (via OpenRouter: Gemini Flash, Claude Haiku, GPT-4o mini and others, or any OpenAI-compatible endpoint set in `OPENROUTER_URL`, including a local one) gets 12 tools that work on the real database and decides which to call, in a loop of up to 6 steps:

| Area | Tools |
|---|---|
| Tasks | `list_tasks`, `create_task`, `move_task` |
| CRM | `list_companies`, `get_company`, `update_pipeline_stage` |
| Finances | `get_finances_summary`, `list_overdue_payments`, `create_payment` |
| Other | `add_note`, `search_global`, `list_calendar` |

Example: "find clients with overdue invoices and add a follow-up task for each on Friday" becomes several tool calls run in sequence. The assistant has no tools that delete data.

## Personal data protection (polanon) - optional

[polanon](https://github.com/boromat/polanon) is my Python library (`pip install polanon`) for reversible masking of Polish personal data before text is sent to a language model. In PolCRM it is switched on in **Settings → AI Assistant**.

With tool calling, personal data is not only in the user's question but also in tool results (company names, contact people, e-mails, phone numbers). So masking covers the whole round trip:

1. the question, the conversation history and **tool results** are masked: `Jan Kowalski` → `<OSOBA_1>`, `contact@...` → `<EMAIL_1>`; client company names from the CRM are always masked (`<FIRMA_1>`), because in a short tool-result field, without a sentence around it, polanon's rules would not recognize e.g. "Auto Serwis Nowak",
2. the model only sees tokens and may pass them to a tool, e.g. `add_note(content="Call back <OSOBA_1>")`,
3. before the tool touches the database, **its arguments are restored** to the real values,
4. tokens in the answer are restored before the user sees it.

The token → value mapping lives only in memory, for one request. Without polanon installed and with masking off, the assistant works as before. When masking is **on** and polanon fails, the app **sends nothing** to the model and returns an error. This is pseudonymisation, not full anonymisation; detection is better with the spaCy model (`pip install "polanon[ner]"` and `python -m spacy download pl_core_news_md`).

Code: [`privacy.py`](privacy.py), the assistant loop: [`ai_assistant.py`](ai_assistant.py), tests: [`tests/test_privacy.py`](tests/test_privacy.py), [`tests/test_polanon_real.py`](tests/test_polanon_real.py). [PolCV](https://github.com/boromat/polcv) uses the same pattern.

## Where to look in the code

If you have 10 minutes, these show best how the project is built:

1. [`ai_assistant.py`](ai_assistant.py) - the 12 tool definitions (JSON Schema) and the tool-calling loop in `run_conversation`, with an injectable model call so it can be tested without the API.
2. [`privacy.py`](privacy.py) - PII masking: one token mapping per request, masked tool results, restored arguments, the fail-closed rule.
3. [`auth.py`](auth.py) and [`routes/auth.py`](routes/auth.py) - login modes, rate limiting, sessions bound to the password, first-run setup.
4. [`i18n.py`](i18n.py) - a bilingual interface without extra dependencies; [`scripts/i18n_check.py`](scripts/i18n_check.py) finds Polish left in the English UI.
5. [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) - deployment diagram, modules and the sequence of a masked request.

## Stack

- **Backend:** Python 3.12+, Flask 3, SQLAlchemy 2 (SQLite or PostgreSQL), waitress
- **Frontend:** Jinja2 templates, Tailwind built locally (`tailwind.config.js`) + custom CSS (two themes), framework-free JavaScript, PWA (manifest + service worker)
- **AI:** OpenRouter (OpenAI-compatible API, tool calling), optional polanon
- **Google:** Places API, PageSpeed Insights, Search Console and GA4 (OAuth 2.0)
- **PDF:** fpdf2 with the DejaVu font (Polish characters)
- **Security:** scrypt password hashes, Flask-WTF (CSRF), Fernet (secrets at rest), SRI for CDN libraries, optional Cloudflare Tunnel + Access
- **Running:** Docker + docker-compose (with PostgreSQL), or systemd / Windows
- **Tests:** pytest on SQLite and PostgreSQL, GitHub Actions (Linux and Windows)

## Running locally

Python 3.12 or newer is required.

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

Open <http://127.0.0.1:4666>. The test data creates three demo accounts: `anna@example.com` (administrator), `tomasz@example.com` and `ola@example.com` (members), all with the password `demo-polcrm`. Without test data, the first visit leads to `/setup`, which creates the administrator account. Remove the test data with `python scripts/seed_test_data.py --clean`.

For everything to work you need keys, entered by an administrator in **Settings** (the app runs without them too):

- **Google Maps API** - lead search, audits, PageSpeed,
- **OpenRouter** - the AI assistant (<https://openrouter.ai/settings/keys>),
- **SMTP** - sending e-mails,
- **Google OAuth** - Search Console and GA4.

Optional masking: `pip install polanon`, then **Settings → AI Assistant → Mask personal data**.

## Docker (with PostgreSQL)

```bash
cp .env.example .env    # fill in FLASK_SECRET_KEY, FERNET_KEY and POSTGRES_PASSWORD
docker compose up -d --build
```

Compose starts the app and PostgreSQL 16; the app listens on `127.0.0.1:4666` only. The first visit leads to `/setup`. Expose it through Cloudflare Tunnel or a reverse proxy with HTTPS ([docs/DEPLOY.md](docs/DEPLOY.md), in Polish).

## Configuration

A `.env` file (template: [`.env.example`](.env.example)). Generate secrets with `python scripts/generate_keys.py`.

| Variable | Description |
|---|---|
| `FLASK_SECRET_KEY` | signs the session and CSRF tokens; required in production |
| `FERNET_KEY` | encrypts API keys, the SMTP password and Google tokens in the database; required in production |
| `FLASK_ENV` | `development` (Flask debug server) or `production` (waitress) |
| `AUTH_MODE` | `password` (default), `cloudflare` (identity from Cloudflare Access) or `profile` (passwordless demo, refused in production) |
| `ALLOWED_EMAILS` | for `cloudflare`: an extra e-mail allow-list checked by the app |
| `DEFAULT_LANGUAGE` | `pl` or `en`: the language before login and of the default templates seeded on first start |
| `DATABASE_URL` | SQLite in `instance/hub.db` by default; PostgreSQL: `postgresql+psycopg://...` |
| `POSTGRES_PASSWORD` | the database password for `docker-compose.yml` |
| `APP_HOST`, `APP_PORT` | `127.0.0.1:4666` by default |
| `SESSION_COOKIE_SECURE` | `true` behind HTTPS |
| `OPENROUTER_API_KEY`, `ASSISTANT_MODEL` | an alternative to the assistant settings in the UI |
| `OPENROUTER_URL` | another OpenAI-compatible endpoint (e.g. LiteLLM or a local model) instead of OpenRouter |

## Deployment

Three tested ways: **Docker Compose** with PostgreSQL, a **VPS with systemd** (the `scripts/deploy_setup.sh` script and the `scripts/polcrm.service` unit) or **Windows** (`scripts\start_prod.bat`). The app always listens locally and reaches the internet through Cloudflare Tunnel (optionally with Cloudflare Access) or a reverse proxy with HTTPS. Step-by-step guide (in Polish): [docs/DEPLOY.md](docs/DEPLOY.md).

## Security

- **Login:** scrypt password hashes, rate limiting of failed attempts (per account and per IP), a fresh session on login, sessions bound to the password (changing it logs out other sessions), deactivation takes effect immediately. `/setup` works only while there is no administrator.
- **Roles:** company settings, API keys, integrations and the team can be changed by administrators only (checked on the server); the last administrator cannot be demoted or deactivated.
- **Cloudflare Access (optional):** with `AUTH_MODE=cloudflare` the identity comes only from the `Cf-Access-Authenticated-User-Email` header, also checked against `ALLOWED_EMAILS`.
- CSRF on every form and `fetch()` call (Flask-WTF), POST-only logout, e-mail templates rendered in a Jinja2 sandbox (SSTI protection), Markdown sanitised with bleach, data escaped in JavaScript, safe file names and path checks on downloads.
- Tailwind built locally; jsDelivr libraries pinned to a version with SRI hashes (`integrity`).
- API keys (Google Maps, OpenRouter), the SMTP password, the OAuth client secret and tokens are encrypted with Fernet in the database; the key lives outside it (`FERNET_KEY`). Client access entries are links to a password manager.
- Optional masking of personal data before it is sent to the AI (polanon), with an "error instead of sending in clear text" rule.

Reporting issues: [SECURITY.md](SECURITY.md).

## Tests

```bash
pip install -r requirements-dev.txt
python -m pytest
python -m ruff check .      # lint: pyflakes rules
# the same suite on PostgreSQL:
TEST_DATABASE_URL=postgresql+psycopg://user:password@127.0.0.1:5432/polcrm_test python -m pytest
```

The tests cover:
- masking in the assistant loop (fake and real polanon),
- the assistant endpoint from HTTP request to database write,
- login, rate limits, roles, team management and first-run setup,
- translations: catalog completeness and no Polish text left in the English UI on any page,
- encryption of keys at rest and Cloudflare Access mode,
- contracts with PDFs, versioned files and whiteboards,
- audits: the edit form, the HTML and PDF report in both languages,
- deleting a company or a whiteboard with everything linked to it (this matters on PostgreSQL, which enforces foreign keys),
- finance and audit scoring logic and the main forms,
- a crawl of every GET route with no server error and no network access.

114 tests in total, the same suite on SQLite and PostgreSQL 16. CI runs them on Linux (Python 3.12 and 3.13) and Windows, separately on PostgreSQL 16, builds the Docker image and checks that the built Tailwind is up to date.

After changing Tailwind classes in templates, rebuild the CSS (Node.js is needed only for this step):

```bash
npx tailwindcss@3.4.17 -c tailwind.config.js -i static/css/tailwind.input.css -o static/css/tailwind.css --minify
```

## Project structure

```
app.py               entry point: the app from core.py + routes from routes/
core.py              configuration, login and roles, hooks, shared helpers
routes/              routes by area (companies, tasks, finances, team, assistant...)
auth.py              login modes, password policy, rate limiting
i18n.py              interface language (pl/en); translations in translations/en/*.json
models.py            SQLAlchemy models + column migrations for older SQLite databases + indexes
ai_assistant.py      AI assistant: 12 tools, tool-calling loop, OpenRouter
privacy.py           optional personal data masking (polanon)
scoring.py           audit score (5 areas) + Google PageSpeed Insights
google_sync.py       OAuth 2.0 + Search Console + GA4
finance_helpers.py   balance, MRR, overdue invoices, retainer payments
email_sender.py      SMTP + e-mail templates in a Jinja2 sandbox
crypto_utils.py      Fernet + the EncryptedText column type
contract_pdf.py      contract PDFs
pdf_report.py        audit report PDFs
templates/           Jinja2 views by module
static/              CSS (including the built Tailwind), JS (UI, assistant, Markdown editor), PWA
scripts/             start, install, admin, keys, test data, translation check, deploy
tests/               pytest
docs/                DEPLOY.md, ARCHITECTURE.md, demo.gif (PL), demo-en.gif (EN)
Dockerfile, docker-compose.yml   production image and a stack with PostgreSQL
```

How the app is built and how data flows through the assistant: [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md). Changes: [CHANGELOG.md](CHANGELOG.md).

## Known limitations

- **No production users.** The app was never used day to day, so it has not been tested by real work.
- **Integrations not verified live.** SMTP and Google Search Console / GA4 were never configured with real accounts; the tests check them without network access.
- **Schema migrations:** older SQLite databases get missing columns automatically on start; PostgreSQL starts from the full 1.0 schema, and later schema changes will need migrations (e.g. Alembic).
- **Assistant tool descriptions** for the model are in Polish; the answer comes in the user's language.
- **Password recovery** is done by an administrator (a new password in Settings → Team) or with `scripts/create_admin.py`; there is no e-mail reset.

## License

[MIT](LICENSE) © 2026 BoroMat
