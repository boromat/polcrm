"""Smoke tests: the app boots on fictional seed data and every main screen renders."""

import json

import pytest

import ai_assistant
import privacy

PAGES = [
    "/", "/companies", "/companies/new", "/pipeline", "/tasks", "/tasks/new", "/calendar",
    "/finances", "/finances/payments", "/finances/expenses", "/finances/subscriptions",
    "/finances/report/internal", "/projects", "/content", "/content/calendar", "/notes",
    "/knowledge", "/packages", "/audits", "/emails/templates", "/emails/log",
    "/contracts/templates", "/tablica", "/settings", "/aktywnosci", "/inbox", "/search",
    "/szukaj-globalnie?q=Kowalski", "/visit-guide",
]


def test_login_is_required(seeded):
    r = seeded.test_client().get("/")
    assert r.status_code == 302
    assert "/login" in r.headers["Location"]


@pytest.mark.parametrize("path", PAGES)
def test_main_pages_render(client, path):
    r = client.get(path, follow_redirects=True)
    assert r.status_code == 200, f"{path} -> {r.status_code}"
    assert b"PolCRM" in r.data


def test_company_detail_renders_for_every_seeded_company(client, seeded):
    from models import Company

    with seeded.app_context():
        ids = [c.id for c in Company.query.all()]
    assert ids
    for cid in ids:
        assert client.get(f"/companies/{cid}").status_code == 200


def test_settings_shows_polanon_toggle(client):
    html = client.get("/settings").get_data(as_text=True)
    assert 'name="pii_masking_enabled"' in html


def test_assistant_api_masks_end_to_end(client, seeded, monkeypatch):
    """Masking on: the tool runs on the real database, the model only gets tokens."""
    from models import Note, Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.assistant_enabled = True
        s.pii_masking_enabled = True
        db.session.commit()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")

    secrets = {"Jan Kowalski": "OSOBA"}

    def fake_anonymize(text, mapping):
        mapping = dict(mapping)
        for value, label in secrets.items():
            if value in text:
                token = next((t for t, v in mapping.items() if v == value), f"<{label}_1>")
                mapping[token] = value
                text = text.replace(value, token)
        return text, mapping

    monkeypatch.setattr(ai_assistant, "build_masker",
                        lambda settings=None: privacy.Masker(anonymize=fake_anonymize))
    sent = []

    def fake_call(messages, **kw):
        sent.append(json.dumps(messages, ensure_ascii=False))
        if len(sent) == 1:
            return {"choices": [{"message": {"content": "", "tool_calls": [{
                "id": "c1", "type": "function", "function": {
                    "name": "add_note",
                    "arguments": json.dumps({"title": "Telefon", "content": "Oddzwonić do <OSOBA_1>"})}}]}}]}
        return {"choices": [{"message": {"content": "Dodałem notatkę o <OSOBA_1>."}}]}

    monkeypatch.setattr(ai_assistant, "call_model", fake_call)
    r = client.post("/api/assistant/chat", json={"message": "Zanotuj: oddzwonić do Jan Kowalski"})
    data = r.get_json()

    assert r.status_code == 200, data
    assert data["reply"] == "Dodałem notatkę o Jan Kowalski."
    assert data["tools_called"] == ["add_note"]
    assert all("Jan Kowalski" not in s for s in sent)
    with seeded.app_context():
        note = Note.query.order_by(Note.id.desc()).first()
        assert note.content == "Oddzwonić do Jan Kowalski"
        s = Settings.get()
        s.pii_masking_enabled = False
        s.assistant_enabled = False
        db.session.commit()


def test_assistant_api_refuses_when_masking_is_broken(client, seeded, monkeypatch):
    from models import Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.assistant_enabled = True
        s.pii_masking_enabled = True
        db.session.commit()
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key-not-real")

    def unavailable(settings=None):
        raise privacy.MaskingUnavailable("pakiet polanon nie jest zainstalowany")

    monkeypatch.setattr(ai_assistant, "build_masker", unavailable)
    monkeypatch.setattr(ai_assistant, "call_model", lambda *a, **k: pytest.fail("model was called"))
    r = client.post("/api/assistant/chat", json={"message": "Jan Kowalski"})
    assert r.status_code == 503
    assert "Nic nie zostało wysłane" in r.get_json()["error"]
    with seeded.app_context():
        s = Settings.get()
        s.pii_masking_enabled = False
        s.assistant_enabled = False
        db.session.commit()


def test_api_keys_are_encrypted_at_rest(seeded):
    """Google Maps API key and OAuth client secret are stored with Fernet, read back transparently."""
    from sqlalchemy import text

    from models import Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.google_api_key = "AIza-test-not-a-real-key"
        s.google_oauth_client_secret = "oauth-secret-not-real"
        db.session.commit()
        raw = db.session.execute(
            text("SELECT google_api_key, google_oauth_client_secret FROM settings")).first()
        assert "AIza-test-not-a-real-key" not in raw[0]
        assert "oauth-secret-not-real" not in raw[1]
        db.session.expire_all()
        assert Settings.get().google_api_key == "AIza-test-not-a-real-key"
        s = Settings.get()
        s.google_api_key = ""
        s.google_oauth_client_secret = ""
        db.session.commit()


def test_cloudflare_access_mode_ignores_profile_cookie(seeded, monkeypatch):
    """With Cloudflare Access only the header counts: a profile cookie must not bypass ALLOWED_EMAILS."""
    import core
    from models import User

    monkeypatch.setattr(core, "AUTH_MODE", "cloudflare")
    monkeypatch.setattr(core, "CF_ACCESS_ENABLED", True)
    monkeypatch.setattr(core, "ALLOWED_EMAILS", {"anna@example.com"})
    with seeded.app_context():
        uid = User.query.filter_by(email="anna@example.com").first().id
    c = seeded.test_client()
    c.set_cookie(core.PROFILE_COOKIE, str(uid))

    assert c.get("/tasks").status_code == 403  # cookie alone
    outsider = {"Cf-Access-Authenticated-User-Email": "intruz@example.com"}
    assert c.get("/tasks", headers=outsider).status_code == 403  # not on the list
    allowed = {"Cf-Access-Authenticated-User-Email": "anna@example.com"}
    assert c.get("/tasks", headers=allowed).status_code == 200


def test_no_get_route_crashes(client, seeded, monkeypatch):
    """Every GET route (with ids 1-3 for detail pages) answers without a server error and without
    touching the network. Catches regressions such as a broken query in a rarely visited page."""
    import re

    import requests

    def no_network(*args, **kwargs):
        raise AssertionError("a page tried to reach the network during the crawl")

    monkeypatch.setattr(requests.sessions.Session, "request", no_network)
    seeded.config["PROPAGATE_EXCEPTIONS"] = False
    skip = {"static", "google_oauth_start", "oauth2callback"}
    failures = []
    try:
        for rule in seeded.url_map.iter_rules():
            if "GET" not in rule.methods or rule.endpoint in skip:
                continue
            args = list(rule.arguments)
            if len(args) > 1 or (args and type(rule._converters[args[0]]).__name__ != "IntegerConverter"):
                continue
            urls = [rule.rule] if not args else [re.sub(r"<int:\w+>", str(i), rule.rule) for i in (1, 2, 3)]
            for url in urls:
                status = client.get(url).status_code
                if status >= 500:
                    failures.append((url, status))
    finally:
        seeded.config["PROPAGATE_EXCEPTIONS"] = None
    assert not failures, failures
