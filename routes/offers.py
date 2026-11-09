"""Service packages and offers."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    app,
)
from i18n import _
from models import (
    Company,
    Offer,
    Package,
    db,
    utcnow,
)

# ── Packages ──────────────────────────────────────────────────

@app.route("/packages", methods=["GET"])
def packages_list():
    packages = Package.query.all()
    return render_template("packages.html", packages=packages)


@app.route("/packages/<int:id>/edit", methods=["POST"])
def package_edit(id):
    p = db.get_or_404(Package, id)
    p.name = request.form.get("name", p.name).strip()
    p.description = request.form.get("description", "").strip()
    price = request.form.get("price", "0").strip()
    p.price = float(price) if price else 0
    dur = request.form.get("duration_days", "30").strip()
    p.duration_days = int(dur) if dur else 30
    p.deliverables = [d.strip() for d in request.form.get("deliverables", "").split("\n") if d.strip()]
    p.expected_results = [r.strip() for r in request.form.get("expected_results", "").split("\n") if r.strip()]
    p.payment_variants = [v.strip() for v in request.form.get("payment_variants", "").split("\n") if v.strip()]
    p.is_active = "is_active" in request.form
    db.session.commit()
    flash(_("Pakiet %(name)s zapisany.", name=p.name), "success")
    return redirect(url_for("packages_list"))


# ── Offers ────────────────────────────────────────────────────

@app.route("/companies/<int:company_id>/offers/new", methods=["POST"])
def offer_new(company_id):
    db.get_or_404(Company, company_id)
    o = Offer(
        company_id=company_id,
        package_id=int(request.form.get("package_id")),
        audit_id=request.form.get("audit_id") or None,
        custom_price=float(request.form.get("custom_price")) if request.form.get("custom_price") else None,
        custom_notes=request.form.get("custom_notes", "").strip(),
        status="draft",
    )
    db.session.add(o)
    c = db.session.get(Company, company_id)
    if c.pipeline_stage in ("audit", "contact", "visit"):
        c.pipeline_stage = "offer"
    db.session.commit()
    flash(_("Utworzono ofertę."), "success")
    return redirect(url_for("company_detail", id=company_id))


@app.route("/offers/<int:id>/status", methods=["POST"])
def offer_status(id):
    o = db.get_or_404(Offer, id)
    new_status = request.form.get("status", o.status)
    o.status = new_status
    if new_status == "sent" and not o.sent_at:
        o.sent_at = utcnow()
    if new_status == "accepted":
        o.accepted_at = utcnow()
        c = db.session.get(Company, o.company_id)
        if c:
            c.pipeline_stage = "client"
    db.session.commit()
    flash(_("Status oferty zmieniony."), "success")
    return redirect(url_for("company_detail", id=o.company_id))
