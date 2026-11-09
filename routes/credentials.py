"""Client access entries (links to a password manager, never passwords)."""

from flask import (
    flash,
    redirect,
    request,
    url_for,
)

from core import (
    _parse_date,
    app,
)
from i18n import _
from models import ClientCredential, Company, db

# ═══════════════════════════════════════════════════════════════
#  DOSTĘPY KLIENTÓW (LINKI DO SEJFÓW)
# ═══════════════════════════════════════════════════════════════

@app.route("/companies/<int:company_id>/credentials/new", methods=["POST"])
def credential_new(company_id):
    db.get_or_404(Company, company_id)
    cr = ClientCredential(
        company_id=company_id,
        label=request.form.get("label", "").strip(),
        login_url=request.form.get("login_url", "").strip(),
        username_hint=request.form.get("username_hint", "").strip(),
        vault_link=request.form.get("vault_link", "").strip(),
        expires_at=_parse_date(request.form.get("expires_at")),
        notes=request.form.get("notes", "").strip(),
    )
    if not cr.label:
        flash(_("Etykieta (np. WP admin) jest wymagana."), "danger")
        return redirect(url_for("company_detail", id=company_id) + "#credentials")
    db.session.add(cr)
    db.session.commit()
    flash(_("Dodano dostęp."), "success")
    return redirect(url_for("company_detail", id=company_id) + "#credentials")


@app.route("/credentials/<int:id>/edit", methods=["POST"])
def credential_edit(id):
    cr = db.get_or_404(ClientCredential, id)
    cr.label = request.form.get("label", cr.label).strip()
    cr.login_url = request.form.get("login_url", "").strip()
    cr.username_hint = request.form.get("username_hint", "").strip()
    cr.vault_link = request.form.get("vault_link", "").strip()
    cr.expires_at = _parse_date(request.form.get("expires_at"))
    cr.notes = request.form.get("notes", "").strip()
    db.session.commit()
    flash(_("Dostęp zapisany."), "success")
    return redirect(url_for("company_detail", id=cr.company_id) + "#credentials")


@app.route("/credentials/<int:id>/delete", methods=["POST"])
def credential_delete(id):
    cr = db.get_or_404(ClientCredential, id)
    company_id = cr.company_id
    db.session.delete(cr)
    db.session.commit()
    flash(_("Dostęp usunięty."), "success")
    return redirect(url_for("company_detail", id=company_id) + "#credentials")
