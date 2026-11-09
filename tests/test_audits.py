"""Audits: the edit form, the HTML report and the PDF report for the demo audit, in both languages.

The audit pages require a Google API key (core.check_settings); their GET views make no calls to
Google, so a placeholder key is enough here.
"""

import pytest


@pytest.fixture()
def audit_id(seeded):
    from models import Audit, Settings, db

    with seeded.app_context():
        settings = Settings.get()
        saved = settings.google_api_key
        settings.google_api_key = "placeholder-key-for-tests"
        db.session.commit()
        audit = Audit.query.order_by(Audit.id).first()
        assert audit is not None, "the demo seed has an audit"
        audit_id = audit.id
    yield audit_id
    with seeded.app_context():
        Settings.get().google_api_key = saved
        db.session.commit()


def test_audit_pages_need_a_google_key(client, seeded):
    from models import Audit

    with seeded.app_context():
        audit_id = Audit.query.order_by(Audit.id).first().id
    r = client.get(f"/audits/{audit_id}/report")
    assert r.status_code == 302 and "/settings" in r.headers["Location"]


@pytest.mark.parametrize("lang", ["pl", "en"])
def test_audit_edit_report_and_pdf_render(client, audit_id, lang):
    client.post(f"/jezyk/{lang}")
    try:
        edit = client.get(f"/audits/{audit_id}/edit")
        assert edit.status_code == 200
        report = client.get(f"/audits/{audit_id}/report")
        assert report.status_code == 200
        html = report.get_data(as_text=True)
        assert "Wolna strona na telefonie" in html  # top problem from the seed (user data, not translated)
        assert ("Audyt marketingowy" in html) == (lang == "pl")
        pdf = client.get(f"/audits/{audit_id}/pdf")
        assert pdf.status_code == 200 and pdf.data[:5] == b"%PDF-" and len(pdf.data) > 5000
    finally:
        client.post("/jezyk/pl")


def test_audit_edit_saves_checklist_and_plan(client, audit_id, seeded):
    """Unticked boxes are saved as False, empty list fields are dropped, the overall score is the mean."""
    from models import Audit, db

    r = client.post(f"/audits/{audit_id}/edit", data={
        "ws_visible_cta": "on", "problem_1": "Brak rezerwacji online", "problem_2": "",
        "action_1": "Przycisk rezerwacji", "status": "ready",
    })
    assert r.status_code == 302
    with seeded.app_context():
        audit = db.session.get(Audit, audit_id)
        assert audit.section_website["checklist"]["visible_cta"] is True
        assert audit.section_website["checklist"]["fast_loading"] is False
        assert audit.top_problems == ["Brak rezerwacji online"]
        assert audit.section_plan90["actions"] == ["Przycisk rezerwacji"]
        assert audit.score_overall == 3.0  # (3 + 4 + 4 + 2 + 2) / 5 from the seed
