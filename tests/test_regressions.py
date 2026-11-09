"""Regression tests for bugs fixed while preparing the public version (see CHANGELOG.md)."""

import app  # noqa: F401  (registers routes)
import core as app_module


def test_vat_zero_is_not_replaced_by_23():
    assert app_module._vat_rate("0") == 0.0
    assert app_module._vat_rate("8") == 8.0
    assert app_module._vat_rate("") == 23.0
    assert app_module._vat_rate(None) == 23.0
    assert app_module._vat_rate("abc") == 23.0


def test_knowledge_article_html_is_sanitised(client, seeded):
    from models import KnowledgeArticle, db

    with seeded.app_context():
        a = KnowledgeArticle(title="XSS", category="Test",
                             body="**ok** <script>alert(1)</script> <img src=x onerror=alert(2)>")
        db.session.add(a)
        db.session.commit()
        aid = a.id
    html = client.get(f"/knowledge/{aid}").get_data(as_text=True)
    assert "<strong>ok</strong>" in html
    assert "<script>alert(1)</script>" not in html
    assert "onerror" not in html


def test_settings_tabs_do_not_overwrite_each_other(client, seeded):
    """'Ogólne' and 'Finanse' used to post the same section, so saving one blanked the other."""
    from models import Settings

    client.post("/settings", data={"section": "general", "google_api_key": "AIza-test-not-real",
                                   "agency_name": "Agencja Testowa"})
    client.post("/settings", data={"section": "finance", "agency_nip": "1234567890",
                                   "default_vat_rate": "0"})
    # an empty secret field keeps the saved key (the page no longer prints it)
    client.post("/settings", data={"section": "general", "google_api_key": "",
                                   "agency_name": "Agencja Testowa"})
    with seeded.app_context():
        s = Settings.get()
        assert s.google_api_key == "AIza-test-not-real"
        assert s.agency_name == "Agencja Testowa"
        assert s.agency_nip == "1234567890"
        assert s.default_vat_rate == 0.0
    page = client.get("/settings").get_data(as_text=True)
    assert "AIza-test-not-real" not in page
    with seeded.app_context():
        from models import db

        s = Settings.get()
        s.google_api_key = ""
        s.default_vat_rate = 23.0
        db.session.commit()


def test_dashboard_links_use_the_scope_the_task_list_reads(client):
    html = client.get("/").get_data(as_text=True)
    assert "/tasks?range=" not in html and "/tasks?status=" not in html
    assert "/tasks?scope=week" in html


def test_company_delete_form_is_not_nested(client, seeded):
    from models import Company

    with seeded.app_context():
        cid = Company.query.first().id
    html = client.get(f"/companies/{cid}").get_data(as_text=True)
    assert 'form="delete-company-form"' in html
    assert 'id="delete-company-form"' in html


def test_contract_pdf_with_polish_characters(tmp_path):
    from contract_pdf import generate_contract_pdf

    out = tmp_path / "umowa.pdf"
    generate_contract_pdf("Umowa o świadczenie usług", "§ 1. Zażółć gęślą jaźń.\n\n§ 2. Płatność.",
                          str(out), agency_name="Agencja")
    assert out.read_bytes()[:5] == b"%PDF-"


def test_audit_pdf(seeded):
    from models import Audit, Company, Settings, db
    from pdf_report import generate_audit_pdf

    with seeded.app_context():
        company = Company.query.first()
        audit = Audit(company_id=company.id, score_visibility=4, score_offer=3, score_trust=5,
                      score_conversion=2, score_analytics=3, score_overall=3.4)
        db.session.add(audit)
        db.session.commit()
        path = generate_audit_pdf(audit, company, [], Settings.get())
    with open(path, "rb") as f:
        assert f.read(5) == b"%PDF-"


def test_logout_only_by_post(seeded):
    from conftest import login

    c = seeded.test_client()
    login(c)
    assert c.get("/wyloguj").status_code == 405  # a GET link from another site cannot log you out
    r = c.post("/wyloguj")
    assert r.status_code == 302 and "/login" in r.headers["Location"]
    assert "/login" in c.get("/").headers["Location"]  # the session is really gone


def test_query_indexes_exist_and_are_used(seeded):
    from sqlalchemy import inspect, text

    from models import db

    with seeded.app_context():
        insp = inspect(db.engine)
        names = {ix["name"] for table in ("tasks", "payments", "companies") for ix in insp.get_indexes(table)}
        assert {"ix_tasks_deadline", "ix_payments_status_due_at", "ix_companies_pipeline_stage"} <= names
        if db.engine.dialect.name == "sqlite":  # query plans are engine specific
            plan = " ".join(r[3] for r in db.session.execute(text(
                "EXPLAIN QUERY PLAN SELECT * FROM tasks WHERE deadline IS NOT NULL AND deadline < '2026-01-01'")))
            assert "ix_tasks_deadline" in plan


def test_call_model_uses_configured_endpoint(monkeypatch):
    """OPENROUTER_URL lets the assistant talk to any OpenAI-compatible gateway (e.g. a local model)."""
    import ai_assistant

    seen = {}

    class _Resp:
        status_code = 200

        @staticmethod
        def json():
            return {"choices": [{"message": {"content": "ok"}}]}

    def fake_post(url, json=None, headers=None, timeout=None):
        seen.update(url=url, model=json["model"], tools=len(json["tools"]), auth=headers["Authorization"])
        return _Resp()

    monkeypatch.setattr(ai_assistant, "OPENROUTER_URL", "http://127.0.0.1:4000/v1/chat/completions")
    monkeypatch.setattr(ai_assistant.requests, "post", fake_post)
    out = ai_assistant.call_model([{"role": "user", "content": "hej"}], model="test/model", api_key="test-key-not-real")
    assert out["choices"][0]["message"]["content"] == "ok"
    assert seen == {"url": "http://127.0.0.1:4000/v1/chat/completions", "model": "test/model",
                    "tools": 12, "auth": "Bearer test-key-not-real"}


def test_settings_form_shows_saved_zero_vat(client, seeded):
    from models import Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.default_vat_rate = 0.0
        db.session.commit()
    html = client.get("/settings").get_data(as_text=True)
    assert 'name="default_vat_rate" value="0.0"' in html
    with seeded.app_context():
        s = Settings.get()
        s.default_vat_rate = 23.0
        db.session.commit()


def test_every_pinned_cdn_asset_has_subresource_integrity():
    """jsDelivr files are pinned to a version, so each tag must carry an integrity hash."""
    import re
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "templates"
    missing = []
    for path in root.rglob("*.html"):
        for tag in re.findall(r"<(?:script|link)[^>]*cdn\.jsdelivr\.net[^>]*>", path.read_text(encoding="utf-8")):
            if 'integrity="sha384-' not in tag or 'crossorigin="anonymous"' not in tag:
                missing.append(f"{path.name}: {tag[:80]}")
    assert not missing, missing


def test_tailwind_is_served_locally_not_from_the_play_cdn(client):
    """The Play CDN compiled CSS in the browser (not for production, no SRI possible)."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[1]
    css = (root / "static/css/tailwind.css").read_text(encoding="utf-8")
    for cls in (".bg-accent", ".text-gray-400", ".rounded-lg", ".grid-cols-2"):
        assert cls in css, cls  # classes used across templates are in the built file
    for path in (root / "templates").rglob("*.html"):
        assert "cdn.tailwindcss.com" not in path.read_text(encoding="utf-8"), path.name
    html = client.get("/companies").get_data(as_text=True)
    assert "/static/css/tailwind.css" in html
    assert client.get("/static/css/tailwind.css").status_code == 200
