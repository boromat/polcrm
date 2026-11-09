"""Companies (CRM), company card and the sales pipeline."""

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    _parse_date,
    _parse_float,
    _parse_int,
    app,
)
from i18n import _
from models import (
    PIPELINE_STAGES,
    Audit,
    ClientCredential,
    ClientFile,
    Company,
    ContentPost,
    Contract,
    EmailLog,
    EmailTemplate,
    GaSnapshot,
    GscSnapshot,
    Note,
    Offer,
    Package,
    Payment,
    Project,
    Task,
    Visit,
    Whiteboard,
    db,
    delete_company,
)

# ── Companies ─────────────────────────────────────────────────

@app.route("/companies")
def companies_list():
    q = request.args.get("q", "").strip()
    stage = request.args.get("stage", "")
    industry = request.args.get("industry", "")

    query = Company.query
    if q:
        query = query.filter(
            Company.name.ilike(f"%{q}%") | Company.address.ilike(f"%{q}%")
        )
    if stage:
        query = query.filter_by(pipeline_stage=stage)
    if industry:
        query = query.filter_by(industry=industry)

    companies = query.order_by(Company.updated_at.desc()).all()
    industries = db.session.query(Company.industry).filter(Company.industry != "").distinct().all()
    return render_template(
        "companies/list.html",
        companies=companies,
        stages=PIPELINE_STAGES,
        industries=[i[0] for i in industries],
        q=q, stage=stage, industry_filter=industry,
    )


@app.route("/companies/new", methods=["GET", "POST"])
def company_new():
    if request.method == "POST":
        c = Company(
            name=request.form.get("name", "").strip(),
            address=request.form.get("address", "").strip(),
            phone=request.form.get("phone", "").strip(),
            website=request.form.get("website", "").strip(),
            industry=request.form.get("industry", "").strip(),
            contact_person=request.form.get("contact_person", "").strip(),
            contact_email=request.form.get("contact_email", "").strip(),
            pipeline_stage="lead",
        )
        c.ensure_portal_token()
        db.session.add(c)
        db.session.commit()
        flash(_("Dodano firmę: %(name)s", name=c.name), "success")
        return redirect(url_for("company_detail", id=c.id))
    return render_template("companies/detail.html", company=None, is_new=True)


