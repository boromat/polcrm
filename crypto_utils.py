"""Szyfrowanie pol bazy danych (Fernet) + TypeDecorator dla SQLAlchemy.

Uzycie w modelach:
    from crypto_utils import EncryptedText
    ...
    gsc_refresh_token = db.Column(EncryptedText, default="")

Migracja bezproblemowa: legacy plaintext jest czytany jako plaintext,
a przy najblizszym zapisie zostaje zaszyfrowany.
"""

import os
from pathlib import Path

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy.types import TypeDecorator, Text


_FERNET_CACHE = None


def _get_fernet():
    """Zwroc Fernet. Kolejnosc: FERNET_KEY z ENV -> stary klucz z tabeli settings -> plik dev.

    Funkcja bywa wolana w trakcie flusha SQLAlchemy (TypeDecorator ponizej), wiec NIE moze
    uzywac sesji ani robic commit - inaczej flush konczy sie bledem "This transaction is closed".
    Dlatego stary klucz z bazy czytamy osobnym polaczeniem (tylko odczyt), a nowy klucz
    deweloperski zapisujemy do pliku instance/fernet_dev.key (gitignored).
    """
    global _FERNET_CACHE
    if _FERNET_CACHE is not None:
        return _FERNET_CACHE

    env_key = os.environ.get("FERNET_KEY", "").strip()
    if env_key:
        _FERNET_CACHE = Fernet(env_key.encode("utf-8"))
        return _FERNET_CACHE

    key = _legacy_db_key() or _dev_file_key()
    _FERNET_CACHE = Fernet(key.encode("utf-8"))
    return _FERNET_CACHE


def _legacy_db_key():
    """Klucz z kolumny settings.fernet_key (starsze instalacje). Brak tabeli/klucza -> None."""
    try:
        from sqlalchemy import text
        from models import db
        with db.engine.connect() as conn:
            row = conn.execute(text("SELECT fernet_key FROM settings ORDER BY id LIMIT 1")).first()
        return (row[0] or "").strip() or None if row else None
    except Exception:
        return None


def _dev_file_key():
    """Klucz deweloperski w instance/fernet_dev.key - tworzony przy pierwszym uzyciu."""
    if os.environ.get("FLASK_ENV", "development").lower() == "production":
        raise RuntimeError("FERNET_KEY musi byc ustawiony w produkcji (scripts/generate_keys.py).")
    path = Path(__file__).parent / "instance" / "fernet_dev.key"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    path.parent.mkdir(parents=True, exist_ok=True)
    key = Fernet.generate_key().decode("utf-8")
    path.write_text(key, encoding="utf-8")
    return key


def reset_fernet_cache():
    """Wyzeruj cache (np. po zmianie klucza w testach)."""
    global _FERNET_CACHE
    _FERNET_CACHE = None


def encrypt_str(plaintext):
    """Zaszyfruj string. Pusta wartosc -> pusta wartosc."""
    if not plaintext:
        return ""
    f = _get_fernet()
    return f.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_str(ciphertext):
    """Odszyfruj string. Na blad -> zwroc ""."""
    if not ciphertext:
        return ""
    try:
        f = _get_fernet()
        return f.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return ""


def decrypt_or_legacy(value):
    """Probuj odszyfrowac. Jak sie nie uda (legacy plaintext), zwroc oryginal.

    Fernet ciphertext zawsze zaczyna sie od 'gAAAAA' (base64 z wersji 0x80).
    Jesli wartosc nie ma tego prefiksu, to na 100% nie jest Fernet -> zwroc jak jest.
    Jesli ma, probuj odszyfrowac -> sukces = czysty string, porazka (InvalidToken)
    = traktujemy jako legacy plaintext ktory "przypadkiem" wyglada jak Fernet.
    """
    if not value:
        return value
    if not value.startswith("gAAAAA"):
        return value  # na pewno plaintext
    try:
        f = _get_fernet()
        return f.decrypt(value.encode("utf-8")).decode("utf-8")
    except (InvalidToken, ValueError):
        return value  # legacy, nie szyfrowane


class EncryptedText(TypeDecorator):
    """Kolumna TEXT szyfrowana Fernetem - transparentnie dla SQLAlchemy.

    Zapis: plaintext → ciphertext (zawsze szyfruje).
    Odczyt: ciphertext → plaintext (z fallbackiem na legacy).
    """

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        if value is None or value == "":
            return value
        return encrypt_str(value)

    def process_result_value(self, value, dialect):
        if value is None or value == "":
            return value
        return decrypt_or_legacy(value)
