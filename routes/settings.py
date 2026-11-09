"""Settings page and the Google OAuth flow (GSC / GA4)."""

import secrets

from flask import (
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import auth
import email_sender
import privacy
from core import (
    _parse_int,
    _vat_rate,
    admin_required,
    app,
    get_current_user,
)
from i18n import _
from models import LANGUAGES, ROLES, Settings, User, db

# ── Settings ──────────────────────────────────────────────────

@app.route("/settings", methods=["GET", "POST"])
def settings():
    s = Settings.get()
    if request.method == "POST":
        section = request.form.get("section", "general")
        if not get_current_user().is_admin:  # członek zespołu zmienia tylko swój profil (/profil)
            abort(403, _("Tylko administrator może zmieniać ustawienia firmy i integracji."))
        if section == "general":
            new_key = request.form.get("google_api_key", "").strip()
            if new_key:  # puste pole = zostaw zapisany klucz (nie wypisujemy go w HTML)
                s.google_api_key = new_key
            s.agency_name = request.form.get("agency_name", "").strip()
            s.agency_phone = request.form.get("agency_phone", "").strip()
            s.agency_email = request.form.get("agency_email", "").strip()
            flash(_("Ustawienia ogólne zapisane."), "success")
        elif section == "finance":
            s.agency_legal_name = request.form.get("agency_legal_name", "").strip()
            s.agency_nip = request.form.get("agency_nip", "").strip()
            s.agency_address = request.form.get("agency_address", "").strip()
            s.agency_bank_account = request.form.get("agency_bank_account", "").strip()
            s.default_vat_rate = _vat_rate(request.form.get("default_vat_rate"))
            s.company_vat_payer = "company_vat_payer" in request.form
            flash(_("Dane firmowe i finansowe zapisane."), "success")
        elif section == "smtp":
            s.smtp_host = request.form.get("smtp_host", "").strip()
            s.smtp_port = _parse_int(request.form.get("smtp_port")) or 587
            s.smtp_user = request.form.get("smtp_user", "").strip()
            s.smtp_from_addr = request.form.get("smtp_from_addr", "").strip()
            s.smtp_use_tls = "smtp_use_tls" in request.form
            new_pwd = request.form.get("smtp_password", "")
            if new_pwd:
                s.smtp_password_encrypted = email_sender.encrypt_password(new_pwd)
            flash(_("Ustawienia SMTP zapisane. Hasło zaszyfrowane lokalnie (Fernet)."), "success")
        elif section == "google_oauth":
            s.google_oauth_client_id = request.form.get("google_oauth_client_id", "").strip()
            new_secret = request.form.get("google_oauth_client_secret", "").strip()
            if new_secret:  # puste pole = zostaw zapisany sekret
                s.google_oauth_client_secret = new_secret
            s.ga_property_id_default = request.form.get("ga_property_id_default", "").strip()
            flash(_("Zapisano dane OAuth. Kliknij Autoryzuj w Google by połączyć konto."), "success")
        elif section == "ai":
            s.assistant_enabled = "assistant_enabled" in request.form
            new_key = request.form.get("openrouter_api_key", "").strip()
            if new_key:
                # Szyfrujemy tym samym helperem co haslo SMTP (Fernet)
                s.openrouter_api_key_encrypted = email_sender.encrypt_password(new_key)
            model = request.form.get("assistant_model", "").strip()
            if model:
                s.assistant_model = model
            s.pii_masking_enabled = "pii_masking_enabled" in request.form
            s.pii_masking_ner = "pii_masking_ner" in request.form
            flash(_("Konfiguracja asystenta AI zapisana."), "success")
        db.session.commit()
        return redirect(url_for("settings") + f"#{section}")

    has_smtp_password = bool(s.smtp_password_encrypted)
    has_google_token = bool(s.gsc_refresh_token)
    has_openrouter_key = bool(s.openrouter_api_key_encrypted)
    return render_template("settings.html", settings=s,
                           polanon=privacy.polanon_status(),
                           has_smtp_password=has_smtp_password,
                           has_google_token=has_google_token,
                           has_openrouter_key=has_openrouter_key,
                           team=User.query.order_by(User.is_active.desc(), User.role, User.name).all(),
                           roles=ROLES, languages=LANGUAGES, min_password_len=auth.MIN_PASSWORD_LENGTH)


# ── Google OAuth ──────────────────────────────────────────────

@app.route("/google-oauth/start")
@admin_required
def google_oauth_start():
    import google_sync
    redirect_uri = url_for("oauth2callback", _external=True)
    url, state = google_sync.get_authorization_url(redirect_uri)
    if not url:
        flash(_("Najpierw uzupełnij Client ID i Client Secret w Ustawieniach."), "danger")
        return redirect(url_for("settings") + "#google_oauth")
    session["oauth_state"] = state
    return redirect(url)


@app.route("/oauth2callback")
def oauth2callback():
    import google_sync
    code = request.args.get("code")
    received_state = request.args.get("state", "")
    expected_state = session.pop("oauth_state", None)

    if not code:
        flash(_("Brak kodu autoryzacji od Google."), "danger")
        return redirect(url_for("settings") + "#google_oauth")

    # CSRF-ochrona OAuth: state MUSI sie zgadzac z tym co zapisalismy w sesji
    if not expected_state or not secrets.compare_digest(received_state, expected_state):
        flash(_("Blad weryfikacji OAuth (state mismatch). Sprobuj ponownie."), "danger")
        return redirect(url_for("settings") + "#google_oauth")

    redirect_uri = url_for("oauth2callback", _external=True)
    try:
        google_sync.exchange_code(redirect_uri, code)
        flash(_("Autoryzacja Google zapisana. Mozesz synchronizowac GSC i GA4."), "success")
    except Exception as exc:
        flash(_("Blad autoryzacji: %(error)s", error=exc), "danger")
    return redirect(url_for("settings") + "#google_oauth")