@app.route("/companies/<int:id>", methods=["GET", "POST"])
def company_detail(id):
    c = db.get_or_404(Company, id)
    if not c.portal_token:
        c.ensure_portal_token()
        db.session.commit()

    if request.method == "POST":
        c.name = request.form.get("name", c.name).strip()
        c.address = request.form.get("address", "").strip()
        c.phone = request.form.get("phone", "").strip()
        c.website = request.form.get("website", "").strip()
        c.industry = request.form.get("industry", "").strip()
        c.client_segment = request.form.get("client_segment", "").strip()
        c.main_services = request.form.get("main_services", "").strip()
        c.contact_person = request.form.get("contact_person", "").strip()
        c.contact_email = request.form.get("contact_email", "").strip()
        c.pipeline_stage = request.form.get("pipeline_stage", c.pipeline_stage)
        c.next_action = request.form.get("next_action", "").strip()
        c.next_action_date = _parse_date(request.form.get("next_action_date", ""))
        c.ltv_potential = _parse_float(request.form.get("ltv_potential"))

        # Retainer fields
        c.is_retainer = "is_retainer" in request.form
        c.monthly_fee_net = _parse_float(request.form.get("monthly_fee_net"))
        c.billing_day = _parse_int(request.form.get("billing_day")) or 1
        c.retainer_started_at = _parse_date(request.form.get("retainer_started_at"))

        # Client legal data (for contracts)
        c.client_legal_name = request.form.get("client_legal_name", "").strip()
        c.client_nip = request.form.get("client_nip", "").strip()
        c.client_address = request.form.get("client_address", "").strip()

        # Google integrations
        c.gsc_site_url = request.form.get("gsc_site_url", "").strip()
        c.ga_property_id = request.form.get("ga_property_id", "").strip()

        # Results
        c.results_description = request.form.get("results_description", "").strip()
        c.results_calls_before = _parse_int(request.form.get("results_calls_before"))
        c.results_calls_after = _parse_int(request.form.get("results_calls_after"))
        c.results_visibility_before = request.form.get("results_visibility_before", "").strip()
        c.results_visibility_after = request.form.get("results_visibility_after", "").strip()
        c.results_reviews_before = _parse_int(request.form.get("results_reviews_before"))
        c.results_reviews_after = _parse_int(request.form.get("results_reviews_after"))

        db.session.commit()
        flash(_("Zapisano zmiany."), "success")
        return redirect(url_for("company_detail", id=c.id))

    notes = Note.query.filter_by(company_id=c.id, scope="company").order_by(Note.created_at.desc()).all()
    audits = Audit.query.filter_by(company_id=c.id).order_by(Audit.created_at.desc()).all()
    offers = Offer.query.filter_by(company_id=c.id).order_by(Offer.created_at.desc()).all()
    visits = Visit.query.filter_by(company_id=c.id).order_by(Visit.scheduled_at.desc()).all()
    packages = Package.query.filter_by(is_active=True).all()
    payments = Payment.query.filter_by(company_id=c.id).order_by(Payment.issued_at.desc()).all()
    projects = Project.query.filter_by(company_id=c.id).order_by(Project.created_at.desc()).all()
    content_posts = ContentPost.query.filter_by(company_id=c.id).order_by(ContentPost.deadline.desc().nullslast() if hasattr(ContentPost.deadline.desc(), 'nullslast') else ContentPost.deadline.desc()).all()
    credentials = ClientCredential.query.filter_by(company_id=c.id).order_by(ClientCredential.label).all()
    contracts = Contract.query.filter_by(company_id=c.id).order_by(Contract.created_at.desc()).all()
    files = ClientFile.query.filter_by(company_id=c.id).order_by(ClientFile.uploaded_at.desc()).all()
    email_log = EmailLog.query.filter_by(company_id=c.id).order_by(EmailLog.sent_at.desc()).limit(20).all()
    gsc_snapshot = GscSnapshot.query.filter_by(company_id=c.id).order_by(GscSnapshot.captured_at.desc()).first()
    ga_snapshot = GaSnapshot.query.filter_by(company_id=c.id).order_by(GaSnapshot.captured_at.desc()).first()
    tasks = Task.query.filter_by(company_id=c.id).order_by(Task.status, Task.deadline.asc()).all()
    email_templates = EmailTemplate.query.order_by(EmailTemplate.name).all()
    whiteboards = Whiteboard.query.filter_by(company_id=c.id).order_by(Whiteboard.updated_at.desc()).all()

    return render_template(
        "companies/detail.html",
        company=c, is_new=False, notes=notes, audits=audits,
        offers=offers, visits=visits, stages=PIPELINE_STAGES,
        packages=packages,
        payments=payments, projects=projects, content_posts=content_posts,
        credentials=credentials, contracts=contracts, files=files,
        email_log=email_log, gsc_snapshot=gsc_snapshot, ga_snapshot=ga_snapshot,
        tasks=tasks, email_templates=email_templates,
        whiteboards=whiteboards,
    )


@app.route("/companies/<int:id>/delete", methods=["POST"])
def company_delete(id):
    c = db.get_or_404(Company, id)
    name = c.name
    delete_company(c)
    db.session.commit()
    flash(_("Usunięto firmę: %(name)s", name=name), "success")
    return redirect(url_for("companies_list"))


# ── Pipeline ──────────────────────────────────────────────────

@app.route("/pipeline")
def pipeline():
    columns = {}
    for stage in PIPELINE_STAGES:
        columns[stage] = Company.query.filter_by(pipeline_stage=stage).order_by(Company.updated_at.desc()).all()
    labels = {
        "lead": _("Lead"), "audit": _("Audyt"), "contact": _("Kontakt"),
        "visit": _("Wizyta"), "offer": _("Oferta"), "client": _("Klient"),
    }
    return render_template("pipeline.html", columns=columns, stages=PIPELINE_STAGES, labels=labels)


@app.route("/api/pipeline/move", methods=["POST"])
def api_pipeline_move():
    data = request.get_json()
    company_id = data.get("company_id")
    new_stage = data.get("stage")
    if new_stage not in PIPELINE_STAGES:
        return jsonify({"error": "Invalid stage"}), 400
    c = db.session.get(Company, company_id)
    if not c:
        return jsonify({"error": "Company not found"}), 404
    c.pipeline_stage = new_stage
    db.session.commit()
    return jsonify({"ok": True})
