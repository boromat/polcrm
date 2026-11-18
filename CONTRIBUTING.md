# Contributing

Bug reports, fixes and translations are welcome. PolCRM is a Flask app for a small agency: clients,
tasks, finances, audits, contracts and an AI assistant, in Polish and English, on SQLite or
PostgreSQL.

## Setup

```bash
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements-dev.txt
python scripts/seed_test_data.py                        # made-up companies and three demo accounts
FLASK_ENV=development python app.py                     # http://127.0.0.1:4666
```

The demo accounts are in the README. `requirements-dev.txt` adds pytest with coverage, ruff, mypy
and polanon, so the masking tests run against the real library. Node.js is needed for one thing
only: rebuilding `static/css/tailwind.css` after a change to the Tailwind classes in a template
(the command is in the README). `docs/ARCHITECTURE.md` explains how the app is put together.

## Quality bar

- `python -m ruff check .`, `python -m ruff format --check .`, `python -m mypy .` and
  `python -m pytest --cov` pass locally. CI runs them on Linux (Python 3.12 and 3.13) and Windows,
  runs the whole suite again on PostgreSQL 16, builds the Docker image and checks that the
  committed Tailwind CSS is up to date.
- Coverage stays at or above the floor in `.coveragerc` (60%, a little under where the suite is).
  The floor is there to stop it sliding back: raise it when the suite has grown past it.
- A change that touches the database runs on both engines: `TEST_DATABASE_URL=postgresql+psycopg://...
  python -m pytest` runs the suite on an empty PostgreSQL schema. Use portable SQLAlchemy only.
- Tests for every behaviour change, and no network in them: `tests/test_app_smoke.py` crawls every
  GET route with the network blocked, and the AI and Google calls are replaced with fakes.
- Every interface string goes through `_()` (`{{ _('...') }}` in a template, `i18n._()` in Python,
  `t()` in JavaScript) and gets its English in `translations/en/*.json` with the same placeholders.
  `tests/test_i18n.py` fails on a missing translation and on Polish text left in the English
  interface (`python scripts/i18n_check.py` shows where).
- A library from jsDelivr is pinned to a version with an `integrity` hash, and a Tailwind class
  added to a template comes with the rebuilt CSS.
- Plain sentences in the imperative mood for commit messages, one logical change each:
  `Add a due date filter to the task list`, `Fix the VAT total for a 0% rate`.
- `README.md` is Polish and `README.en.md` is its English translation: a change to one is made to
  the other in the same commit.

## Test data

Invented data only, in tests, fixtures, screenshots and issues alike. No real client, person,
company, address, phone number or log belongs in the repository.

- E-mail addresses and websites use `example.com` or a `.example` domain
  (`anna@example.com`, `biuro@kwiaciarnia.example`).
- A PESEL has a valid checksum and a birth date before 1860 or after 2100, so it can never belong
  to a living person: `50810112354` is 1 January 1850.
- `scripts/seed_test_data.py` fills a database with made-up companies for the tests and for a demo;
  extend it rather than adding real-looking records elsewhere.

## Changes written with AI tools

Welcome, on the same terms as any other change. Say in the pull request that an AI tool wrote or
helped write it, and which one, so the review knows where to look. You answer for the change as if
you had typed it yourself: you have read every line, run the quality bar above, and can answer
questions about it. A pull request that nobody answers for after a review is closed.

## Masking and security

The optional masking of personal data before an AI call is done by
[polanon](https://github.com/boromat/polanon). A value it did not recognise is a detection gap in
polanon: report it there, with invented text of the same shape. A way to read or change data
without the right role, to get a secret out of the database, or to make the assistant send personal
data while masking is on is a security report: see `SECURITY.md`, never a public issue.

## Releases

The version number lives in `CHANGELOG.md` only. To release, rename `## Unreleased` to
`## X.Y.Z - YYYY-MM-DD` in a commit of its own (`Release X.Y.Z`), then push the tag `vX.Y.Z`.
`.github/workflows/release.yml` checks that the section is there and dated, publishes the Docker
image to `ghcr.io/boromat/polcrm` and creates the GitHub release with that section as its notes.
