"""Contracts (template -> PDF -> client file), file uploads with versions, whiteboards and their API."""

import io

# ── contracts ───────────────────────────────────────────────────


def _company_id(seeded):
    from models import Company

    with seeded.app_context():
        return Company.query.filter(Company.name.like("%Dentysta%")).first().id


def test_contract_generated_as_pdf_and_downloadable(client, seeded):
    from models import ClientFile, Contract, db

    cid = _company_id(seeded)
    assert client.get(f"/companies/{cid}/contracts/new").status_code == 200
    r = client.post(f"/companies/{cid}/contracts/new", data={
        "template_key": "seo_retainer", "name": "Umowa SEO test", "monthly_fee_net": "1500",
        "billing_day": "10", "notes": "test",
    })
    assert r.status_code == 302 and "#contracts" in r.headers["Location"]
    with seeded.app_context():
        contract = Contract.query.filter_by(name="Umowa SEO test").one()
        pdf = db.session.get(ClientFile, contract.generated_pdf_file_id)
        assert contract.status == "draft" and pdf.mime == "application/pdf" and pdf.size_bytes > 1000
        contract_id, file_id = contract.id, pdf.id

    download = client.get(f"/files/{file_id}/download")
    assert download.status_code == 200 and download.data[:5] == b"%PDF-"

    assert client.post(f"/contracts/{contract_id}/status", data={"status": "signed"}).status_code == 302
    with seeded.app_context():
        assert db.session.get(Contract, contract_id).status == "signed"
    assert client.post(f"/contracts/{contract_id}/delete").status_code == 302
    with seeded.app_context():
        assert db.session.get(Contract, contract_id) is None


def test_two_contracts_in_the_same_second_get_separate_files(client, seeded, monkeypatch):
    """The PDF name has a seconds timestamp; the file on disk must still be unique per contract."""
    from datetime import datetime as real_datetime

    import routes.contracts as contracts_routes
    from models import ClientFile, Contract, db

    class FrozenDatetime(real_datetime):
        @classmethod
        def now(cls, tz=None):
            return real_datetime(2026, 5, 4, 10, 0, 0)

    monkeypatch.setattr(contracts_routes, "datetime", FrozenDatetime)
    cid = _company_id(seeded)
    for name in ("Umowa A", "Umowa B"):
        client.post(f"/companies/{cid}/contracts/new", data={
            "template_key": "seo_retainer", "name": name, "monthly_fee_net": "1000", "billing_day": "5"})
    with seeded.app_context():
        files = [db.session.get(ClientFile, c.generated_pdf_file_id)
                 for c in Contract.query.filter(Contract.name.in_(["Umowa A", "Umowa B"]))]
        assert len(files) == 2 and files[0].stored_path != files[1].stored_path
        assert files[0].filename == files[1].filename  # the readable download name stays the same
        for c in Contract.query.filter(Contract.name.in_(["Umowa A", "Umowa B"])).all():
            client.post(f"/contracts/{c.id}/delete")


def test_contract_needs_a_valid_template(client, seeded):
    from models import Contract

    cid = _company_id(seeded)
    with seeded.app_context():
        before = Contract.query.count()
    r = client.post(f"/companies/{cid}/contracts/new", data={"template_key": "does-not-exist"})
    assert r.status_code == 302 and "/contracts/new" in r.headers["Location"]
    with seeded.app_context():
        assert Contract.query.count() == before


def test_file_upload_versions_and_safe_storage(client, seeded):
    from models import ClientFile, db

    cid = _company_id(seeded)
    for content in (b"first version", b"second version"):
        r = client.post(f"/companies/{cid}/files/upload", data={
            "file": (io.BytesIO(content), "../../oferta.txt"), "label": "Oferta test", "category": "other",
        }, content_type="multipart/form-data")
        assert r.status_code == 302
    with seeded.app_context():
        files = ClientFile.query.filter_by(label="Oferta test").order_by(ClientFile.version).all()
        assert [f.version for f in files] == [1, 2]
        # stored under a random name inside the company folder, never the client-supplied path
        assert all(f.stored_path.startswith(f"uploads/{cid}/") and ".." not in f.stored_path for f in files)
        latest = files[-1].id
    assert client.get(f"/files/{latest}/download").data == b"second version"
    assert client.post(f"/files/{latest}/delete").status_code == 302
    with seeded.app_context():
        assert db.session.get(ClientFile, latest) is None
        for f in ClientFile.query.filter_by(label="Oferta test").all():
            db.session.delete(f)
        db.session.commit()


# ── whiteboards ─────────────────────────────────────────────────


def test_whiteboard_drawing_api(client, seeded):
    from models import Whiteboard, db

    r = client.post("/tablica/nowa", data={"name": "Szkic testowy"})
    assert r.status_code == 302
    bid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    assert client.get(f"/tablica/{bid}").status_code == 200

    ok = client.post(f"/api/tablica/{bid}/stroke", json={"tool": "pen", "points": [[0, 0], [10, 12]], "color": "#111111"})
    assert ok.status_code == 200 and ok.get_json()["ok"]
    sid = ok.get_json()["id"]
    assert client.post(f"/api/tablica/{bid}/stroke", json={"tool": "laser", "points": [[0, 0]]}).status_code == 400
    assert client.post(f"/api/tablica/{bid}/stroke", json={"tool": "pen", "points": "nope"}).status_code == 400

    state = client.get(f"/api/tablica/{bid}/state").get_json()
    assert any(s["id"] == sid for s in state["strokes"])

    assert client.post(f"/api/tablica/{bid}/stroke/{sid}/delete").status_code == 200
    state = client.get(f"/api/tablica/{bid}/state").get_json()
    assert all(s["id"] != sid for s in state["strokes"])

    assert client.post(f"/tablica/{bid}/delete").status_code == 302
    with seeded.app_context():
        assert db.session.get(Whiteboard, bid) is None
