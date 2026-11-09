"""Polish/English interface: every marked string is translated, the English UI has no Polish left."""

import ast
import json
import re
from pathlib import Path

import i18n

ROOT = Path(__file__).resolve().parents[1]
PLACEHOLDER = re.compile(r"%\((\w+)\)s")
# _('...') / _("...") in templates; the message is a plain literal (no concatenation)
TEMPLATE_CALL = re.compile(r"""\b_\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")""")
JS_CALL = re.compile(r"""\bt\(\s*(?:'((?:[^'\\]|\\.)*)'|"((?:[^"\\]|\\.)*)")\s*\)""")


def _template_messages():
    out = {}
    for path in (ROOT / "templates").rglob("*.html"):
        for m in TEMPLATE_CALL.finditer(path.read_text(encoding="utf-8")):
            msg = m.group(1) if m.group(1) is not None else m.group(2)
            out.setdefault(msg.replace("\\'", "'").replace('\\"', '"'), str(path.relative_to(ROOT)))
    return out


def _python_messages():
    out = {}
    files = [p for p in ROOT.glob("*.py")] + list((ROOT / "routes").glob("*.py"))
    for path in files:
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "_"
                    and node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                out.setdefault(node.args[0].value, str(path.relative_to(ROOT)))
    return out


def _js_messages():
    out = {}
    for path in (ROOT / "static" / "js").glob("*.js"):
        for m in JS_CALL.finditer(path.read_text(encoding="utf-8")):
            msg = m.group(1) if m.group(1) is not None else m.group(2)
            out.setdefault(msg.replace("\\'", "'"), str(path.relative_to(ROOT)))
    return out


def test_every_marked_string_has_an_english_translation():
    catalog = i18n.load_catalog("en")
    missing = [f"{where}: {msg!r}" for msg, where in {**_template_messages(), **_python_messages()}.items()
               if msg not in catalog]
    assert not missing, f"{len(missing)} without translation:\n" + "\n".join(sorted(missing)[:60])


def test_js_strings_are_in_js_catalog():
    js = json.loads((ROOT / "translations" / "en" / "js.json").read_text(encoding="utf-8"))
    missing = [f"{where}: {msg!r}" for msg, where in _js_messages().items() if msg not in js]
    assert not missing, "\n".join(sorted(missing)[:60])


def test_translations_keep_placeholders():
    catalog = i18n.load_catalog("en")
    broken = [k for k, v in catalog.items() if set(PLACEHOLDER.findall(k)) != set(PLACEHOLDER.findall(v))]
    assert not broken, broken[:20]


def test_language_switch_and_dates(client, seeded):
    from datetime import date

    from models import User, db

    assert i18n.format_long_date(date(2026, 4, 17), "pl") == "Piątek, 17 kwietnia 2026"
    assert i18n.format_long_date(date(2026, 4, 17), "en") == "Friday, April 17, 2026"
    r = client.post("/jezyk/en")
    assert r.status_code == 302
    html = client.get("/").get_data(as_text=True)
    assert '<html lang="en"' in html
    with seeded.app_context():
        assert User.query.filter_by(email="anna@example.com").one().language == "en"
    client.post("/jezyk/pl")
    assert '<html lang="pl"' in client.get("/").get_data(as_text=True)
    with seeded.app_context():
        u = User.query.filter_by(email="anna@example.com").one()
        u.language = "pl"
        db.session.commit()


def test_english_interface_has_no_polish_left(seeded):
    import sys

    sys.path.insert(0, str(ROOT / "scripts"))
    import i18n_check
    from conftest import login
    from models import User, db

    with seeded.app_context():
        ola = User.query.filter_by(email="ola@example.com").one()
        ola.language = "en"
        db.session.commit()
    seeded.config["PROPAGATE_EXCEPTIONS"] = False
    try:
        c = seeded.test_client()
        login(c, "ola@example.com")
        report = i18n_check.find_leftovers(seeded, c)
    finally:
        seeded.config["PROPAGATE_EXCEPTIONS"] = None
        with seeded.app_context():
            ola = User.query.filter_by(email="ola@example.com").one()
            ola.language = "pl"
            db.session.commit()
    lines = [f"{p}: {t[:120]}" for p, texts in sorted(report.items()) for t in texts]
    assert not lines, f"{len(lines)} Polish texts in the English UI:\n" + "\n".join(lines[:80])


def test_manifest_is_public_and_follows_the_language(seeded):
    c = seeded.test_client()
    r = c.get("/manifest.webmanifest", headers={"Accept-Language": "en-US,en;q=0.9"})
    assert r.status_code == 200 and r.mimetype == "application/manifest+json"
    data = r.get_json()
    assert data["name"] == "PolCRM" and data["lang"] == "en"
    assert {s["name"] for s in data["shortcuts"]} >= {"New task", "Finance"}
    c.set_cookie(i18n.LANG_COOKIE, "pl")
    assert c.get("/manifest.webmanifest").get_json()["shortcuts"][0]["name"] == "Nowe zadanie"


def test_first_admin_keeps_the_setup_language(seeded):
    from models import User, db

    with seeded.app_context():
        admins = User.query.filter_by(role="admin").all()
        ids = [u.id for u in admins]
        for u in admins:
            u.role = "member"
        db.session.commit()
    try:
        c = seeded.test_client()
        c.set_cookie(i18n.LANG_COOKIE, "en")
        assert "Create administrator account" in c.get("/setup").get_data(as_text=True)
        c.post("/setup", data={"name": "First Admin", "email": "first@example.com",
                               "password": "first-admin-pass", "password2": "first-admin-pass"})
        with seeded.app_context():
            assert User.query.filter_by(email="first@example.com").one().language == "en"
        assert '<html lang="en"' in c.get("/").get_data(as_text=True)
    finally:
        with seeded.app_context():
            for uid in ids:
                db.session.get(User, uid).role = "admin"
            first = User.query.filter_by(email="first@example.com").first()
            if first:
                db.session.delete(first)
            db.session.commit()


def test_profile_language_change_confirms_in_the_new_language(client):
    r = client.post("/profil", data={"name": "Anna", "language": "en"}, follow_redirects=True)
    try:
        assert "Profile saved." in r.get_data(as_text=True)
    finally:
        client.post("/jezyk/pl")


def test_activity_shows_labels_not_codes(client, seeded):
    from models import AuditLog, Task, db

    with seeded.app_context():
        task = Task.query.first()
        db.session.add(AuditLog(table_name="tasks", record_id=task.id, action="status_change", field="status",
                                old_value="todo", new_value="in_progress"))
        db.session.commit()
        task_id = task.id
    html = client.get(f"/tasks/{task_id}").get_data(as_text=True)
    assert "Do zrobienia" in html and "W trakcie" in html and "in_progress" not in html.split("timeline-wrap")[-1]
    client.post("/jezyk/en")
    try:
        page = client.get("/aktywnosci").get_data(as_text=True)
        assert ">Status change<" in page and ">Tasks<" in page
        assert "In progress" in client.get(f"/tasks/{task_id}").get_data(as_text=True)
    finally:
        client.post("/jezyk/pl")
