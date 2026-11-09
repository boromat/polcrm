"""Email sending + template rendering + Fernet-encrypted SMTP password."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.utils import formataddr

from jinja2.sandbox import SandboxedEnvironment

from i18n import _
from models import db, Settings, EmailLog, EmailTemplate
from crypto_utils import encrypt_str, decrypt_str


# SandboxedEnvironment blokuje ataki SSTI przez ograniczony dostep do atrybutow
# obiektow. autoescape=True chroni przed XSS w preview/body HTML.
_jinja_env = SandboxedEnvironment(autoescape=True)

# Maks dlugosc body zapisywanego do EmailLog (bezpieczenstwo przy wyciekach DB)
_EMAIL_LOG_BODY_LIMIT = 2000


# Wsteczna kompatybilnosc - aliasuj do wspoldzielonych helperow
encrypt_password = encrypt_str
decrypt_password = decrypt_str


def render_template_string(template_str, context):
    if not template_str:
        return ""
    try:
        tmpl = _jinja_env.from_string(template_str)
        return tmpl.render(**context)
    except Exception as exc:
        return _("[Blad renderowania szablonu: %(error)s]", error=exc)


def build_context(company=None, payment=None, audit=None, extra=None):
    """Build standard context for email/contract templates."""
    s = Settings.get()
    agency = {
        "name": s.agency_name,
        "legal_name": s.agency_legal_name or s.agency_name,
        "nip": s.agency_nip,
        "address": s.agency_address,
        "phone": s.agency_phone,
        "email": s.agency_email,
        "bank_account": s.agency_bank_account,
    }
    client_ctx = {}
    if company:
        client_ctx = {
            "name": company.name,
            "legal_name": company.client_legal_name or company.name,
            "nip": company.client_nip,
            "address": company.client_address or company.address,
            "website": company.website,
            "contact_person": company.contact_person,
            "contact_email": company.contact_email,
            "phone": company.phone,
        }
    ctx = {"agency": agency, "company": client_ctx, "client": client_ctx}
    if payment:
        ctx["payment"] = payment
    if audit:
        ctx["audit"] = audit
    if extra:
        ctx.update(extra)
    return ctx


def _truncate_body_for_log(body):
    """Przytnij body do limitu + doklej znacznik, zeby nie ladowac do bazy calych HTMLi."""
    if not body:
        return ""
    if len(body) <= _EMAIL_LOG_BODY_LIMIT:
        return body
    return body[:_EMAIL_LOG_BODY_LIMIT] + f"\n...[przyciete, oryginal {len(body)} znakow]"


def send_email(to_address, subject, body_html, cc=None, bcc=None,
               company_id=None, template_key=""):
    """
    Send an email via SMTP. Logs the attempt regardless of success.
    Returns (ok: bool, message: str).
    """
    s = Settings.get()
    if not s.smtp_host or not s.smtp_from_addr:
        log = EmailLog(
            company_id=company_id,
            template_key=template_key,
            to_address=to_address,
            cc=cc or "",
            bcc=bcc or "",
            subject_rendered=subject,
            body_rendered=_truncate_body_for_log(body_html),
            status="failed",
            error_message=_("SMTP nie jest skonfigurowany w Ustawieniach."),
        )
        db.session.add(log)
        db.session.commit()
        return False, _("SMTP nie jest skonfigurowany.")

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr((s.agency_name or "PolCRM", s.smtp_from_addr))
    msg["To"] = to_address
    if cc:
        msg["Cc"] = cc
    msg.attach(MIMEText(body_html, "html", "utf-8"))

    recipients = [to_address]
    if cc:
        recipients.extend([a.strip() for a in cc.split(",") if a.strip()])
    if bcc:
        recipients.extend([a.strip() for a in bcc.split(",") if a.strip()])

    try:
        password = decrypt_password(s.smtp_password_encrypted)
        if s.smtp_use_tls:
            server = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=20)
            server.starttls()
        else:
            server = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=20)
        if s.smtp_user:
            server.login(s.smtp_user, password)
        server.sendmail(s.smtp_from_addr, recipients, msg.as_string())
        server.quit()
        status = "sent"
        error = ""
    except Exception as exc:
        status = "failed"
        error = str(exc)

    log = EmailLog(
        company_id=company_id,
        template_key=template_key,
        to_address=to_address,
        cc=cc or "",
        bcc=bcc or "",
        subject_rendered=subject,
        body_rendered=_truncate_body_for_log(body_html),
        status=status,
        error_message=error,
    )
    db.session.add(log)
    db.session.commit()

    return status == "sent", error or _("Wiadomosc wyslana.")


def render_email_template(key, context):
    """Render an email template (subject + body) by key."""
    tmpl = EmailTemplate.query.filter_by(key=key).first()
    if not tmpl:
        return None, None
    subject = render_template_string(tmpl.subject_template, context)
    body = render_template_string(tmpl.body_template, context)
    return subject, body
