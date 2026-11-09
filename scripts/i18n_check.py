"""Find Polish text left in the English interface.

Logs in as a person with language "en", requests every GET page (detail pages with ids 1-3) and
collects the visible interface text: text nodes and the placeholder / title / aria-label / alt
attributes. Text that comes from the database (company names, task titles, notes - user data stays
in the language it was written in) is removed first, using every string value in the database.
What remains and still looks Polish (Polish letters or common Polish UI words) is reported.

    python scripts/i18n_check.py            # report for every page
    python scripts/i18n_check.py /tasks     # only pages whose path starts with /tasks

Used by tests/test_i18n.py, which requires an empty report.
"""

from __future__ import annotations

import json
import re
import sys
from html.parser import HTMLParser

POLISH_LETTERS = re.compile(r"[ąćęłńóśźżĄĆĘŁŃÓŚŹŻ]")
POLISH_WORDS = re.compile(r"\b(" + "|".join([
    "zapisz", "usun", "dodaj", "edytuj", "anuluj", "brak", "nowy", "nowa", "nowe", "wszystkie", "szukaj",
    "firmy", "firma", "zadania", "zadanie", "ustawienia", "kalendarz", "notatki", "notatka", "finanse",
    "koszty", "termin", "opis", "status zadania", "wyloguj", "zaloguj", "jutro", "klient", "klienci", "projekt",
    "projekty", "wizyta", "wizyty", "oferta", "oferty", "pakiet", "pakiety", "umowa", "umowy", "szablon",
    "szablony", "raport", "bilans", "pilne", "wysoki", "niski", "zrobione", "do zrobienia", "pokaz", "wiecej",
    "zamknij", "filtruj", "szczegoly", "skrzynka", "tablica", "przeglad", "uwaga", "albo", "oraz", "jest",
    "nie ma", "kliknij", "wpisz", "wybierz", "zobacz", "otworz", "pobierz", "wyslij", "zadan", "firm",
    "lub", "tylko", "przez", "jesli", "jeszcze", "bez", "dla", "przy", "tutaj", "teraz", "dzis",
]) + r")\b", re.IGNORECASE)
# Allowed in the English UI: currency, brand, names of Polish services (business directories)
ALLOWED = re.compile(r"\bzł\b|PolCRM|\bPLN\b|Panorama Firm")


