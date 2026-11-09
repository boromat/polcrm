"""Contract templates, contract PDFs and client files."""

import mimetypes
import uuid
from datetime import date, datetime
from pathlib import Path

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

import email_sender
from core import (
    BASE_DIR,
    CONTRACTS_DIR,
    UPLOADS_DIR,
    _log_audit,
    _parse_float,
    _safe_referrer,
    app,
)
from models import (
    ClientFile,
    Company,
    Contract,
    ContractTemplate,
    Settings,
    db,
)
from i18n import _

# ═══════════════════════════════════════════════════════════════
#  UMOWY I PLIKI
# ═══════════════════════════════════════════════════════════════

@app.route("/contracts/templates")
def contracts_templates_list():
    templates = ContractTemplate.query.order_by(ContractTemplate.name).all()
    return render_template("contracts/templates_list.html", templates=templates)


@app.route("/contracts/templates/<int:id>/edit", methods=["GET", "POST"])
def contract_template_edit(id):
    t = db.get_or_404(ContractTemplate, id)
    if request.method == "POST":
        t.name = request.form.get("name", t.name).strip()
        t.body_template = request.form.get("body_template", "").strip()
        t.placeholders_doc = request.form.get("placeholders_doc", "").strip()
        db.session.commit()
        flash(_("Szablon umowy zapisany."), "success")
        return redirect(url_for("contracts_templates_list"))
    return render_template("contracts/template_form.html", template=t)


