"""E-mail templates, sending over SMTP and the sent log."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import email_sender
from core import (
    _parse_int,
    app,
)
from models import (
    Company,
    EmailLog,
    EmailTemplate,
    Payment,
    db,
)
from i18n import _

# ═══════════════════════════════════════════════════════════════
#  EMAIL (SZABLONY, WYSYŁKA, LOG)
# ═══════════════════════════════════════════════════════════════

@app.route("/emails/templates")
def emails_templates_list():
    templates = EmailTemplate.query.order_by(EmailTemplate.name).all()
    return render_template("emails/templates_list.html", templates=templates)


@app.route("/emails/templates/new", methods=["GET", "POST"])
def email_template_new():
    if request.method == "POST":
        t = EmailTemplate(
            key=request.form.get("key", "").strip(),
            name=request.form.get("name", "").strip(),
            subject_template=request.form.get("subject_template", "").strip(),
            body_template=request.form.get("body_template", "").strip(),
            placeholders_doc=request.form.get("placeholders_doc", "").strip(),
        )
        if not t.key:
            flash(_("Klucz szablonu (np. welcome) jest wymagany."), "danger")
            return redirect(url_for("email_template_new"))
        db.session.add(t)
        db.session.commit()
        flash(_("Szablon dodany."), "success")
        return redirect(url_for("emails_templates_list"))
    return render_template("emails/template_form.html", template=None)


@app.route("/emails/templates/<int:id>/edit", methods=["GET", "POST"])
def email_template_edit(id):
    t = db.get_or_404(EmailTemplate, id)
    if request.method == "POST":
        t.name = request.form.get("name", t.name).strip()
        t.subject_template = request.form.get("subject_template", "").strip()
        t.body_template = request.form.get("body_template", "").strip()
        t.placeholders_doc = request.form.get("placeholders_doc", "").strip()
        db.session.commit()
        flash(_("Szablon zapisany."), "success")
        return redirect(url_for("emails_templates_list"))
    return render_template("emails/template_form.html", template=t)


@app.route("/emails/templates/<int:id>/delete", methods=["POST"])
def email_template_delete(id):
    t = db.get_or_404(EmailTemplate, id)
    db.session.delete(t)
    db.session.commit()
    flash(_("Szablon usunięty."), "success")
    return redirect(url_for("emails_templates_list"))


@app.route("/companies/<int:company_id>/email/compose", methods=["GET", "POST"])
def email_compose(company_id):
    company = db.get_or_404(Company, company_id)
    template_key = request.args.get("template") or request.form.get("template_key", "")
    payment_id = _parse_int(request.args.get("payment_id") or request.form.get("payment_id"))

    ctx_payment = db.session.get(Payment, payment_id) if payment_id else None
    latest_audit = company.latest_audit

    if request.method == "POST":
        to = request.form.get("to_address", "").strip() or company.contact_email
        subject = request.form.get("subject", "").strip()
        body = request.form.get("body", "").strip()
        cc = request.form.get("cc", "").strip()
        bcc = request.form.get("bcc", "").strip()
        if not to or not subject or not body:
            flash(_("Adresat, temat i treść są wymagane."), "danger")
            return redirect(url_for("email_compose", company_id=company_id, template=template_key))
        ok, msg = email_sender.send_email(
            to_address=to, subject=subject, body_html=body,
            cc=cc, bcc=bcc, company_id=company_id, template_key=template_key,
        )
        if ok:
            flash(_("Wiadomość wysłana do %(to)s.", to=to), "success")
        else:
            flash(_("Nie udało się wysłać: %(error)s", error=msg), "danger")
        return redirect(url_for("company_detail", id=company_id) + "#emails")

    # GET - render template
    ctx = email_sender.build_context(company=company, payment=ctx_payment, audit=latest_audit)
    subject, body = ("", "")
    if template_key:
        subject, body = email_sender.render_email_template(template_key, ctx)
    templates = EmailTemplate.query.order_by(EmailTemplate.name).all()
    payments = Payment.query.filter_by(company_id=company_id).order_by(Payment.issued_at.desc()).all()
    return render_template("emails/compose.html", company=company, templates=templates,
                           template_key=template_key, subject=subject or "", body=body or "",
                           payments=payments, payment_id=payment_id)


@app.route("/emails/log")
def emails_log():
    logs = EmailLog.query.order_by(EmailLog.sent_at.desc()).limit(200).all()
    return render_template("emails/log.html", logs=logs)