class _Collector(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.texts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style", "textarea", "code", "pre"):
            self._skip += 1
        for key, value in attrs:
            if key in ("placeholder", "title", "aria-label", "alt") and value:
                self.texts.append(value)

    def handle_endtag(self, tag):
        if tag in ("script", "style", "textarea", "code", "pre") and self._skip:
            self._skip -= 1

    def handle_data(self, data):
        if not self._skip and data.strip():
            self.texts.append(data)


_MD_LINE = re.compile(r"^\s*(?:#{1,6}\s+|>\s*|[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)")
_MD_INLINE = re.compile(r"\*\*|__|`+|!?\[|\]\([^)]*\)|\]")


def _fragments(value: str):
    """A stored string and the pieces of it that can appear as one text node once rendered:
    each line, the line without Markdown markers, and the runs between inline formatting."""
    yield value
    for line in value.splitlines():
        yield line
        line = _MD_LINE.sub("", line)
        yield line
        yield from _MD_INLINE.split(line)


def _strings_in(value):
    """Strings inside a column value. JSON kept in text columns (lists of keywords, lists of dicts)
    is parsed, and a list of strings is also yielded joined with ", " as the templates show it."""
    if isinstance(value, str):
        yield value
        if value[:1] in "[{":
            try:
                yield from _strings_in(json.loads(value))
            except ValueError:
                pass
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings_in(v)
    elif isinstance(value, (list, tuple)):
        if value and all(isinstance(v, str) for v in value):
            yield ", ".join(value)
        for v in value:
            yield from _strings_in(v)


def _db_strings(db):
    """Every string value stored in the database (user data), longest first."""
    from sqlalchemy import JSON, String, Text

    values = set()
    for mapper in db.Model.registry.mappers:
        cols = [c for c in mapper.columns if isinstance(c.type, (String, Text, JSON))]
        if not cols:
            continue
        for row in db.session.query(*cols).all():
            for v in row:
                for text in _strings_in(v):
                    for part in _fragments(text):
                        part = " ".join(part.split())
                        if len(part) >= 3:
                            values.add(part)
    return sorted(values, key=len, reverse=True)


def _looks_polish(text: str) -> bool:
    text = ALLOWED.sub(" ", text)
    folded = text.translate(str.maketrans("ąćęłńóśźżĄĆĘŁŃÓŚŹŻ", "acelnoszzACELNOSZZ"))
    return bool(POLISH_LETTERS.search(text) or POLISH_WORDS.search(folded))


def polish_texts(html: str, data=()) -> list[str]:
    """Polish-looking interface texts in one page, after removing the user data strings in `data`."""
    parser = _Collector()
    parser.feed(html)
    found = []
    for raw in parser.texts:
        text = " ".join(raw.split())
        if not _looks_polish(text):
            continue
        for value in data:  # strip user data, keep the interface text around it
            if value in text:
                text = text.replace(value, " ")
        text = " ".join(text.split())
        if text and _looks_polish(text) and text not in found:
            found.append(text)
    return found


def find_leftovers(app, client, prefix: str = "") -> dict[str, list[str]]:
    """{path: [Polish-looking UI texts]} for every GET page, rendered for an English-speaking user.

    Pages behind the Google API key check (audits, lead search) get a placeholder key for the run,
    so they render instead of redirecting; their GET views make no calls to Google."""
    from models import Settings, db

    with app.app_context():
        data = _db_strings(db)
        settings = Settings.get()
        saved_key = settings.google_api_key
        settings.google_api_key = saved_key or "placeholder-key-for-i18n-check"
        db.session.commit()
    try:
        return _crawl(app, client, prefix, data)
    finally:
        with app.app_context():
            settings = Settings.get()
            settings.google_api_key = saved_key
            db.session.commit()


def _crawl(app, client, prefix, data) -> dict[str, list[str]]:
    report: dict[str, list[str]] = {}
    for rule in app.url_map.iter_rules():
        if "GET" not in rule.methods or rule.endpoint in ("static", "oauth2callback", "google_oauth_start"):
            continue
        args = list(rule.arguments)
        if len(args) > 1 or (args and type(rule._converters[args[0]]).__name__ != "IntegerConverter"):
            continue
        paths = [rule.rule] if not args else [re.sub(r"<int:\w+>", str(i), rule.rule) for i in (1, 2, 3)]
        for path in paths:
            if prefix and not path.startswith(prefix):
                continue
            resp = client.get(path)
            if resp.status_code != 200 or "html" not in (resp.content_type or ""):
                continue
            found = polish_texts(resp.get_data(as_text=True), data)
            if found:
                report[path] = found
    return report


def main():
    import os
    import tempfile
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent
    sys.path.insert(0, str(root))
    sys.path.insert(0, str(root / "scripts"))
    tmp = Path(tempfile.mkdtemp(prefix="polcrm-i18n-"))
    os.environ["DATABASE_URL"] = "sqlite:///" + (tmp / "i18n.db").as_posix()
    os.environ.setdefault("FLASK_ENV", "development")
    import contextlib
    import io

    import seed_test_data
    from app import app
    from models import User, db

    with contextlib.redirect_stdout(io.StringIO()):
        seed_test_data.seed()
    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False, PROPAGATE_EXCEPTIONS=False)
    with app.app_context():
        user = User.query.filter_by(email="anna@example.com").one()
        user.language = "en"
        db.session.commit()
    client = app.test_client()
    import core
    core.LOGIN_LIMITER.reset()
    client.post("/login", data={"email": "anna@example.com", "password": seed_test_data.DEMO_PASSWORD})
    report = find_leftovers(app, client, sys.argv[1] if len(sys.argv) > 1 else "")
    total = 0
    for path, texts in sorted(report.items()):
        print(f"\n{path}")
        for t in texts:
            print(f"   {t[:160]}")
            total += 1
    print(f"\n{total} Polish-looking texts on {len(report)} pages")


if __name__ == "__main__":
    main()
