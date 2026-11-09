"""Main create / update / delete flows through the HTML forms (what a user clicks, end to end)."""

from datetime import date, timedelta


def test_company_create_and_delete(client, seeded):
    from models import Company, db

    r = client.post("/companies/new", data={
        "name": "Testowa Kwiaciarnia", "industry": "kwiaciarnia", "pipeline_stage": "lead",
        "phone": "+48 500 000 009", "website": "kwiaciarnia.example", "contact_email": "biuro@kwiaciarnia.example",
    })
    assert r.status_code == 302
    with seeded.app_context():
        c = Company.query.filter_by(name="Testowa Kwiaciarnia").one()
        cid = c.id
        assert c.pipeline_stage == "lead" and c.contact_email == "biuro@kwiaciarnia.example"
    assert f"/companies/{cid}" in r.headers["Location"]

    assert client.post(f"/companies/{cid}/delete").status_code == 302
    with seeded.app_context():
        assert db.session.get(Company, cid) is None


def test_task_create_and_mark_done(client, seeded):
    from models import Task, db

    deadline = (date.today() + timedelta(days=3)).isoformat()
    r = client.post("/tasks/new", data={"title": "Przygotować ofertę testową", "priority": "high",
                                        "status": "todo", "deadline": deadline})
    assert r.status_code == 302
    with seeded.app_context():
        t = Task.query.filter_by(title="Przygotować ofertę testową").one()
        tid = t.id
        assert t.priority == "high" and t.deadline.isoformat() == deadline

    assert client.post(f"/tasks/{tid}/status", data={"status": "done"}).status_code in (200, 302)
    with seeded.app_context():
        t = db.session.get(Task, tid)
        assert t.status == "done" and t.done_at is not None


def test_payment_create_computes_gross(client, seeded):
    from models import Company, Payment

    with seeded.app_context():
        cid = Company.query.first().id
    r = client.post("/finances/payments/new", data={
        "company_id": str(cid), "title": "Audyt SEO - test", "amount_net": "1000", "vat_rate": "23",
        "kind": "one_time", "status": "unpaid", "issued_at": date.today().isoformat(),
        "due_at": (date.today() + timedelta(days=14)).isoformat(),
    })
    assert r.status_code == 302
    with seeded.app_context():
        p = Payment.query.filter_by(title="Audyt SEO - test").one()
        assert p.amount_net == 1000 and p.amount_gross == 1230.0
        assert p.payment_number and p.payment_number.startswith("P-")


def test_note_with_html_is_stored_but_rendered_safely(client, seeded):
    from models import Note

    r = client.post("/notes/new", data={"title": "Notatka XSS", "content": "**ważne** <script>alert(1)</script>",
                                        "scope": "personal", "note_type": "general"})
    assert r.status_code == 302
    with seeded.app_context():
        assert Note.query.filter_by(title="Notatka XSS").one()
    html = client.get("/notes").get_data(as_text=True)
    assert "<script>alert(1)</script>" not in html
