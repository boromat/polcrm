"""PolCRM entry point: builds the app (core.py), registers the routes (routes/) and runs it.

Run: python app.py (development) or FLASK_ENV=production python app.py (waitress).
"""

import os

import routes  # noqa: F401  (registers every route on app)
from core import IS_PRODUCTION, app

# ── Entry point ───────────────────────────────────────────────

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", "4666"))

    if IS_PRODUCTION:
        # Produkcja: waitress (stabilny WSGI, dziala natywnie na Windows)
        from waitress import serve
        print(f"[PRODUKCJA] waitress na http://{host}:{port}")
        print("[PRODUKCJA] Ekspozycja przez Cloudflare Tunnel - nie otwieraj portu na zewnatrz.")
        serve(app, host=host, port=port, threads=8)
    else:
        # Dev: Flask dev server z debugiem
        print(f"[DEV] Flask debug na http://{host}:{port}")
        app.run(host=host, port=port, debug=True)
