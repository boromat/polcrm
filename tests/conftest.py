"""Shared fixtures. Every test session gets its own throw-away SQLite database."""

import os
import sys
import tempfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# Must be set before `app` is imported: the app configures itself at import time.
_TMP = Path(tempfile.mkdtemp(prefix="polcrm-tests-"))
# TEST_DATABASE_URL=postgresql+psycopg://... runs the whole suite on PostgreSQL (CI does both).
_TEST_DB = os.environ.get("TEST_DATABASE_URL", "").strip()
if _TEST_DB:
    from sqlalchemy import create_engine, text

    _engine = create_engine(_TEST_DB)
    with _engine.begin() as _conn:  # every run starts from an empty schema
        _conn.execute(text("DROP SCHEMA public CASCADE"))
        _conn.execute(text("CREATE SCHEMA public"))
    _engine.dispose()
    os.environ["DATABASE_URL"] = _TEST_DB
else:
    os.environ["DATABASE_URL"] = "sqlite:///" + (_TMP / "test.db").as_posix()
os.environ["FLASK_ENV"] = "development"
os.environ["CF_ACCESS_ENABLED"] = "false"
os.environ.pop("OPENROUTER_API_KEY", None)


@pytest.fixture(scope="session")
def flask_app():
    from app import app

    app.config.update(TESTING=True, WTF_CSRF_ENABLED=False)
    return app


@pytest.fixture(scope="session")
def seeded(flask_app):
    """Fictional test data from scripts/seed_test_data.py (the same data the README demo uses)."""
    sys.path.insert(0, str(ROOT / "scripts"))
    import seed_test_data

    seed_test_data.seed()  # opens its own app context
    return flask_app


DEMO_PASSWORD = "demo-polcrm"  # the default from scripts/seed_test_data.py


def login(client, email="anna@example.com", password=DEMO_PASSWORD):
    import core

    core.LOGIN_LIMITER.reset()
    return client.post("/login", data={"email": email, "password": password})


@pytest.fixture()
def client(seeded):
    """A test client logged in (password login) as the demo administrator."""
    c = seeded.test_client()
    r = login(c)
    assert r.status_code == 302, r.status_code
    return c
