"""PolCRM entry point: builds the app (core.py), registers the routes (routes/) and runs it.

Run: python app.py (development) or FLASK_ENV=production python app.py (waitress).
The Werkzeug debugger needs FLASK_DEBUG=1 as well (scripts/start.bat sets it).
"""

import os

import routes  # noqa: F401  (registers every route on app)
from core import IS_PRODUCTION, app

# ── Entry point ───────────────────────────────────────────────


def main():
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "4666"))

    if IS_PRODUCTION:
        # Produkcja: waitress (stabilny WSGI, dziala natywnie na Windows)
        from waitress import serve

        print(f"[PRODUKCJA] waitress na http://{host}:{port}")
        print("[PRODUKCJA] Ekspozycja przez Cloudflare Tunnel - nie otwieraj portu na zewnatrz.")
        serve(app, host=host, port=port, threads=8)
    else:
        # Dev: serwer Flaska. Debugger Werkzeuga tylko na wyrazne FLASK_DEBUG=1, zeby instalacja, ktorej
        # .env pominal FLASK_ENV=production, nie wystawila go przez tunel.
        debug = os.environ.get("FLASK_DEBUG", "").strip() == "1"
        print(f"[DEV] serwer Flaska{' z debugerem' if debug else ''} na http://{host}:{port}")
        app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    main()
