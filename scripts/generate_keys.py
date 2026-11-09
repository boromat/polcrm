"""Wygeneruj sekrety do pliku .env - uruchom raz przed pierwszym startem produkcji."""

import secrets

from cryptography.fernet import Fernet


def main():
    flask_secret = secrets.token_hex(32)
    fernet_key = Fernet.generate_key().decode("utf-8")

    print()
    print("=" * 70)
    print("  WYGENEROWANE SEKRETY - wklej do pliku .env")
    print("=" * 70)
    print()
    print(f"FLASK_SECRET_KEY={flask_secret}")
    print(f"FERNET_KEY={fernet_key}")
    print()
    print("=" * 70)
    print("  UWAGA: zapisz te klucze w bezpiecznym miejscu (np. 1Password).")
    print("  Jeśli stracisz FERNET_KEY, stracisz dostep do zapisanego hasla SMTP.")
    print("=" * 70)
    print()


if __name__ == "__main__":
    main()
