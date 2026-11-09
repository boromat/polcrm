"""Interface language: Polish (source) and English.

Polish strings in the code and templates are the message keys; English translations live in
``translations/en/*.json`` (several files so that areas of the app can be translated and reviewed
separately, all merged at start). No compiled ``.mo`` files and no extra dependency.

* Python:    ``from i18n import _`` then ``_("Zapisano.")`` or ``_("Dodano: %(name)s", name=x)``
* Templates: ``{{ _('Zapisz') }}``, ``{{ _('Witaj %(name)s', name=user.name) }}`` (Jinja i18n
  extension, new-style gettext: values are escaped, the message itself is trusted)
* JavaScript: ``t('Zapisz')`` with the strings from ``translations/en/js.json`` sent to the page

The language comes from the logged-in person's profile; before login from the ``polcrm_lang``
cookie, then the browser's Accept-Language, then ``DEFAULT_LANGUAGE`` (pl).
A missing translation falls back to Polish - never to an empty string or an error.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

LANGUAGES = ("pl", "en")
LANG_COOKIE = "polcrm_lang"
DEFAULT_LANGUAGE = os.environ.get("DEFAULT_LANGUAGE", "pl").strip().lower()
if DEFAULT_LANGUAGE not in LANGUAGES:
    DEFAULT_LANGUAGE = "pl"

_DIR = Path(__file__).parent / "translations"


def load_catalog(lang: str) -> dict[str, str]:
    """All ``translations/<lang>/*.json`` merged. A key defined twice must agree."""
    catalog: dict[str, str] = {}
    folder = _DIR / lang
    if not folder.is_dir():
        return catalog
    for path in sorted(folder.glob("*.json")):
        for key, value in json.loads(path.read_text(encoding="utf-8")).items():
            if key in catalog and catalog[key] != value:
                raise ValueError(f"{path.name}: conflicting translation for {key!r}")
            catalog[key] = value
    return catalog


CATALOGS: dict[str, dict[str, str]] = {"en": load_catalog("en")}


def current_language() -> str:
    """Language of the current request (set by core.set_language), or DEFAULT_LANGUAGE outside one."""
    try:
        from flask import g, has_request_context
    except ImportError:  # pragma: no cover - flask is always installed with the app
        return DEFAULT_LANGUAGE
    if has_request_context() and "lang" in g:
        return g.lang
    return DEFAULT_LANGUAGE


def gettext(message: str, lang: str | None = None) -> str:
    lang = lang or current_language()
    if lang == "pl" or not message:
        return message
    return CATALOGS.get(lang, {}).get(message, message)


def _(message: str, **values) -> str:
    """Translate, then fill ``%(name)s`` placeholders (Python side; templates escape on their own)."""
    text = gettext(message)
    return text % values if values else text


def ngettext(singular: str, plural: str, n: int) -> str:
    return gettext(singular if n == 1 else plural)


def js_catalog(lang: str) -> dict[str, str]:
    """Strings used by static/js (translations/en/js.json), sent to the page as JSON."""
    if lang == "pl":
        return {}
    path = _DIR / lang / "js.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}


# Dates: the app shows weekday and month names in both languages.
MONTHS = {
    "pl": ["stycznia", "lutego", "marca", "kwietnia", "maja", "czerwca", "lipca", "sierpnia",
           "września", "października", "listopada", "grudnia"],
    "en": ["January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"],
}
MONTHS_NOMINATIVE = {
    "pl": ["Styczeń", "Luty", "Marzec", "Kwiecień", "Maj", "Czerwiec", "Lipiec", "Sierpień",
           "Wrzesień", "Październik", "Listopad", "Grudzień"],
    "en": MONTHS["en"],
}
WEEKDAYS = {
    "pl": ["Poniedziałek", "Wtorek", "Środa", "Czwartek", "Piątek", "Sobota", "Niedziela"],
    "en": ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"],
}


def format_long_date(d, lang: str | None = None) -> str:
    lang = lang or current_language()
    if lang == "en":
        return f"{WEEKDAYS['en'][d.weekday()]}, {MONTHS['en'][d.month - 1]} {d.day}, {d.year}"
    return f"{WEEKDAYS['pl'][d.weekday()]}, {d.day} {MONTHS['pl'][d.month - 1]} {d.year}"


def weekday_name(d, lang: str | None = None) -> str:
    return WEEKDAYS[lang or current_language()][d.weekday()]


def month_name(month: int, lang: str | None = None) -> str:
    """Nominative month name (headings, payment titles): "Marzec" / "March"."""
    return MONTHS_NOMINATIVE[lang or current_language()][month - 1]