@app.route("/companies/<int:company_id>/contracts/new", methods=["GET", "POST"])
def contract_new(company_id):
    company = db.get_or_404(Company, company_id)
    if request.method == "POST":
        from contract_pdf import generate_contract_pdf
        template_key = request.form.get("template_key", "").strip()
        tmpl = ContractTemplate.query.filter_by(key=template_key).first()
        if not tmpl:
            flash(_("Wybierz poprawny szablon umowy."), "danger")
            return redirect(url_for("contract_new", company_id=company_id))

        extra = {
            "today": date.today().strftime("%d.%m.%Y"),
            "monthly_fee_net": request.form.get("monthly_fee_net", "")
                               or (f"{company.monthly_fee_net:.2f}" if company.monthly_fee_net else "-"),
            "monthly_fee_gross": request.form.get("monthly_fee_gross", ""),
            "billing_day": request.form.get("billing_day", str(company.billing_day or 1)),
            "extra_clauses": request.form.get("extra_clauses", "").strip(),
            "domain": request.form.get("domain", company.website or "").strip(),
            "total_net": request.form.get("total_net", ""),
            "total_gross": request.form.get("total_gross", ""),
            "payment_stage_1": request.form.get("payment_stage_1", ""),
            "payment_stage_2": request.form.get("payment_stage_2", ""),
            "payment_stage_3": request.form.get("payment_stage_3", ""),
            "deadline": request.form.get("deadline", ""),
            "main_contract_date": request.form.get("main_contract_date", ""),
            "duration_years": request.form.get("duration_years", "3"),
            "penalty": request.form.get("penalty", "10 000"),
        }
        # Compute gross from net if possible - VAT rate from Settings (0 when the agency is not a VAT payer)
        s = Settings.get()
        if s.company_vat_payer is False:
            vat_rate = 0.0
        else:
            vat_rate = s.default_vat_rate if s.default_vat_rate is not None else 23.0
        vat_factor = 1 + vat_rate / 100
        mn = _parse_float(extra["monthly_fee_net"])
        if mn and not extra["monthly_fee_gross"]:
            extra["monthly_fee_gross"] = f"{mn * vat_factor:.2f}"
        tn = _parse_float(extra["total_net"])
        if tn and not extra["total_gross"]:
            extra["total_gross"] = f"{tn * vat_factor:.2f}"

        ctx = email_sender.build_context(company=company, extra=extra)
        rendered = email_sender.render_template_string(tmpl.body_template, ctx)

        # Save file
        safe_name = "".join(c if c.isalnum() else "_" for c in company.name)[:40]
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pdf_filename = f"umowa_{tmpl.key}_{safe_name}_{stamp}.pdf"
        # Unique on disk: two contracts generated in the same second must not share (overwrite) a file
        stored_name = f"{pdf_filename[:-4]}_{uuid.uuid4().hex[:8]}.pdf"
        target_path = CONTRACTS_DIR / stored_name
        generate_contract_pdf(tmpl.name, rendered, target_path, agency_name=s.agency_name)

        stored_rel = f"contracts/{stored_name}"
        cf = ClientFile(
            company_id=company_id,
            filename=pdf_filename,
            label=tmpl.name,
            stored_path=stored_rel,
            mime="application/pdf",
            size_bytes=target_path.stat().st_size,
            category="contract",
            version=1,
        )
        db.session.add(cf)
        db.session.flush()

        contract = Contract(
            company_id=company_id,
            template_key=template_key,
            name=request.form.get("name") or tmpl.name,
            content_rendered=rendered,
            generated_pdf_file_id=cf.id,
            status="draft",
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(contract)
        db.session.commit()
        flash(_("Umowa wygenerowana jako PDF."), "success")
        return redirect(url_for("company_detail", id=company_id) + "#contracts")

    templates = ContractTemplate.query.order_by(ContractTemplate.name).all()
    return render_template("contracts/new.html", company=company, templates=templates,
                           preset_template_key=request.args.get("template_key", ""))


@app.route("/contracts/<int:id>/status", methods=["POST"])
def contract_status(id):
    c = db.get_or_404(Contract, id)
    new = request.form.get("status")
    if new in ("draft", "sent", "signed", "archived"):
        c.status = new
        if new == "signed":
            c.signed_at = date.today()
        db.session.commit()
    return redirect(_safe_referrer(url_for("company_detail", id=c.company_id) + "#contracts"))


@app.route("/contracts/<int:id>/delete", methods=["POST"])
def contract_delete(id):
    c = db.get_or_404(Contract, id)
    company_id = c.company_id
    db.session.delete(c)
    db.session.commit()
    flash(_("Umowa usunięta."), "success")
    return redirect(url_for("company_detail", id=company_id) + "#contracts")


# -- Files (upload/download/versioning) --

@app.route("/companies/<int:company_id>/files/upload", methods=["POST"])
def file_upload(company_id):
    db.get_or_404(Company, company_id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash(_("Wybierz plik do wgrania."), "danger")
        return redirect(url_for("company_detail", id=company_id) + "#files")

    label = request.form.get("label", "").strip() or f.filename
    category = request.form.get("category", "other")

    # Versioning
    existing = (
        ClientFile.query.filter_by(company_id=company_id, label=label)
        .order_by(ClientFile.version.desc()).first()
    )
    version = (existing.version + 1) if existing else 1
    parent_id = existing.id if existing else None

    # Storage
    comp_dir = UPLOADS_DIR / str(company_id)
    comp_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    target_path = comp_dir / stored_name
    f.save(target_path)

    cf = ClientFile(
        company_id=company_id,
        filename=f.filename,
        label=label,
        stored_path=f"uploads/{company_id}/{stored_name}",
        mime=f.mimetype or (mimetypes.guess_type(f.filename)[0] or "application/octet-stream"),
        size_bytes=target_path.stat().st_size,
        category=category,
        version=version,
        parent_file_id=parent_id,
    )
    db.session.add(cf)
    db.session.commit()
    flash(_("Plik wgrany (wersja %(version)s).", version=version), "success")
    return redirect(url_for("company_detail", id=company_id) + "#files")


@app.route("/files/<int:id>/download")
def file_download(id):
    cf = db.get_or_404(ClientFile, id)
    output_root = (BASE_DIR / "output").resolve()
    path = (output_root / cf.stored_path).resolve()
    try:
        path.relative_to(output_root)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    # Download name tez przez secure_filename, zeby zla nazwa w DB nie zrobila
    # content-disposition injection
    return send_file(path, as_attachment=True,
                     download_name=secure_filename(cf.filename) or "plik",
                     mimetype=cf.mime)


@app.route("/files/<int:id>/delete", methods=["POST"])
def file_delete(id):
    cf = db.get_or_404(ClientFile, id)
    path = BASE_DIR / "output" / cf.stored_path
    company_id = cf.company_id
    task_id = cf.task_id
    filename = cf.filename
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass
    db.session.delete(cf)
    if task_id:
        _log_audit("tasks", task_id, "update", "files", filename, "", note=_("Usunięto plik"))
    db.session.commit()
    flash(_("Plik usunięty."), "success")
    if task_id:
        return redirect(url_for("task_detail", id=task_id))
    if company_id:
        return redirect(url_for("company_detail", id=company_id) + "#files")
    return redirect(url_for("dashboard"))
