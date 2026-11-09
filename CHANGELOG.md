# Changelog

## 1.0.0 - 2026-11-09

First public release. PolCRM comes from an internal tool built for a two-person agency, which was
deployed but never went into daily use. The changes against that version come in two parts:
preparing the code for publication, then what a stand-alone deployment by any small agency needs
(own login, a team of any size, Polish and English, PostgreSQL and Docker).

### Stand-alone deployment

#### Added

- Password login (scrypt hashes, rate limiting per account and IP, fresh session on login, sessions
  bound to the password), first-run `/setup` and `scripts/create_admin.py`. `AUTH_MODE` selects
  `password` (default), `cloudflare` (Cloudflare Access header) or `profile` (local demo only,
  refused in production).
- Team management in Settings → Team: any number of people, roles `admin` / `member`, deactivation,
  password resets; own profile with name, color, language and password change. Admin-only routes
  are enforced on the server; the last administrator cannot be demoted or deactivated.
- English interface: `i18n.py` (Polish source strings as keys, `translations/en/*.json`, Jinja i18n,
  JS `t()`), PL/EN switch in the top bar and on the login page, dates in both languages, English
  PDFs and assistant answers, English default templates with `DEFAULT_LANGUAGE=en`.
  `scripts/i18n_check.py` and tests guard completeness and Polish leftovers in the English UI.
- PostgreSQL support (`psycopg`), `Dockerfile` and `docker-compose.yml` with PostgreSQL 16, CI jobs
  for PostgreSQL and the Docker image.
- Tests for login, roles and team, translations, contracts with PDFs, file uploads, whiteboards,
  audits (edit form, HTML and PDF report in both languages) and deleting a company or a whiteboard
  with everything linked to it. 114 tests, the same suite on SQLite and PostgreSQL 16.
- Demo data: three accounts with passwords, a finished audit with competitors and a whiteboard.
- The PWA manifest is served per language (`/manifest.webmanifest`) instead of a static Polish file.

#### Changed

- `app.py` (almost 4,000 lines) split into `core.py` and `routes/` modules by area; URLs and endpoint
  names are unchanged (route map compared before and after).
- The dashboard team pulse and day timeline work for any team size, with two queries in total
  instead of three per person; demo data has three accounts.
- Fresh installations no longer create the two default profiles; the first account is the
  administrator created in `/setup`, in the language the setup page was shown in. New accounts
  start in `DEFAULT_LANGUAGE`.
- The activity log and task history show labels instead of codes ("Status change", "To do → In
  progress" instead of `status_change`, `todo → in_progress`).
- Google Places requests (lead search, competitors) use `DEFAULT_LANGUAGE` instead of a fixed `pl`.
- Settings sit in one centred column on wide screens; the team table headers line up with their
  columns and select fields have the same height as text fields.

#### Fixed

- Contract and audit PDFs failed with an fpdf "Not enough horizontal space" error whenever two
  text lines followed each other (`multi_cell` left the cursor at the right margin). The audit PDF
  failed for every audit with a list of problems or recommendations.
- Two contracts generated in the same second for the same client and template shared one PDF file
  on disk, so the second overwrote the first; the stored file name is now unique.
- New contracts computed the gross amount with a fixed 23% VAT; they now use the VAT rate from
  Settings (0% when the agency is not a VAT payer).
- Deleting a company failed on PostgreSQL when the company had content posts linked to tasks,
  loose tasks, costs, e-mail history or whiteboards; on SQLite (no foreign key checks) it left
  orphaned rows. `models.delete_company` now removes what belongs to the company and detaches
  the rest. Deleting a whiteboard also removes its erased elements, which the ORM cascade missed.
- After a message to the assistant, its send button showed a spinner for 8 seconds: the global
  "loading" state was applied to forms handled in JavaScript and to cancelled `confirm()` dialogs.
- The CSRF error page was always in Polish (CSRF check runs before the language is set).

### Preparing the internal code for publication

#### Added

- Optional PII masking for the AI assistant with [polanon](https://github.com/boromat/polanon)
  (`privacy.py`): the question, the history and tool results are masked, tool arguments and the
  answer are restored locally, and a masking failure blocks the request ("fail closed").
  Switched on in Settings → AI Assistant, with an optional spaCy NER mode. Client company names
  from the CRM are always masked (polanon `DenylistGuard`), also when a client is named like a
  well-known brand on polanon's allowlist: a bare name in a tool-result field has no sentence
  around it, and the rules alone let "Auto Serwis Nowak" through.
- Docstrings for the assistant's tool executors and the tool contract.
- Test suite (pytest): masking contract with a fake and with the real polanon, the assistant
  endpoint end to end, smoke tests of every main screen on seed data, encryption at rest,
  Cloudflare Access mode, finance helpers, audit scoring and the main forms.
- GitHub Actions CI on Ubuntu (Python 3.12, 3.13) and Windows, with a pyflakes lint (ruff);
  unused imports removed.
- `OPENROUTER_URL` setting (any OpenAI-compatible endpoint, e.g. LiteLLM or a local model),
  `DATABASE_URL` setting, `requirements-dev.txt`, `pytest.ini`, `.gitattributes`.
- README in Polish and English with a 1920x1080 demo GIF (fictional seed data only),
  `docs/ARCHITECTURE.md`, `SECURITY.md`.

#### Changed

- The Google Maps API key and the OAuth client secret are now encrypted at rest (Fernet), like the
  other secrets. Plain-text values from older databases are still read.
- In development, without `FERNET_KEY`, the Fernet key is generated into
  `instance/fernet_dev.key` instead of being written to the database in the middle of a flush.
- Assistant history in the session cookie is capped (8 entries, 600 characters each) to stay under
  the browser's cookie size limit.
- `SQLAlchemy` is pinned (`2.0.57`); Windows scripts create and use `.venv`.
- No deprecated APIs left: `datetime.utcnow()` replaced by `models.utcnow()` (the same naive UTC
  value, so stored data is unchanged), `Query.get()` / `get_or_404()` by `db.session.get()` /
  `db.get_or_404()`. The test suite (including a crawl of every GET route) runs without warnings and turns these deprecations into errors.
- Rewritten `docs/DEPLOY.md`; neutral example profiles, e-mails and `.example` domains in seed data.

#### Fixed

- `scripts/seed_test_data.py` crashed on a fresh database (Fernet key committed inside a flush)
  and on the Windows console (`cp1250` could not print arrows); it now also runs from the
  repository root.
- With `CF_ACCESS_ENABLED=true` a profile cookie no longer works without the Cloudflare Access
  header, so it cannot bypass `ALLOWED_EMAILS`.
- Stored XSS: knowledge base articles were rendered from Markdown without sanitising; calendar
  events, board names and Google Places results were inserted into JavaScript/HTML unescaped.
- Settings: the "Ogólne" and "Finanse" tabs posted the same section, so saving one blanked the
  other; saved API keys and the OAuth client secret are no longer printed into the page source.
- A 0% VAT rate (exempt) was silently saved as 23%.
- "Usuń" on the company card saved the form instead of deleting (nested `<form>`).
- Dashboard links used `?range=` / `?status=`, which the task list ignores.
- The assistant read a non-existent `contact_phone` field and offered a payment kind the model
  layer does not know.
- PDF generation: removed the runtime font download from GitHub and a broken Helvetica fallback
  (the DejaVu fonts ship with the repository).
- PWA manifest pointed to PNG icons that did not exist; removed an unused legacy template.
- Generated retainer payments used a hard-coded 23% VAT instead of the rate from Settings, and
  ignored "Jestem VAT-owcem"; a saved 0% rate was shown (and re-saved) as 23 in the form.
- Markdown preview in the editor: quotes were not escaped and any link target was accepted
  (`javascript:`), so previewing someone else's text could run script.
- Logout accepted GET, so a link from another site could log a user out; it is POST-only now.
- Seed data: retainer payment titles follow their (relative) dates instead of fixed 2026 months.
- User names and colors are escaped before going into `innerHTML` (mentions, whiteboard cursors).
- The FullCalendar stylesheet link returned 404 on every calendar page (FullCalendar 6 injects its
  CSS from JavaScript); removed.

#### Security

- Subresource Integrity (`integrity` + `crossorigin`) on every pinned jsDelivr asset, with a test
  that fails when a new CDN tag has no hash; service worker cache version bumped.

- Tailwind is built locally (`tailwind.config.js`, `static/css/tailwind.css`, 22 KB minified) instead
  of the Play CDN, which compiled CSS in the browser and could not carry SRI. Full-page screenshots
  of 23 screens before and after are pixel-identical; a CI job fails when the committed CSS is
  out of date.

#### Performance

- Dashboard: the sparklines, streak and pipeline counters run 3 queries instead of up to 80
  (same results, checked before and after).
- SQLite indexes for the filters used by the dashboard, lists and the assistant
  (`models.ensure_indexes`, created idempotently on start).

#### UI

- Gender-neutral activity labels ("utworzył(a)", "Utworzone przez"), clearer profile picker copy.
