"""Database models for the PolCRM agency hub."""

import json
import secrets
from datetime import date, datetime, timezone

from flask_sqlalchemy import SQLAlchemy

import i18n
from crypto_utils import EncryptedText
from i18n import _

db = SQLAlchemy()

def utcnow():
    """Bieżący czas UTC jako naiwny datetime - to samo co dawne datetime.utcnow(), które
    Python 3.12 oznaczył jako przestarzałe. Naiwny, bo tak zapisane są istniejące dane w SQLite."""
    return datetime.now(timezone.utc).replace(tzinfo=None)



# ── Helpers ────────────────────────────────────────────────────

class JsonProperty:
    """Descriptor that auto-serializes a column to/from JSON."""

    def __init__(self, column_name):
        self.column_name = column_name

    def __set_name__(self, owner, name):
        self.name = name

    def __get__(self, obj, objtype=None):
        if obj is None:
            return self
        raw = getattr(obj, self.column_name)
        if raw is None:
            return None
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, TypeError):
            return raw

    def __set__(self, obj, value):
        if value is None:
            setattr(obj, self.column_name, None)
        elif isinstance(value, str):
            setattr(obj, self.column_name, value)
        else:
            setattr(obj, self.column_name, json.dumps(value, ensure_ascii=False))


# ── Settings (singleton) ──────────────────────────────────────

class Settings(db.Model):
    __tablename__ = "settings"
    id = db.Column(db.Integer, primary_key=True)
    google_api_key = db.Column(EncryptedText, default="")  # Fernet; stare wartości jawne są czytane bez zmian
    agency_name = db.Column(db.String(256), default="")
    agency_phone = db.Column(db.String(64), default="")
    agency_email = db.Column(db.String(256), default="")
    agency_logo_path = db.Column(db.String(512), default="")

    # SMTP
    smtp_host = db.Column(db.String(256), default="")
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(256), default="")
    smtp_password_encrypted = db.Column(db.Text, default="")
    smtp_from_addr = db.Column(db.String(256), default="")
    smtp_use_tls = db.Column(db.Boolean, default=True)

    # Fernet key (encryption for SMTP password)
    fernet_key = db.Column(db.Text, default="")

    # Google OAuth (GSC + GA)
    google_oauth_client_id = db.Column(db.String(512), default="")
    google_oauth_client_secret = db.Column(EncryptedText, default="")
    gsc_refresh_token = db.Column(EncryptedText, default="")
    ga_refresh_token = db.Column(EncryptedText, default="")
    ga_property_id_default = db.Column(db.String(64), default="")

    # Finances
    default_vat_rate = db.Column(db.Float, default=23.0)
    company_vat_payer = db.Column(db.Boolean, default=True)
    fiscal_year_start_month = db.Column(db.Integer, default=1)

    # Agency legal data (for contracts)
    agency_legal_name = db.Column(db.String(512), default="")
    agency_nip = db.Column(db.String(32), default="")
    agency_address = db.Column(db.Text, default="")
    agency_bank_account = db.Column(db.String(64), default="")

    # AI Assistant (OpenRouter)
    openrouter_api_key_encrypted = db.Column(db.Text, default="")
    assistant_model = db.Column(db.String(128), default="google/gemini-3.1-flash-lite-preview")
    assistant_enabled = db.Column(db.Boolean, default=False)
    # Maskowanie danych osobowych przed wysłaniem do AI (opcjonalny pakiet polanon)
    pii_masking_enabled = db.Column(db.Boolean, default=False)
    pii_masking_ner = db.Column(db.Boolean, default=False)

    @classmethod
    def get(cls):
        s = cls.query.first()
        if s is None:
            s = cls(id=1)
            db.session.add(s)
            db.session.commit()
        return s


# ── Company ───────────────────────────────────────────────────

PIPELINE_STAGES = ["lead", "audit", "contact", "visit", "offer", "client"]

class Company(db.Model):
    __tablename__ = "companies"
    id = db.Column(db.Integer, primary_key=True)
    place_id = db.Column(db.String(256), unique=True, nullable=True)
    name = db.Column(db.String(512), nullable=False)
    address = db.Column(db.Text, default="")
    phone = db.Column(db.String(64), default="")
    intl_phone = db.Column(db.String(64), default="")
    lat = db.Column(db.Float, nullable=True)
    lng = db.Column(db.Float, nullable=True)
    rating = db.Column(db.Float, nullable=True)
    user_ratings_total = db.Column(db.Integer, nullable=True)
    website = db.Column(db.String(1024), default="")
    business_status = db.Column(db.String(64), default="")
    primary_type = db.Column(db.String(128), default="")
    google_maps_url = db.Column(db.String(1024), default="")

    # Business context
    industry = db.Column(db.String(256), default="")
    client_segment = db.Column(db.String(256), default="")
    main_services = db.Column(db.Text, default="")
    contact_person = db.Column(db.String(256), default="")
    contact_email = db.Column(db.String(256), default="")
    ltv_potential = db.Column(db.Float, nullable=True)

    # Pipeline
    pipeline_stage = db.Column(db.String(32), default="lead")
    next_action = db.Column(db.Text, default="")
    next_action_date = db.Column(db.Date, nullable=True)

    # Results (case studies)
    results_description = db.Column(db.Text, default="")
    results_calls_before = db.Column(db.Integer, nullable=True)
    results_calls_after = db.Column(db.Integer, nullable=True)
    results_visibility_before = db.Column(db.String(64), default="")
    results_visibility_after = db.Column(db.String(64), default="")
    results_reviews_before = db.Column(db.Integer, nullable=True)
    results_reviews_after = db.Column(db.Integer, nullable=True)

    # Retainer / billing
    is_retainer = db.Column(db.Boolean, default=False)
    monthly_fee_net = db.Column(db.Float, nullable=True)
    billing_day = db.Column(db.Integer, default=1)
    retainer_started_at = db.Column(db.Date, nullable=True)

    # Client legal data (for contracts/invoicing reference)
    client_legal_name = db.Column(db.String(512), default="")
    client_nip = db.Column(db.String(32), default="")
    client_address = db.Column(db.Text, default="")

    # Portal (future-proofing)
    portal_token = db.Column(db.String(128), unique=True, nullable=True)

    # Google integrations (per-client)
    gsc_site_url = db.Column(db.String(512), default="")
    ga_property_id = db.Column(db.String(64), default="")

    # Timestamps
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    # Attribution
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    # Relations
    audits = db.relationship("Audit", backref="company", lazy=True, cascade="all, delete-orphan")
    notes = db.relationship("Note", backref="company", lazy=True, cascade="all, delete-orphan")
    visits = db.relationship("Visit", backref="company", lazy=True, cascade="all, delete-orphan")
    offers = db.relationship("Offer", backref="company", lazy=True, cascade="all, delete-orphan")
    payments = db.relationship("Payment", backref="company", lazy=True, cascade="all, delete-orphan")
    projects = db.relationship("Project", backref="company", lazy=True, cascade="all, delete-orphan")
    content_posts = db.relationship("ContentPost", backref="company", lazy=True, cascade="all, delete-orphan")
    credentials = db.relationship("ClientCredential", backref="company", lazy=True, cascade="all, delete-orphan")
    contracts = db.relationship("Contract", backref="company", lazy=True, cascade="all, delete-orphan")
    files = db.relationship("ClientFile", backref="company", lazy=True, cascade="all, delete-orphan")
    gsc_snapshots = db.relationship("GscSnapshot", backref="company", lazy=True, cascade="all, delete-orphan")
    ga_snapshots = db.relationship("GaSnapshot", backref="company", lazy=True, cascade="all, delete-orphan")

    @property
    def latest_audit(self):
        if self.audits:
            return sorted(self.audits, key=lambda a: a.created_at, reverse=True)[0]
        return None

    @property
    def stage_label(self):
        labels = {
            "lead": _("Lead"),
            "audit": _("Audyt"),
            "contact": _("Kontakt"),
            "visit": _("Wizyta"),
            "offer": _("Oferta"),
            "client": _("Klient"),
        }
        return labels.get(self.pipeline_stage, self.pipeline_stage)

    def ensure_portal_token(self):
        if not self.portal_token:
            self.portal_token = secrets.token_urlsafe(48)


# ── Audit ─────────────────────────────────────────────────────

class Audit(db.Model):
    __tablename__ = "audits"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    created_at = db.Column(db.DateTime, default=utcnow)

    # Scores (1-5)
    score_visibility = db.Column(db.Integer, nullable=True)
    score_offer = db.Column(db.Integer, nullable=True)
    score_trust = db.Column(db.Integer, nullable=True)
    score_conversion = db.Column(db.Integer, nullable=True)
    score_analytics = db.Column(db.Integer, nullable=True)
    score_overall = db.Column(db.Float, nullable=True)

    # 7 sections (JSON stored as text)
    _section_context = db.Column("section_context", db.Text, default="{}")
    _section_website = db.Column("section_website", db.Text, default="{}")
    _section_seo = db.Column("section_seo", db.Text, default="{}")
    _section_gbp = db.Column("section_gbp", db.Text, default="{}")
    _section_directories = db.Column("section_directories", db.Text, default="{}")
    _section_competition = db.Column("section_competition", db.Text, default="{}")
    _section_plan90 = db.Column("section_plan90", db.Text, default="{}")

    section_context = JsonProperty("_section_context")
    section_website = JsonProperty("_section_website")
    section_seo = JsonProperty("_section_seo")
    section_gbp = JsonProperty("_section_gbp")
    section_directories = JsonProperty("_section_directories")
    section_competition = JsonProperty("_section_competition")
    section_plan90 = JsonProperty("_section_plan90")

    # Report content (JSON)
    _top_problems = db.Column("top_problems", db.Text, default="[]")
    _top_opportunities = db.Column("top_opportunities", db.Text, default="[]")
    _recommended_actions = db.Column("recommended_actions", db.Text, default="[]")

    top_problems = JsonProperty("_top_problems")
    top_opportunities = JsonProperty("_top_opportunities")
    recommended_actions = JsonProperty("_recommended_actions")

    # PageSpeed
    pagespeed_mobile = db.Column(db.Integer, nullable=True)
    pagespeed_desktop = db.Column(db.Integer, nullable=True)
    _pagespeed_data = db.Column("pagespeed_data", db.Text, default="{}")
    pagespeed_data = JsonProperty("_pagespeed_data")

    # Status
    status = db.Column(db.String(32), default="draft")

    # Relations
    competitors = db.relationship("Competitor", backref="audit", lazy=True, cascade="all, delete-orphan")

    @property
    def scores_dict(self):
        return {
            _("Widoczność online"): self.score_visibility,
            _("Oferta i komunikacja"): self.score_offer,
            _("Zaufanie"): self.score_trust,
            _("Konwersja"): self.score_conversion,
            _("Analityka"): self.score_analytics,
        }

    def compute_overall(self):
        scores = [s for s in [
            self.score_visibility, self.score_offer, self.score_trust,
            self.score_conversion, self.score_analytics
        ] if s is not None]
        if scores:
            self.score_overall = round(sum(scores) / len(scores), 1)


# ── Competitor ────────────────────────────────────────────────

class Competitor(db.Model):
    __tablename__ = "competitors"
    id = db.Column(db.Integer, primary_key=True)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=False)
    name = db.Column(db.String(512), default="")
    place_id = db.Column(db.String(256), default="")
    address = db.Column(db.Text, default="")
    website = db.Column(db.String(1024), default="")
    rating = db.Column(db.Float, nullable=True)
    user_ratings_total = db.Column(db.Integer, nullable=True)
    score_visibility = db.Column(db.Integer, nullable=True)
    score_trust = db.Column(db.Integer, nullable=True)
    strengths = db.Column(db.Text, default="")
    weaknesses = db.Column(db.Text, default="")


# ── Package ───────────────────────────────────────────────────

class Package(db.Model):
    __tablename__ = "packages"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    description = db.Column(db.Text, default="")
    price = db.Column(db.Float, default=0)
    duration_days = db.Column(db.Integer, default=30)
    _deliverables = db.Column("deliverables", db.Text, default="[]")
    _expected_results = db.Column("expected_results", db.Text, default="[]")
    _payment_variants = db.Column("payment_variants", db.Text, default="[]")
    is_active = db.Column(db.Boolean, default=True)

    deliverables = JsonProperty("_deliverables")
    expected_results = JsonProperty("_expected_results")
    payment_variants = JsonProperty("_payment_variants")

    offers = db.relationship("Offer", backref="package", lazy=True)


# ── Offer ─────────────────────────────────────────────────────

class Offer(db.Model):
    __tablename__ = "offers"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    package_id = db.Column(db.Integer, db.ForeignKey("packages.id"), nullable=False)
    audit_id = db.Column(db.Integer, db.ForeignKey("audits.id"), nullable=True)
    custom_price = db.Column(db.Float, nullable=True)
    custom_notes = db.Column(db.Text, default="")
    _deliverables_override = db.Column("deliverables_override", db.Text, default="")
    timeline_override = db.Column(db.String(128), default="")
    status = db.Column(db.String(32), default="draft")
    sent_at = db.Column(db.DateTime, nullable=True)
    accepted_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    deliverables_override = JsonProperty("_deliverables_override")

    audit = db.relationship("Audit", backref="offers")

    @property
    def effective_price(self):
        return self.custom_price if self.custom_price is not None else self.package.price


# ── Visit ─────────────────────────────────────────────────────

class Visit(db.Model):
    __tablename__ = "visits"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    scheduled_at = db.Column(db.DateTime, nullable=False)
    duration_minutes = db.Column(db.Integer, default=60)
    visit_type = db.Column(db.String(32), default="consultation")
    status = db.Column(db.String(32), default="planned")

    # Preparation checklist
    prep_report_printed = db.Column(db.Boolean, default=False)
    prep_screenshots = db.Column(db.Boolean, default=False)
    prep_offer_template = db.Column(db.Boolean, default=False)
    prep_questions = db.Column(db.Boolean, default=False)

    # Post-visit
    notes = db.Column(db.Text, default="")
    outcome = db.Column(db.Text, default="")
    follow_up_action = db.Column(db.Text, default="")
    follow_up_date = db.Column(db.Date, nullable=True)

    # Attribution
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    @property
    def type_label(self):
        labels = {"consultation": _("Konsultacja"), "follow_up": _("Follow-up"), "closing": _("Domknięcie")}
        return labels.get(self.visit_type, self.visit_type)

    @property
    def status_label(self):
        labels = {
            "planned": _("Zaplanowana"),
            "completed": _("Odbyta"),
            "cancelled": _("Odwołana"),
            "rescheduled": _("Przełożona"),
        }
        return labels.get(self.status, self.status)

    @property
    def prep_done_count(self):
        return sum([self.prep_report_printed, self.prep_screenshots,
                    self.prep_offer_template, self.prep_questions])


# ── Note ──────────────────────────────────────────────────────

NOTE_SCOPES = ["company", "project", "personal"]

class Note(db.Model):
    __tablename__ = "notes"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    scope = db.Column(db.String(16), default="company")  # company | project | personal
    title = db.Column(db.String(256), default="")
    content = db.Column(db.Text, nullable=False)
    note_type = db.Column(db.String(32), default="general")
    pinned = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    @property
    def type_label(self):
        labels = {
            "general": _("Notatka"),
            "call": _("Telefon"),
            "meeting": _("Spotkanie"),
            "follow_up": _("Follow-up"),
            "idea": _("Pomysł"),
            "todo": _("Do zrobienia"),
        }
        return labels.get(self.note_type, self.note_type)


# ── Payment (income / revenue ledger) ─────────────────────────

PAYMENT_KINDS = ["retainer", "addon", "project_milestone", "one_time"]
PAYMENT_STATUSES = ["unpaid", "paid", "overdue", "cancelled"]

class Payment(db.Model):
    __tablename__ = "payments"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    payment_number = db.Column(db.String(32), unique=True, nullable=True)
    title = db.Column(db.String(512), default="")
    description = db.Column(db.Text, default="")
    amount_net = db.Column(db.Float, default=0)
    vat_rate = db.Column(db.Float, default=23.0)
    amount_gross = db.Column(db.Float, default=0)
    kind = db.Column(db.String(32), default="one_time")
    status = db.Column(db.String(32), default="unpaid")
    period_month = db.Column(db.Integer, nullable=True)
    period_year = db.Column(db.Integer, nullable=True)
    issued_at = db.Column(db.Date, default=date.today)
    due_at = db.Column(db.Date, nullable=True)
    paid_at = db.Column(db.Date, nullable=True)
    external_invoice_number = db.Column(db.String(64), default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    def recompute_gross(self):
        self.amount_gross = round((self.amount_net or 0) * (1 + (self.vat_rate or 0) / 100), 2)

    @property
    def status_label(self):
        labels = {
            "unpaid": _("Nieopłacone"),
            "paid": _("Opłacone"),
            "overdue": _("Przeterminowane"),
            "cancelled": _("Anulowane"),
        }
        return labels.get(self.status, self.status)

    @property
    def kind_label(self):
        labels = {
            "retainer": _("Abonament"),
            "addon": _("Dodatek"),
            "project_milestone": _("Etap projektu"),
            "one_time": _("Jednorazowe"),
        }
        return labels.get(self.kind, self.kind)


# ── Expense (costs) ───────────────────────────────────────────

EXPENSE_CATEGORIES = ["seo_tools", "subcontractor", "marketing", "office_transport"]

class Expense(db.Model):
    __tablename__ = "expenses"
    id = db.Column(db.Integer, primary_key=True)
    category = db.Column(db.String(32), default="seo_tools")
    subcategory = db.Column(db.String(128), default="")
    title = db.Column(db.String(512), default="")
    description = db.Column(db.Text, default="")
    vendor = db.Column(db.String(256), default="")
    amount_net = db.Column(db.Float, default=0)
    vat_rate = db.Column(db.Float, default=23.0)
    amount_gross = db.Column(db.Float, default=0)
    payment_date = db.Column(db.Date, default=date.today)
    subscription_id = db.Column(db.Integer, db.ForeignKey("subscriptions.id"), nullable=True)
    client_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    attachment_file_id = db.Column(db.Integer, db.ForeignKey("client_files.id"), nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    client = db.relationship("Company", foreign_keys=[client_id])

    def recompute_gross(self):
        self.amount_gross = round((self.amount_net or 0) * (1 + (self.vat_rate or 0) / 100), 2)

    @property
    def category_label(self):
        labels = {
            "seo_tools": _("Narzędzia SEO"),
            "subcontractor": _("Podwykonawca"),
            "marketing": _("Marketing własny"),
            "office_transport": _("Biuro i transport"),
        }
        return labels.get(self.category, self.category)


# ── Subscription (recurring tool costs) ───────────────────────

BILLING_CYCLES = ["monthly", "quarterly", "yearly"]

class Subscription(db.Model):
    __tablename__ = "subscriptions"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False)
    vendor = db.Column(db.String(256), default="")
    amount_net = db.Column(db.Float, default=0)
    vat_rate = db.Column(db.Float, default=23.0)
    billing_cycle = db.Column(db.String(16), default="monthly")
    renewal_date = db.Column(db.Date, nullable=True)
    category = db.Column(db.String(32), default="seo_tools")
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    expenses = db.relationship("Expense", backref="subscription", lazy=True)

    @property
    def monthly_allocation(self):
        """Spread amount across months for balance reports."""
        if self.billing_cycle == "monthly":
            return self.amount_net or 0
        if self.billing_cycle == "quarterly":
            return (self.amount_net or 0) / 3
        if self.billing_cycle == "yearly":
            return (self.amount_net or 0) / 12
        return self.amount_net or 0

    @property
    def cycle_label(self):
        labels = {"monthly": _("Miesięcznie"), "quarterly": _("Kwartalnie"), "yearly": _("Rocznie")}
        return labels.get(self.billing_cycle, self.billing_cycle)


# ── Project (simple checklist of tasks, inc. website builds) ──

PROJECT_KINDS = ["website", "seo_retainer", "content_campaign", "other"]
PROJECT_STATUSES = ["planning", "active", "on_hold", "done", "cancelled"]

class Project(db.Model):
    __tablename__ = "projects"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    name = db.Column(db.String(512), nullable=False)
    kind = db.Column(db.String(32), default="website")
    domain = db.Column(db.String(256), default="")
    cms = db.Column(db.String(64), default="")
    hosting = db.Column(db.String(256), default="")
    budget_net = db.Column(db.Float, nullable=True)
    status = db.Column(db.String(32), default="planning")
    started_at = db.Column(db.Date, nullable=True)
    deadline = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    tasks = db.relationship("Task", backref="project", lazy=True, cascade="all, delete-orphan")

    @property
    def kind_label(self):
        labels = {
            "website": _("Strona WWW"),
            "seo_retainer": _("Abonament SEO"),
            "content_campaign": _("Kampania content"),
            "other": _("Inny"),
        }
        return labels.get(self.kind, self.kind)

    @property
    def status_label(self):
        labels = {
            "planning": _("Planowanie"),
            "active": _("W toku"),
            "on_hold": _("Wstrzymany"),
            "done": _("Zakończony"),
            "cancelled": _("Anulowany"),
        }
        return labels.get(self.status, self.status)

    @property
    def progress_percent(self):
        if not self.tasks:
            return 0
        done = sum(1 for t in self.tasks if t.status == "done")
        return int(done / len(self.tasks) * 100)


# ── Task ──────────────────────────────────────────────────────

TASK_PRIORITIES = ["low", "medium", "high", "urgent"]
TASK_STATUSES = ["todo", "in_progress", "blocked", "done"]


def task_priority_label(code):
    labels = {"low": _("Niski"), "medium": _("Średni"), "high": _("Wysoki"), "urgent": _("Pilny")}
    return labels.get(code, code)


def task_status_label(code):
    labels = {
        "todo": _("Do zrobienia"),
        "in_progress": _("W trakcie"),
        "blocked": _("Zablokowane"),
        "done": _("Zrobione"),
    }
    return labels.get(code, code)


class Task(db.Model):
    __tablename__ = "tasks"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512), nullable=False)
    description = db.Column(db.Text, default="")
    priority = db.Column(db.String(16), default="medium")
    status = db.Column(db.String(16), default="todo")
    deadline = db.Column(db.Date, nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    content_post_id = db.Column(db.Integer, db.ForeignKey("content_posts.id"), nullable=True)
    parent_task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    done_at = db.Column(db.DateTime, nullable=True)
    order_hint = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    company = db.relationship("Company", foreign_keys=[company_id])
    subtasks = db.relationship(
        "Task",
        backref=db.backref("parent_task", remote_side="Task.id"),
        cascade="all, delete-orphan",
        foreign_keys=[parent_task_id],
    )
    comments = db.relationship("TaskComment", backref="task", cascade="all, delete-orphan", lazy=True)
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])

    @property
    def progress_subtasks(self):
        subs = self.subtasks or []
        if not subs:
            return (0, 0, 0)
        done = sum(1 for s in subs if s.status == "done")
        total = len(subs)
        pct = int(done * 100 / total) if total else 0
        return (done, total, pct)

    @property
    def priority_label(self):
        return task_priority_label(self.priority)

    @property
    def status_label(self):
        return task_status_label(self.status)

    @property
    def is_overdue(self):
        return (
            self.deadline is not None
            and self.status != "done"
            and self.deadline < date.today()
        )


# ── ContentPost (content calendar) ────────────────────────────

CONTENT_TYPES = ["blog", "landing", "guest_post", "social", "email"]
CONTENT_STATUSES = ["idea", "writing", "review", "approved", "published"]

class ContentPost(db.Model):
    __tablename__ = "content_posts"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    title = db.Column(db.String(512), nullable=False)
    _keywords = db.Column("keywords", db.Text, default="[]")
    content_type = db.Column(db.String(32), default="blog")
    status = db.Column(db.String(32), default="idea")
    deadline = db.Column(db.Date, nullable=True)
    published_at = db.Column(db.DateTime, nullable=True)
    url = db.Column(db.String(1024), default="")
    writer_name = db.Column(db.String(256), default="")
    writer_cost_expense_id = db.Column(db.Integer, db.ForeignKey("expenses.id"), nullable=True)
    brief = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    keywords = JsonProperty("_keywords")
    writer_expense = db.relationship("Expense", foreign_keys=[writer_cost_expense_id])

    @property
    def status_label(self):
        labels = {
            "idea": _("Pomysł"),
            "writing": _("W pisaniu"),
            "review": _("Do akceptacji"),
            "approved": _("Zaakceptowany"),
            "published": _("Opublikowany"),
        }
        return labels.get(self.status, self.status)

    @property
    def type_label(self):
        labels = {
            "blog": _("Blog"),
            "landing": _("Landing"),
            "guest_post": _("Guest post"),
            "social": _("Social"),
            "email": _("Email"),
        }
        return labels.get(self.content_type, self.content_type)


# ── KnowledgeArticle (SOP / baza wiedzy) ──────────────────────

class KnowledgeArticle(db.Model):
    __tablename__ = "knowledge_articles"
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(512), nullable=False)
    category = db.Column(db.String(128), default="Ogólne")
    body = db.Column(db.Text, default="")  # markdown
    _tags = db.Column("tags", db.Text, default="[]")
    pinned = db.Column(db.Boolean, default=False)
    order_hint = db.Column(db.Integer, default=0)
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    tags = JsonProperty("_tags")


# ── ClientCredential (link do sejfu haseł) ────────────────────

class ClientCredential(db.Model):
    __tablename__ = "client_credentials"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    label = db.Column(db.String(128), nullable=False)
    login_url = db.Column(db.String(1024), default="")
    username_hint = db.Column(db.String(256), default="")
    vault_link = db.Column(EncryptedText, default="")  # bitwarden:// / onepassword:// - szyfrowane Fernet
    expires_at = db.Column(db.Date, nullable=True)
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)


# ── EmailTemplate ─────────────────────────────────────────────

class EmailTemplate(db.Model):
    __tablename__ = "email_templates"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(256), default="")
    subject_template = db.Column(db.String(512), default="")
    body_template = db.Column(db.Text, default="")
    placeholders_doc = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


# ── EmailLog ──────────────────────────────────────────────────

class EmailLog(db.Model):
    __tablename__ = "email_log"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    template_key = db.Column(db.String(64), default="")
    to_address = db.Column(db.String(512), default="")
    cc = db.Column(db.String(512), default="")
    bcc = db.Column(db.String(512), default="")
    subject_rendered = db.Column(db.Text, default="")
    body_rendered = db.Column(db.Text, default="")
    sent_at = db.Column(db.DateTime, default=utcnow)
    status = db.Column(db.String(16), default="sent")  # sent | failed | queued
    error_message = db.Column(db.Text, default="")

    company = db.relationship("Company")


# ── ContractTemplate ──────────────────────────────────────────

class ContractTemplate(db.Model):
    __tablename__ = "contract_templates"
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(256), default="")
    body_template = db.Column(db.Text, default="")
    placeholders_doc = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)


# ── Contract ──────────────────────────────────────────────────

class Contract(db.Model):
    __tablename__ = "contracts"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    template_key = db.Column(db.String(64), default="")
    name = db.Column(db.String(512), default="")
    content_rendered = db.Column(db.Text, default="")
    generated_pdf_file_id = db.Column(db.Integer, db.ForeignKey("client_files.id"), nullable=True)
    signed_at = db.Column(db.Date, nullable=True)
    status = db.Column(db.String(16), default="draft")  # draft | sent | signed | archived
    notes = db.Column(db.Text, default="")
    created_at = db.Column(db.DateTime, default=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    pdf_file = db.relationship("ClientFile", foreign_keys=[generated_pdf_file_id])

    @property
    def status_label(self):
        labels = {"draft": _("Szkic"), "sent": _("Wysłane"), "signed": _("Podpisane"), "archived": _("Zarchiwizowane")}
        return labels.get(self.status, self.status)


# ── ClientFile (with versioning) ──────────────────────────────

FILE_CATEGORIES = ["contract", "brief", "mockup", "report", "other"]

class ClientFile(db.Model):
    __tablename__ = "client_files"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True)
    project_id = db.Column(db.Integer, db.ForeignKey("projects.id"), nullable=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)
    filename = db.Column(db.String(512), nullable=False)
    label = db.Column(db.String(256), default="")  # logical name for versioning
    stored_path = db.Column(db.String(1024), nullable=False)  # względem output/, np. uploads/<firma>/<plik>
    mime = db.Column(db.String(128), default="")
    size_bytes = db.Column(db.Integer, default=0)
    category = db.Column(db.String(32), default="other")
    version = db.Column(db.Integer, default=1)
    parent_file_id = db.Column(db.Integer, db.ForeignKey("client_files.id"), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=utcnow)
    uploaded_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    project = db.relationship("Project", foreign_keys=[project_id])
    task = db.relationship("Task", foreign_keys=[task_id], backref="files")
    uploaded_by = db.relationship("User", foreign_keys=[uploaded_by_user_id])
    versions = db.relationship("ClientFile", remote_side=[id], foreign_keys=[parent_file_id])

    @property
    def size_human(self):
        s = self.size_bytes or 0
        for unit in ("B", "KB", "MB", "GB"):
            if s < 1024:
                return f"{s:.0f} {unit}" if unit == "B" else f"{s:.1f} {unit}"
            s /= 1024
        return f"{s:.1f} TB"

    @property
    def icon_class(self):
        m = (self.mime or "").lower()
        if m.startswith("image/"): return "bi-file-earmark-image"
        if "pdf" in m: return "bi-file-earmark-pdf"
        if "word" in m or m.endswith("/msword") or "document" in m: return "bi-file-earmark-word"
        if "excel" in m or "sheet" in m: return "bi-file-earmark-excel"
        if "zip" in m or "compress" in m: return "bi-file-earmark-zip"
        if "video" in m: return "bi-file-earmark-play"
        if "audio" in m: return "bi-file-earmark-music"
        return "bi-file-earmark"

    @property
    def category_label(self):
        labels = {
            "contract": _("Umowa"),
            "brief": _("Brief"),
            "mockup": _("Makieta"),
            "report": _("Raport"),
            "other": _("Inny"),
        }
        return labels.get(self.category, self.category)


# ── GSC / GA snapshots ────────────────────────────────────────

class GscSnapshot(db.Model):
    __tablename__ = "gsc_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    captured_at = db.Column(db.DateTime, default=utcnow)
    date_range_start = db.Column(db.Date, nullable=True)
    date_range_end = db.Column(db.Date, nullable=True)
    total_clicks = db.Column(db.Integer, default=0)
    total_impressions = db.Column(db.Integer, default=0)
    avg_ctr = db.Column(db.Float, default=0)
    avg_position = db.Column(db.Float, default=0)
    _top_queries = db.Column("top_queries", db.Text, default="[]")
    _top_pages = db.Column("top_pages", db.Text, default="[]")

    top_queries = JsonProperty("_top_queries")
    top_pages = JsonProperty("_top_pages")


class GaSnapshot(db.Model):
    __tablename__ = "ga_snapshots"
    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=False)
    captured_at = db.Column(db.DateTime, default=utcnow)
    date_range_start = db.Column(db.Date, nullable=True)
    date_range_end = db.Column(db.Date, nullable=True)
    users = db.Column(db.Integer, default=0)
    sessions = db.Column(db.Integer, default=0)
    engaged_sessions = db.Column(db.Integer, default=0)
    conversions = db.Column(db.Integer, default=0)
    avg_engagement_time = db.Column(db.Float, default=0)
    _top_sources = db.Column("top_sources", db.Text, default="[]")
    _top_pages = db.Column("top_pages", db.Text, default="[]")

    top_sources = JsonProperty("_top_sources")
    top_pages = JsonProperty("_top_pages")


# ── User (konto w zespole: login, rola, język) ─────────────────

ROLES = ("admin", "member")
LANGUAGES = ("pl", "en")


class User(db.Model):
    """Osoba w zespole. Admin zarządza zespołem i ustawieniami, członek pracuje na danych."""

    __tablename__ = "users"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), nullable=False)
    email = db.Column(db.String(256), default="", index=True)  # login + mapowanie Cloudflare Access
    initials = db.Column(db.String(4), default="")
    avatar_color = db.Column(db.String(16), default="#6c5ce7")
    default_theme = db.Column(db.String(16), default="colorful")  # colorful | minimal
    password_hash = db.Column(db.String(256), default="")  # pusty = konto bez hasła (Cloudflare / demo)
    role = db.Column(db.String(16), default="member")  # admin | member
    is_active = db.Column(db.Boolean, default=True)
    language = db.Column(db.String(5), default=lambda: i18n.DEFAULT_LANGUAGE)  # pl | en, set in the profile
    last_login_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    def set_password(self, password):
        from werkzeug.security import generate_password_hash
        self.password_hash = generate_password_hash(password)  # scrypt (Werkzeug 3)

    def check_password(self, password):
        from werkzeug.security import check_password_hash
        return bool(self.password_hash) and check_password_hash(self.password_hash, password)

    @property
    def is_admin(self):
        return self.role == "admin"

    @property
    def has_password(self):
        return bool(self.password_hash)

    def __repr__(self):
        return f"<User {self.id} {self.name}>"


# ── TaskComment (dyskusja pod zadaniem) ──────────────────────

class TaskComment(db.Model):
    __tablename__ = "task_comments"
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    body = db.Column(db.Text, default="")  # markdown
    _mentions = db.Column("mentioned_user_ids", db.Text, default="[]")  # JSON list of user IDs
    created_at = db.Column(db.DateTime, default=utcnow)
    edited_at = db.Column(db.DateTime, nullable=True)

    user = db.relationship("User", foreign_keys=[user_id])
    mentions = JsonProperty("_mentions")


# ── Mention (@mentions box / skrzynka) ───────────────────────

class Mention(db.Model):
    __tablename__ = "mentions"
    id = db.Column(db.Integer, primary_key=True)
    mentioned_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    author_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    source_type = db.Column(db.String(32), default="task_comment")  # task_comment | note | task_description
    source_id = db.Column(db.Integer, nullable=True)  # id of TaskComment/Note/Task
    task_id = db.Column(db.Integer, db.ForeignKey("tasks.id"), nullable=True)  # for navigation
    snippet = db.Column(db.String(512), default="")  # short excerpt
    read_at = db.Column(db.DateTime, nullable=True)
    created_at = db.Column(db.DateTime, default=utcnow)

    mentioned_user = db.relationship("User", foreign_keys=[mentioned_user_id])
    author = db.relationship("User", foreign_keys=[author_user_id])


# ── Whiteboard (tablice rysunkowe, wspólne dla zespołu) ──────────

class Whiteboard(db.Model):
    __tablename__ = "whiteboards"
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(256), nullable=False, default="Tablica")
    description = db.Column(db.Text, default="")
    canvas_width = db.Column(db.Integer, default=2400)
    canvas_height = db.Column(db.Integer, default=1400)
    bg_color = db.Column(db.String(16), default="#ffffff")
    # Opcjonalne przypisanie do firmy
    company_id = db.Column(db.Integer, db.ForeignKey("companies.id"), nullable=True, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    updated_by_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)

    strokes = db.relationship(
        "WhiteboardStroke",
        backref="whiteboard",
        cascade="all, delete-orphan",
        order_by="WhiteboardStroke.stroke_order, WhiteboardStroke.id",
        primaryjoin="and_(Whiteboard.id==WhiteboardStroke.whiteboard_id, WhiteboardStroke.deleted==False)",
    )
    deletions = db.relationship(
        "WhiteboardDeletion",
        backref="whiteboard",
        cascade="all, delete-orphan",
    )
    created_by = db.relationship("User", foreign_keys=[created_by_user_id])
    updated_by = db.relationship("User", foreign_keys=[updated_by_user_id])
    company = db.relationship("Company", foreign_keys=[company_id])

    @property
    def strokes_count(self):
        return len(self.strokes) if self.strokes else 0


# Dozwolone narzedzia
WHITEBOARD_TOOLS = (
    "pen", "eraser", "highlighter", "text",
    "rect", "ellipse", "line", "arrow",
    "sticky", "image",
)


class WhiteboardStroke(db.Model):
    """Pojedynczy obiekt na tablicy - kreska, ksztalt, tekst, sticky, obraz."""

    __tablename__ = "whiteboard_strokes"
    id = db.Column(db.Integer, primary_key=True)
    whiteboard_id = db.Column(db.Integer, db.ForeignKey("whiteboards.id"), nullable=False, index=True)
    author_user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    tool = db.Column(db.String(16), default="pen")
    color = db.Column(db.String(16), default="#111111")
    fill_color = db.Column(db.String(16), default="")  # dla ksztaltow (pusty = bez fill)
    width = db.Column(db.Float, default=2.5)
    opacity = db.Column(db.Float, default=1.0)
    # Punkty:
    #   pen/highlighter/eraser: [[x,y],[x,y],...]
    #   rect/ellipse/line/arrow: [[x1,y1],[x2,y2]]
    #   text/sticky/image: [[x,y]] (top-left) + width_box/height_box/font_size/text/image_path
    _points = db.Column("points", db.Text, default="[]")
    # Dla tekstu / sticky / image
    text = db.Column(db.Text, default="")
    font_size = db.Column(db.Float, default=18.0)
    width_box = db.Column(db.Float, default=0)   # szerokosc boksu (sticky/image)
    height_box = db.Column(db.Float, default=0)  # wysokosc boksu
    image_path = db.Column(db.String(512), default="")  # wzgledem output/whiteboard_images/
    # Z-index / kolejnosc warstw (niskie = z tylu, wysokie = z przodu)
    stroke_order = db.Column(db.Float, default=0.0, index=True)
    # Soft delete - dla synchronizacji kasowania miedzy klientami
    deleted = db.Column(db.Boolean, default=False, index=True)
    created_at = db.Column(db.DateTime, default=utcnow)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow)

    points = JsonProperty("_points")
    author = db.relationship("User", foreign_keys=[author_user_id])


class WhiteboardDeletion(db.Model):
    """Log skasowan - do propagacji do pollingujacych klientow."""
    __tablename__ = "whiteboard_deletions"
    id = db.Column(db.Integer, primary_key=True)
    whiteboard_id = db.Column(db.Integer, db.ForeignKey("whiteboards.id"), nullable=False, index=True)
    stroke_id = db.Column(db.Integer, nullable=False)
    deleted_at = db.Column(db.DateTime, default=utcnow)


class WhiteboardCursor(db.Model):
    """Live cursor - pozycja uzytkownika na tablicy. Update przez heartbeat."""
    __tablename__ = "whiteboard_cursors"
    id = db.Column(db.Integer, primary_key=True)
    whiteboard_id = db.Column(db.Integer, db.ForeignKey("whiteboards.id"), nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False)
    x = db.Column(db.Float, default=0)
    y = db.Column(db.Float, default=0)
    updated_at = db.Column(db.DateTime, default=utcnow, onupdate=utcnow, index=True)
    __table_args__ = (db.UniqueConstraint("whiteboard_id", "user_id", name="uq_wb_user_cursor"),)

    user = db.relationship("User", foreign_keys=[user_id])


# ── AuditLog (historia zmian dla detail views) ───────────────

class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    table_name = db.Column(db.String(64), nullable=False)  # tasks | notes | payments ...
    record_id = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=True)
    action = db.Column(db.String(32), default="update")  # create | update | delete | status_change | comment
    field = db.Column(db.String(64), default="")
    old_value = db.Column(db.Text, default="")
    new_value = db.Column(db.Text, default="")
    note = db.Column(db.String(512), default="")
    created_at = db.Column(db.DateTime, default=utcnow)

    user = db.relationship("User", foreign_keys=[user_id])

    @staticmethod
    def table_labels():
        return {
            "tasks": _("Zadania"), "notes": _("Notatki"), "payments": _("Płatności"), "expenses": _("Koszty"),
            "companies": _("Firmy"), "visits": _("Wizyty"), "content_posts": _("Content"),
            "contracts": _("Umowy"), "projects": _("Projekty"), "audits": _("Audyty"),
        }

    @staticmethod
    def action_labels():
        return {
            "create": _("Dodanie"), "update": _("Zmiana"), "delete": _("Usunięcie"),
            "status_change": _("Zmiana statusu"), "comment": _("Komentarz"),
        }

    @property
    def field_label(self):
        labels = {
            "status": _("status"), "priority": _("priorytet"), "deadline": _("termin"), "title": _("tytuł"),
            "description": _("opis"), "files": _("pliki"), "subtasks": _("podzadania"),
        }
        return labels.get(self.field, self.field)

    def value_label(self, value):
        """Task status and priority codes as labels; other values as stored."""
        if self.table_name == "tasks" and self.field == "status":
            return task_status_label(value)
        if self.table_name == "tasks" and self.field == "priority":
            return task_priority_label(value)
        return value


# ── Deleting records with links ───────────────────────────────
# Explicit, because SQLite does not enforce foreign keys (a missing cascade only leaves orphaned
# rows) while PostgreSQL rejects a delete that leaves references behind.

def _null(column, ids):
    """UPDATE ... SET column = NULL WHERE column IN ids."""
    if ids:
        column.class_.query.filter(column.in_(ids)).update({column: None}, synchronize_session=False)


def delete_whiteboard(board):
    """A board with all its elements: also the erased ones (soft delete), which the `strokes`
    relationship does not see, the deletion log and live cursors. Image files stay on disk:
    a duplicated board points at the same files."""
    for model in (WhiteboardStroke, WhiteboardDeletion, WhiteboardCursor):
        model.query.filter(model.whiteboard_id == board.id).delete(synchronize_session=False)
    db.session.expire(board)
    db.session.delete(board)


def delete_company(company):
    """A company with what belongs to it (the cascade relationships: projects with their tasks,
    audits, offers, files, contracts, content, payments...). Records that live on their own stay
    and lose only the link: tasks pinned to the company outside its projects, costs, e-mail
    history and whiteboards. The caller commits."""
    cid = company.id
    project_ids = [p.id for p in company.projects]
    post_ids = [p.id for p in company.content_posts]
    file_ids = [f.id for f in company.files]
    audit_ids = [a.id for a in company.audits]
    doomed = {t.id for t in Task.query.filter(Task.project_id.in_(project_ids))} if project_ids else set()
    frontier = set(doomed)
    while frontier:  # subtasks go with their parent (Task.subtasks cascade)
        frontier = {t.id for t in Task.query.filter(Task.parent_task_id.in_(frontier))} - doomed
        doomed |= frontier

    if doomed:
        Mention.query.filter(Mention.task_id.in_(doomed)).delete(synchronize_session=False)
    _null(ClientFile.task_id, doomed)
    _null(ClientFile.project_id, project_ids)
    _null(ClientFile.parent_file_id, file_ids)
    _null(Contract.generated_pdf_file_id, file_ids)
    _null(Expense.attachment_file_id, file_ids)
    _null(Task.content_post_id, post_ids)
    _null(Note.project_id, project_ids)
    _null(Offer.audit_id, audit_ids)
    Task.query.filter(Task.company_id == cid, ~Task.id.in_(doomed) if doomed else True).update(
        {Task.company_id: None}, synchronize_session=False)
    for column in (Expense.client_id, EmailLog.company_id, Whiteboard.company_id):
        _null(column, [cid])
    db.session.expire_all()
    db.session.delete(db.session.get(Company, cid))


# ── Schema extension (idempotent ALTER TABLE for new columns) ─

def ensure_schema():
    """
    Add new columns to existing tables without dropping data.
    SQLite supports ALTER TABLE ADD COLUMN - run after db.create_all().
    """
    from sqlalchemy import inspect, text

    inspector = inspect(db.engine)
    if not inspector.has_table("companies"):
        return
    if db.engine.dialect.name != "sqlite":
        # PostgreSQL (i inne) startują od pełnego schematu z create_all(); łatki poniżej
        # dotyczą tylko starszych baz SQLite sprzed kolejnych kolumn.
        ensure_indexes()
        return

    existing_cols = {c["name"] for c in inspector.get_columns("companies")}
    alter_companies = [
        ("is_retainer", "BOOLEAN DEFAULT 0"),
        ("monthly_fee_net", "FLOAT"),
        ("billing_day", "INTEGER DEFAULT 1"),
        ("retainer_started_at", "DATE"),
        ("client_legal_name", "VARCHAR(512) DEFAULT ''"),
        ("client_nip", "VARCHAR(32) DEFAULT ''"),
        ("client_address", "TEXT DEFAULT ''"),
        ("portal_token", "VARCHAR(128)"),
        ("gsc_site_url", "VARCHAR(512) DEFAULT ''"),
        ("ga_property_id", "VARCHAR(64) DEFAULT ''"),
    ]
    with db.engine.begin() as conn:
        for name, ddl in alter_companies:
            if name not in existing_cols:
                conn.execute(text(f"ALTER TABLE companies ADD COLUMN {name} {ddl}"))

    settings_cols = {c["name"] for c in inspector.get_columns("settings")} if inspector.has_table("settings") else set()
    alter_settings = [
        ("smtp_host", "VARCHAR(256) DEFAULT ''"),
        ("smtp_port", "INTEGER DEFAULT 587"),
        ("smtp_user", "VARCHAR(256) DEFAULT ''"),
        ("smtp_password_encrypted", "TEXT DEFAULT ''"),
        ("smtp_from_addr", "VARCHAR(256) DEFAULT ''"),
        ("smtp_use_tls", "BOOLEAN DEFAULT 1"),
        ("fernet_key", "TEXT DEFAULT ''"),
        ("google_oauth_client_id", "VARCHAR(512) DEFAULT ''"),
        ("google_oauth_client_secret", "VARCHAR(512) DEFAULT ''"),
        ("gsc_refresh_token", "TEXT DEFAULT ''"),
        ("ga_refresh_token", "TEXT DEFAULT ''"),
        ("ga_property_id_default", "VARCHAR(64) DEFAULT ''"),
        ("default_vat_rate", "FLOAT DEFAULT 23.0"),
        ("company_vat_payer", "BOOLEAN DEFAULT 1"),
        ("fiscal_year_start_month", "INTEGER DEFAULT 1"),
        ("agency_legal_name", "VARCHAR(512) DEFAULT ''"),
        ("agency_nip", "VARCHAR(32) DEFAULT ''"),
        ("agency_address", "TEXT DEFAULT ''"),
        ("agency_bank_account", "VARCHAR(64) DEFAULT ''"),
        ("openrouter_api_key_encrypted", "TEXT DEFAULT ''"),
        ("assistant_model", "VARCHAR(128) DEFAULT 'google/gemini-3.1-flash-lite-preview'"),
        ("assistant_enabled", "BOOLEAN DEFAULT 0"),
        ("pii_masking_enabled", "BOOLEAN DEFAULT 0"),
        ("pii_masking_ner", "BOOLEAN DEFAULT 0"),
    ]
    with db.engine.begin() as conn:
        for name, ddl in alter_settings:
            if name not in settings_cols:
                conn.execute(text(f"ALTER TABLE settings ADD COLUMN {name} {ddl}"))

    notes_cols = {c["name"] for c in inspector.get_columns("notes")} if inspector.has_table("notes") else set()
    alter_notes = [
        ("project_id", "INTEGER"),
        ("scope", "VARCHAR(16) DEFAULT 'company'"),
        ("title", "VARCHAR(256) DEFAULT ''"),
        ("pinned", "BOOLEAN DEFAULT 0"),
    ]
    with db.engine.begin() as conn:
        for name, ddl in alter_notes:
            if name not in notes_cols:
                conn.execute(text(f"ALTER TABLE notes ADD COLUMN {name} {ddl}"))

    # Relax NOT NULL on notes.company_id (oryginalnie było NOT NULL - teraz scope=personal wymaga NULL)
    if inspector.has_table("notes"):
        notes_info = inspector.get_columns("notes")
        company_col = next((c for c in notes_info if c["name"] == "company_id"), None)
        if company_col and not company_col.get("nullable", True):
            with db.engine.begin() as conn:
                conn.execute(text("""
                    CREATE TABLE notes_new (
                        id INTEGER PRIMARY KEY,
                        company_id INTEGER,
                        project_id INTEGER,
                        scope VARCHAR(16) DEFAULT 'company',
                        title VARCHAR(256) DEFAULT '',
                        content TEXT NOT NULL,
                        note_type VARCHAR(32) DEFAULT 'general',
                        pinned BOOLEAN DEFAULT 0,
                        created_at DATETIME,
                        FOREIGN KEY(company_id) REFERENCES companies(id),
                        FOREIGN KEY(project_id) REFERENCES projects(id)
                    )
                """))
                conn.execute(text("""
                    INSERT INTO notes_new (id, company_id, project_id, scope, title, content, note_type, pinned, created_at)
                    SELECT id, company_id, project_id,
                           COALESCE(scope, 'company'), COALESCE(title, ''),
                           content, note_type, COALESCE(pinned, 0), created_at
                    FROM notes
                """))
                conn.execute(text("DROP TABLE notes"))
                conn.execute(text("ALTER TABLE notes_new RENAME TO notes"))

    # Attribution FK (created_by_user_id, updated_by_user_id) - wszystkie kluczowe tabele
    attribution_tables = [
        "tasks", "notes", "content_posts", "payments", "expenses",
        "projects", "contracts", "visits", "client_credentials",
        "subscriptions", "knowledge_articles", "companies",
    ]
    with db.engine.begin() as conn:
        for tbl in attribution_tables:
            if not inspector.has_table(tbl):
                continue
            cols = {c["name"] for c in inspector.get_columns(tbl)}
            if "created_by_user_id" not in cols:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN created_by_user_id INTEGER"))
            if "updated_by_user_id" not in cols:
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN updated_by_user_id INTEGER"))
            if "updated_at" not in cols and tbl in ("tasks", "notes", "content_posts", "knowledge_articles"):
                conn.execute(text(f"ALTER TABLE {tbl} ADD COLUMN updated_at DATETIME"))

    # Task: parent_task_id
    if inspector.has_table("tasks"):
        task_cols = {c["name"] for c in inspector.get_columns("tasks")}
        with db.engine.begin() as conn:
            if "parent_task_id" not in task_cols:
                conn.execute(text("ALTER TABLE tasks ADD COLUMN parent_task_id INTEGER"))

    # ClientFile: task_id + uploaded_by_user_id
    if inspector.has_table("client_files"):
        cf_cols = {c["name"] for c in inspector.get_columns("client_files")}
        with db.engine.begin() as conn:
            if "task_id" not in cf_cols:
                conn.execute(text("ALTER TABLE client_files ADD COLUMN task_id INTEGER"))
            if "uploaded_by_user_id" not in cf_cols:
                conn.execute(text("ALTER TABLE client_files ADD COLUMN uploaded_by_user_id INTEGER"))

    # User: email (dla Cloudflare Access mapping)
    if inspector.has_table("users"):
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        with db.engine.begin() as conn:
            if "email" not in user_cols:
                conn.execute(text("ALTER TABLE users ADD COLUMN email VARCHAR(256) DEFAULT ''"))

    # WhiteboardStroke: text + font_size + nowe pola dla ksztaltow/sticky/image
    if inspector.has_table("whiteboard_strokes"):
        ws_cols = {c["name"] for c in inspector.get_columns("whiteboard_strokes")}
        with db.engine.begin() as conn:
            if "text" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN text TEXT DEFAULT ''"))
            if "font_size" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN font_size FLOAT DEFAULT 18.0"))
            if "fill_color" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN fill_color VARCHAR(16) DEFAULT ''"))
            if "width_box" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN width_box FLOAT DEFAULT 0"))
            if "height_box" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN height_box FLOAT DEFAULT 0"))
            if "image_path" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN image_path VARCHAR(512) DEFAULT ''"))
            if "stroke_order" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN stroke_order FLOAT DEFAULT 0.0"))
            if "deleted" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN deleted BOOLEAN DEFAULT 0"))
            if "updated_at" not in ws_cols:
                conn.execute(text("ALTER TABLE whiteboard_strokes ADD COLUMN updated_at DATETIME"))

    # Konta: hasło, rola, aktywność, język (bazy sprzed logowania hasłem)
    if inspector.has_table("users"):
        user_cols = {c["name"] for c in inspector.get_columns("users")}
        boolean_true = "TRUE" if db.engine.dialect.name == "postgresql" else "1"
        with db.engine.begin() as conn:
            for name, ddl in (
                ("password_hash", "VARCHAR(256) DEFAULT ''"),
                ("role", "VARCHAR(16) DEFAULT 'member'"),
                ("is_active", f"BOOLEAN DEFAULT {boolean_true}"),
                ("language", "VARCHAR(5) DEFAULT 'pl'"),
                ("last_login_at", "TIMESTAMP"),
            ):
                if name not in user_cols:
                    conn.execute(text(f"ALTER TABLE users ADD COLUMN {name} {ddl}"))

    # Whiteboard: company_id (przypisanie do klienta)
    if inspector.has_table("whiteboards"):
        wb_cols = {c["name"] for c in inspector.get_columns("whiteboards")}
        with db.engine.begin() as conn:
            if "company_id" not in wb_cols:
                conn.execute(text("ALTER TABLE whiteboards ADD COLUMN company_id INTEGER"))

    ensure_indexes()


# Indeksy pod filtry używane na dashboardzie, listach i w asystencie AI. Kolumny bez
# indeksu w modelach (np. tasks.status + deadline) były skanowane w całości przy każdym
# wejściu na dashboard. CREATE INDEX IF NOT EXISTS jest idempotentne - bezpieczne przy
# każdym starcie, także na starszych bazach.
_INDEXES = [
    ("ix_tasks_deadline", "tasks", "deadline"),
    ("ix_tasks_status_done_at", "tasks", "status, done_at"),
    ("ix_tasks_company_id", "tasks", "company_id"),
    ("ix_payments_status_due_at", "payments", "status, due_at"),
    ("ix_payments_paid_at", "payments", "paid_at"),
    ("ix_payments_company_id", "payments", "company_id"),
    ("ix_expenses_payment_date", "expenses", "payment_date"),
    ("ix_companies_pipeline_stage", "companies", "pipeline_stage"),
    ("ix_visits_scheduled_at", "visits", "scheduled_at"),
    ("ix_content_posts_status", "content_posts", "status"),
    ("ix_notes_company_id", "notes", "company_id"),
    ("ix_audit_log_created_at", "audit_log", "created_at"),
]


def ensure_indexes():
    """Utwórz brakujące indeksy (idempotentnie). Brak tabeli/kolumny w starej bazie = pomiń."""
    from sqlalchemy import text

    for name, table, columns in _INDEXES:
        try:
            with db.engine.begin() as conn:
                conn.execute(text(f"CREATE INDEX IF NOT EXISTS {name} ON {table} ({columns})"))
        except Exception:  # noqa: BLE001 - indeks to optymalizacja, nie może zablokować startu
            pass


# ── Seed defaults ─────────────────────────────────────────────

def seed_defaults():
    """Create default packages, email/contract templates, and knowledge articles.

    Nie tworzy już kont: pierwsze konto (admin) zakłada strona /setup albo
    scripts/create_admin.py, a konta demo - scripts/seed_test_data.py.

    Domyślnie po polsku; z DEFAULT_LANGUAGE=en (agencja anglojęzyczna) świeża baza dostaje
    angielskie wersje z _english_*() poniżej. Istniejących danych nic tu nie tłumaczy.
    """
    english = i18n.DEFAULT_LANGUAGE == "en"
    # Starsze bazy: konta sprzed ról. Jeśli nikt nie jest adminem, adminem zostaje
    # najstarsze aktywne konto, żeby ktoś mógł zarządzać zespołem.
    if User.query.count() and not User.query.filter_by(role="admin").count():
        first = User.query.order_by(User.id).first()
        first.role = "admin"
        db.session.commit()

    if Package.query.count() == 0:
        defaults = _english_packages() if english else [
            Package(
                name="START",
                description="Quick wins - szybkie rezultaty w 30 dni",
                price=1500,
                duration_days=30,
                _deliverables=json.dumps([
                    "Optymalizacja wizytówki Google Business Profile",
                    "Kluczowe poprawki na stronie (CTA, formularze, kontakt)",
                    "Wdrożenie śledzenia konwersji (GA4)",
                    "System pozyskiwania opinii od klientów",
                ], ensure_ascii=False),
                _expected_results=json.dumps([
                    "Lepsza widoczność w Google Maps",
                    "Więcej telefonów i zapytań z wizytówki",
                    "Podstawowe dane o ruchu i konwersjach",
                ], ensure_ascii=False),
                _payment_variants=json.dumps(["Jednorazowo"], ensure_ascii=False),
                is_active=True,
            ),
            Package(
                name="GROWTH",
                description="Rozszerzony pakiet - wzrost w 60 dni",
                price=3500,
                duration_days=60,
                _deliverables=json.dumps([
                    "Wszystko z pakietu START",
                    "Treści SEO lokalne (5 podstron zoptymalizowanych)",
                    "Przebudowa kluczowych sekcji strony",
                    "System zbierania i zarządzania opiniami",
                    "Podstawowa kampania Google Ads (setup + 2 tyg. zarządzania)",
                ], ensure_ascii=False),
                _expected_results=json.dumps([
                    "Wzrost widoczności na frazy lokalne",
                    "Więcej organicznego ruchu na stronie",
                    "Pierwsze leady z kampanii płatnej",
                    "Regularny wzrost opinii",
                ], ensure_ascii=False),
                _payment_variants=json.dumps(["Jednorazowo", "2 raty"], ensure_ascii=False),
                is_active=True,
            ),
            Package(
                name="PREMIUM",
                description="Pełne przejęcie marketingu - współpraca ongoing",
                price=5000,
                duration_days=90,
                _deliverables=json.dumps([
                    "Strategia marketingu lokalnego",
                    "Content plan + realizacja (blog, social media)",
                    "Pełne SEO lokalne (on-site + off-site)",
                    "Zarządzanie kampaniami Google Ads",
                    "Miesięczne raportowanie i optymalizacja",
                    "Dedykowany opiekun klienta",
                ], ensure_ascii=False),
                _expected_results=json.dumps([
                    "Dominacja w wynikach lokalnych",
                    "Stały napływ nowych klientów",
                    "Mierzalny ROI z działań marketingowych",
                    "Profesjonalny wizerunek online",
                ], ensure_ascii=False),
                _payment_variants=json.dumps(["Miesięcznie", "Kwartalnie"], ensure_ascii=False),
                is_active=True,
            ),
        ]
        db.session.add_all(defaults)
        db.session.commit()

    if EmailTemplate.query.count() == 0:
        email_seeds = _english_email_templates() if english else [
            EmailTemplate(
                key="welcome",
                name="Powitanie klienta",
                subject_template="Witamy w {{ agency.name }} - kolejne kroki współpracy",
                body_template=(
                    "<p>Dzień dobry {{ company.contact_person or company.name }},</p>"
                    "<p>Dziękujemy za zaufanie i wybór naszej agencji. Od dziś zaczynamy pracę nad widocznością "
                    "<b>{{ company.name }}</b> w Google.</p>"
                    "<p><b>Najbliższe kroki:</b></p>"
                    "<ol>"
                    "<li>Dostęp do Google Business Profile, Search Console i Analytics.</li>"
                    "<li>Audyt wyjściowy (do 7 dni).</li>"
                    "<li>Plan działań na pierwszy miesiąc.</li>"
                    "</ol>"
                    "<p>W razie pytań jesteśmy do dyspozycji pod tym adresem.</p>"
                    "<p>Pozdrawiamy,<br>{{ agency.name }}</p>"
                ),
                placeholders_doc="{{ company.name }}, {{ company.contact_person }}, {{ agency.name }}",
            ),
            EmailTemplate(
                key="payment_reminder",
                name="Przypomnienie o płatności",
                subject_template="Przypomnienie o płatności {{ payment.payment_number }} - {{ payment.title }}",
                body_template=(
                    "<p>Dzień dobry {{ company.contact_person or company.name }},</p>"
                    "<p>Uprzejmie przypominamy, że kwota <b>{{ payment.amount_gross }} zł brutto</b> "
                    "z tytułu &bdquo;{{ payment.title }}&rdquo; była płatna do {{ payment.due_at.strftime('%d.%m.%Y') if payment.due_at else '-' }}.</p>"
                    "<p>Prosimy o uregulowanie w najbliższym dogodnym terminie.</p>"
                    "<p>Pozdrawiamy,<br>{{ agency.name }}</p>"
                ),
                placeholders_doc="{{ payment.* }}, {{ company.* }}, {{ agency.* }}",
            ),
            EmailTemplate(
                key="follow_up_after_visit",
                name="Follow-up po wizycie",
                subject_template="Podsumowanie naszego spotkania - {{ company.name }}",
                body_template=(
                    "<p>Dzień dobry {{ company.contact_person or company.name }},</p>"
                    "<p>Dziękujemy za spotkanie. Poniżej krótkie podsumowanie ustaleń:</p>"
                    "<ul>"
                    "<li>Punkt 1 (uzupełnij przed wysyłką)</li>"
                    "<li>Punkt 2</li>"
                    "</ul>"
                    "<p>Kolejny krok po naszej stronie: przygotowanie oferty.</p>"
                    "<p>Pozdrawiamy,<br>{{ agency.name }}</p>"
                ),
                placeholders_doc="{{ company.* }}, {{ agency.* }}",
            ),
            EmailTemplate(
                key="audit_delivery",
                name="Przekazanie audytu",
                subject_template="Audyt marketingowy dla {{ company.name }} - gotowy",
                body_template=(
                    "<p>Dzień dobry {{ company.contact_person or company.name }},</p>"
                    "<p>W załączeniu przesyłamy audyt marketingowy Państwa firmy. Znajdą tam Państwo:</p>"
                    "<ul>"
                    "<li>Ocenę 5 kluczowych obszarów (1-5)</li>"
                    "<li>Główne problemy i szanse</li>"
                    "<li>Konkretny plan działania na 90 dni</li>"
                    "</ul>"
                    "<p>Chętnie omówimy wyniki podczas wspólnej rozmowy.</p>"
                    "<p>Pozdrawiamy,<br>{{ agency.name }}</p>"
                ),
                placeholders_doc="{{ company.* }}, {{ agency.* }}, {{ audit.* }}",
            ),
        ]
        db.session.add_all(email_seeds)
        db.session.commit()

    if ContractTemplate.query.count() == 0:
        contract_seeds = _english_contract_templates() if english else [
            ContractTemplate(
                key="seo_retainer",
                name="Umowa abonamentowa SEO",
                body_template=(
                    "UMOWA O ŚWIADCZENIE USŁUG SEO\n\n"
                    "Zawarta dnia {{ today }} pomiędzy:\n\n"
                    "{{ agency.legal_name }}, NIP: {{ agency.nip }}, adres: {{ agency.address }},\n"
                    "zwaną dalej Wykonawcą,\n\n"
                    "a\n\n"
                    "{{ client.legal_name or client.name }}, NIP: {{ client.nip }}, adres: {{ client.address }},\n"
                    "zwaną dalej Zleceniodawcą.\n\n"
                    "§ 1. PRZEDMIOT UMOWY\n"
                    "Wykonawca zobowiązuje się do świadczenia usług pozycjonowania strony {{ client.website }} "
                    "w wyszukiwarce Google, zgodnie z planem działań stanowiącym załącznik do niniejszej umowy.\n\n"
                    "§ 2. WYNAGRODZENIE\n"
                    "Miesięczne wynagrodzenie Wykonawcy wynosi {{ monthly_fee_net }} zł netto "
                    "({{ monthly_fee_gross }} zł brutto) i płatne jest do {{ billing_day }}. dnia każdego miesiąca "
                    "na rachunek: {{ agency.bank_account }}.\n\n"
                    "§ 3. OKRES OBOWIĄZYWANIA\n"
                    "Umowa zostaje zawarta na czas nieokreślony z miesięcznym okresem wypowiedzenia.\n\n"
                    "§ 4. POSTANOWIENIA KOŃCOWE\n"
                    "{{ extra_clauses }}\n\n"
                    "Podpisy:\n\n"
                    ".................................\t\t.................................\n"
                    "Wykonawca\t\t\t\t\tZleceniodawca"
                ),
                placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ monthly_fee_net }}, {{ monthly_fee_gross }}, {{ billing_day }}, {{ extra_clauses }}",
            ),
            ContractTemplate(
                key="website_build",
                name="Umowa wykonania strony WWW",
                body_template=(
                    "UMOWA O WYKONANIE STRONY INTERNETOWEJ\n\n"
                    "Zawarta dnia {{ today }} pomiędzy:\n\n"
                    "{{ agency.legal_name }}, NIP: {{ agency.nip }}, adres: {{ agency.address }},\n"
                    "zwaną dalej Wykonawcą,\n\n"
                    "a\n\n"
                    "{{ client.legal_name or client.name }}, NIP: {{ client.nip }}, adres: {{ client.address }},\n"
                    "zwaną dalej Zamawiającym.\n\n"
                    "§ 1. PRZEDMIOT UMOWY\n"
                    "Wykonawca zobowiązuje się do zaprojektowania i wdrożenia strony internetowej "
                    "pod adresem {{ domain }}, zgodnie z briefem zaakceptowanym przez obie strony.\n\n"
                    "§ 2. WYNAGRODZENIE I PŁATNOŚCI\n"
                    "Łączne wynagrodzenie wynosi {{ total_net }} zł netto ({{ total_gross }} zł brutto) "
                    "i płatne jest w następujących etapach:\n"
                    "a) {{ payment_stage_1 }} - po podpisaniu umowy,\n"
                    "b) {{ payment_stage_2 }} - po akceptacji projektu graficznego,\n"
                    "c) {{ payment_stage_3 }} - po oddaniu strony do użytku.\n\n"
                    "§ 3. TERMIN REALIZACJI\n"
                    "Strona zostanie uruchomiona w terminie do {{ deadline }}.\n\n"
                    "§ 4. PRZENIESIENIE PRAW\n"
                    "Z chwilą uregulowania pełnego wynagrodzenia, Wykonawca przenosi na Zamawiającego "
                    "autorskie prawa majątkowe do zrealizowanych utworów (projektu graficznego, kodu, treści).\n\n"
                    "§ 5. POSTANOWIENIA KOŃCOWE\n"
                    "{{ extra_clauses }}\n\n"
                    "Podpisy:\n\n"
                    ".................................\t\t.................................\n"
                    "Wykonawca\t\t\t\t\tZamawiający"
                ),
                placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ domain }}, {{ total_net }}, {{ total_gross }}, {{ payment_stage_1..3 }}, {{ deadline }}",
            ),
            ContractTemplate(
                key="rodo",
                name="Umowa powierzenia przetwarzania (RODO)",
                body_template=(
                    "UMOWA POWIERZENIA PRZETWARZANIA DANYCH OSOBOWYCH\n\n"
                    "Zawarta dnia {{ today }} pomiędzy:\n\n"
                    "{{ client.legal_name or client.name }}, NIP: {{ client.nip }}, adres: {{ client.address }},\n"
                    "zwaną dalej Administratorem,\n\n"
                    "a\n\n"
                    "{{ agency.legal_name }}, NIP: {{ agency.nip }}, adres: {{ agency.address }},\n"
                    "zwaną dalej Podmiotem przetwarzającym.\n\n"
                    "§ 1. PRZEDMIOT\n"
                    "Administrator powierza Podmiotowi przetwarzającemu przetwarzanie danych osobowych "
                    "w zakresie niezbędnym do realizacji umowy głównej z dnia {{ main_contract_date }}.\n\n"
                    "§ 2. KATEGORIE DANYCH\n"
                    "Dane kontaktowe klientów Administratora: imię, nazwisko, e-mail, telefon, adres.\n\n"
                    "§ 3. OBOWIĄZKI PODMIOTU PRZETWARZAJĄCEGO\n"
                    "Podmiot przetwarzający zobowiązuje się do przetwarzania danych wyłącznie zgodnie z poleceniami "
                    "Administratora, zapewnienia odpowiednich środków technicznych i organizacyjnych oraz "
                    "zgłaszania naruszeń w terminie 24 godzin.\n\n"
                    "§ 4. OKRES OBOWIĄZYWANIA\n"
                    "Umowa obowiązuje przez czas trwania umowy głównej. Po jej zakończeniu Podmiot "
                    "przetwarzający zwróci lub usunie powierzone dane.\n\n"
                    "Podpisy:\n\n"
                    ".................................\t\t.................................\n"
                    "Administrator\t\t\t\tPodmiot przetwarzający"
                ),
                placeholders_doc="{{ today }}, {{ main_contract_date }}, {{ agency.* }}, {{ client.* }}",
            ),
            ContractTemplate(
                key="nda",
                name="Umowa poufności (NDA)",
                body_template=(
                    "UMOWA O ZACHOWANIU POUFNOŚCI (NDA)\n\n"
                    "Zawarta dnia {{ today }} pomiędzy:\n\n"
                    "{{ agency.legal_name }}, NIP: {{ agency.nip }}, adres: {{ agency.address }},\n"
                    "a\n\n"
                    "{{ client.legal_name or client.name }}, NIP: {{ client.nip }}, adres: {{ client.address }}.\n\n"
                    "§ 1. INFORMACJE POUFNE\n"
                    "Strony zobowiązują się do zachowania w tajemnicy wszelkich informacji biznesowych, "
                    "technicznych i handlowych uzyskanych w trakcie współpracy.\n\n"
                    "§ 2. OKRES OBOWIĄZYWANIA\n"
                    "Zobowiązanie do poufności obowiązuje przez {{ duration_years }} lata od daty podpisania umowy.\n\n"
                    "§ 3. WYJĄTKI\n"
                    "Obowiązek nie dotyczy informacji publicznie dostępnych lub uzyskanych niezależnie.\n\n"
                    "§ 4. KARA UMOWNA\n"
                    "Naruszenie obowiązku poufności skutkuje karą umowną w wysokości {{ penalty }} zł.\n\n"
                    "Podpisy:\n\n"
                    ".................................\t\t.................................\n"
                    "Strona A\t\t\t\t\tStrona B"
                ),
                placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ duration_years }}, {{ penalty }}",
            ),
        ]
        db.session.add_all(contract_seeds)
        db.session.commit()

    if KnowledgeArticle.query.count() == 0:
        knowledge_seeds = _english_knowledge_articles() if english else [
            KnowledgeArticle(
                title="Procedura wdrożenia nowego klienta",
                category="Onboarding",
                body=(
                    "# Onboarding klienta - checklist\n\n"
                    "## Dzień 0 (podpisanie umowy)\n"
                    "- [ ] Umowa główna podpisana i zarchiwizowana w plikach klienta\n"
                    "- [ ] Umowa RODO podpisana\n"
                    "- [ ] Utworzony folder w Dropbox/Drive\n"
                    "- [ ] Wysłany e-mail powitalny (szablon: welcome)\n\n"
                    "## Dni 1-3 (zebranie dostępów)\n"
                    "- [ ] Google Business Profile - uprawnienia dla agencji\n"
                    "- [ ] Google Search Console - dodany użytkownik\n"
                    "- [ ] Google Analytics 4 - dodany użytkownik\n"
                    "- [ ] WordPress admin - konto dla agencji\n"
                    "- [ ] Hosting / DNS - dane dostępowe w Bitwarden\n\n"
                    "## Dni 4-7 (audyt wyjściowy)\n"
                    "- [ ] Audyt SEO (wbudowany w apkę)\n"
                    "- [ ] Analiza konkurencji (3 konkurenci)\n"
                    "- [ ] PageSpeed raport\n"
                    "- [ ] Plan 90 dni przygotowany i wysłany\n"
                ),
                _tags=json.dumps(["onboarding", "checklist"], ensure_ascii=False),
                pinned=True,
            ),
            KnowledgeArticle(
                title="Scenariusz pierwszej rozmowy handlowej",
                category="Sprzedaż",
                body=(
                    "# Pierwsza rozmowa z klientem\n\n"
                    "## Cel rozmowy\n"
                    "Zrozumieć sytuację klienta i zdecydować czy jest dopasowanie (fit check).\n\n"
                    "## Pytania do zadania\n"
                    "1. Jak teraz pozyskujecie klientów?\n"
                    "2. Ile kosztuje was pozyskanie jednego klienta?\n"
                    "3. Ile jest wart jeden klient (LTV)?\n"
                    "4. Co próbowaliście wcześniej w marketingu i czemu nie zadziałało?\n"
                    "5. Jakie macie oczekiwania co do efektów za 3 / 6 / 12 miesięcy?\n"
                    "6. Kto decyduje o wdrożeniu? Jak wygląda proces decyzyjny?\n\n"
                    "## Czerwone flagi (lead słaby)\n"
                    "- Brak mierzenia obecnych działań\n"
                    "- Oczekiwanie natychmiastowych efektów\n"
                    "- Budżet < 1500 zł/mc\n"
                    "- Brak decyzyjności\n"
                ),
                _tags=json.dumps(["sprzedaż", "rozmowa"], ensure_ascii=False),
                pinned=True,
            ),
            KnowledgeArticle(
                title="Checklist audytu SEO",
                category="Procedury audytu",
                body=(
                    "# Co sprawdzamy w audycie SEO\n\n"
                    "## On-site (strona)\n"
                    "- Meta title i description na każdej podstronie\n"
                    "- Struktura nagłówków H1-H3\n"
                    "- Linkowanie wewnętrzne\n"
                    "- Schema markup (LocalBusiness / Product / Article)\n"
                    "- HTTPS / SSL\n"
                    "- Mobile friendly (test Google)\n"
                    "- Core Web Vitals (PageSpeed)\n\n"
                    "## Google Business Profile\n"
                    "- Kompletne dane (NAP)\n"
                    "- Kategorie główna + dodatkowe\n"
                    "- Zdjęcia, posty, opinie\n"
                    "- Odpowiedzi na opinie\n\n"
                    "## Off-site\n"
                    "- Profile w katalogach (Panorama, PKT, Yelp)\n"
                    "- Spójność NAP we wszystkich źródłach\n"
                    "- Profil linkowy (Ahrefs/ręcznie)\n"
                ),
                _tags=json.dumps(["audyt", "checklist"], ensure_ascii=False),
            ),
            KnowledgeArticle(
                title="Szablon raportu miesięcznego dla klienta",
                category="Raportowanie",
                body=(
                    "# Co zawiera raport miesięczny\n\n"
                    "## Sekcje\n"
                    "1. **Podsumowanie miesiąca** - co zostało zrobione (max 5 punktów)\n"
                    "2. **Metryki** - wzrost/spadek pozycji, ruchu, konwersji\n"
                    "3. **Najlepsze frazy** - top 10 z największymi zmianami\n"
                    "4. **Problemy i blokery** - co stanęło na drodze\n"
                    "5. **Plan na kolejny miesiąc** - 3-5 zadań priorytetowych\n\n"
                    "## Zasady\n"
                    "- Max 2 strony PDF\n"
                    "- Konkretne liczby, nie ogólniki\n"
                    "- Jeden wykres per sekcja metryk\n"
                    "- Język prosty, bez branżowego żargonu\n"
                ),
                _tags=json.dumps(["raport", "komunikacja"], ensure_ascii=False),
            ),
        ]
        db.session.add_all(knowledge_seeds)
        db.session.commit()


# English defaults for a fresh database with DEFAULT_LANGUAGE=en (an English-speaking agency).
# Same keys, prices and Jinja placeholders as the Polish seeds above - only the text differs.

def _english_packages():
    return [
        Package(
            name="START",
            description="Quick wins - fast results in 30 days",
            price=1500,
            duration_days=30,
            _deliverables=json.dumps([
                "Google Business Profile optimization",
                "Key website fixes (CTA, forms, contact)",
                "Conversion tracking setup (GA4)",
                "System for collecting customer reviews",
            ], ensure_ascii=False),
            _expected_results=json.dumps([
                "Better visibility in Google Maps",
                "More calls and inquiries from the business profile",
                "Basic traffic and conversion data",
            ], ensure_ascii=False),
            _payment_variants=json.dumps(["One-time"], ensure_ascii=False),
            is_active=True,
        ),
        Package(
            name="GROWTH",
            description="Extended package - growth in 60 days",
            price=3500,
            duration_days=60,
            _deliverables=json.dumps([
                "Everything in the START package",
                "Local SEO content (5 optimized subpages)",
                "Rebuild of key website sections",
                "Review collection and management system",
                "Basic Google Ads campaign (setup + 2 weeks of management)",
            ], ensure_ascii=False),
            _expected_results=json.dumps([
                "Higher visibility for local keywords",
                "More organic website traffic",
                "First leads from the paid campaign",
                "Steady growth in reviews",
            ], ensure_ascii=False),
            _payment_variants=json.dumps(["One-time", "2 installments"], ensure_ascii=False),
            is_active=True,
        ),
        Package(
            name="PREMIUM",
            description="Full marketing takeover - ongoing partnership",
            price=5000,
            duration_days=90,
            _deliverables=json.dumps([
                "Local marketing strategy",
                "Content plan + execution (blog, social media)",
                "Full local SEO (on-site + off-site)",
                "Google Ads campaign management",
                "Monthly reporting and optimization",
                "Dedicated account manager",
            ], ensure_ascii=False),
            _expected_results=json.dumps([
                "Dominance in local search results",
                "Steady flow of new clients",
                "Measurable ROI from marketing activities",
                "Professional online image",
            ], ensure_ascii=False),
            _payment_variants=json.dumps(["Monthly", "Quarterly"], ensure_ascii=False),
            is_active=True,
        ),
    ]


def _english_email_templates():
    return [
        EmailTemplate(
            key="welcome",
            name="Client welcome",
            subject_template="Welcome to {{ agency.name }} - next steps",
            body_template=(
                "<p>Hello {{ company.contact_person or company.name }},</p>"
                "<p>Thank you for your trust and for choosing our agency. Starting today, we are working on the "
                "Google visibility of <b>{{ company.name }}</b>.</p>"
                "<p><b>Next steps:</b></p>"
                "<ol>"
                "<li>Access to Google Business Profile, Search Console and Analytics.</li>"
                "<li>Initial audit (within 7 days).</li>"
                "<li>Action plan for the first month.</li>"
                "</ol>"
                "<p>If you have any questions, just reply to this e-mail.</p>"
                "<p>Best regards,<br>{{ agency.name }}</p>"
            ),
            placeholders_doc="{{ company.name }}, {{ company.contact_person }}, {{ agency.name }}",
        ),
        EmailTemplate(
            key="payment_reminder",
            name="Payment reminder",
            subject_template="Payment reminder {{ payment.payment_number }} - {{ payment.title }}",
            body_template=(
                "<p>Hello {{ company.contact_person or company.name }},</p>"
                "<p>This is a friendly reminder that the amount of <b>{{ payment.amount_gross }} zł gross</b> "
                "for &ldquo;{{ payment.title }}&rdquo; was due on {{ payment.due_at.strftime('%d.%m.%Y') if payment.due_at else '-' }}.</p>"
                "<p>Please settle it at your earliest convenience.</p>"
                "<p>Best regards,<br>{{ agency.name }}</p>"
            ),
            placeholders_doc="{{ payment.* }}, {{ company.* }}, {{ agency.* }}",
        ),
        EmailTemplate(
            key="follow_up_after_visit",
            name="Follow-up after a visit",
            subject_template="Summary of our meeting - {{ company.name }}",
            body_template=(
                "<p>Hello {{ company.contact_person or company.name }},</p>"
                "<p>Thank you for the meeting. Here is a short summary of what we agreed:</p>"
                "<ul>"
                "<li>Point 1 (fill in before sending)</li>"
                "<li>Point 2</li>"
                "</ul>"
                "<p>Next step on our side: preparing the offer.</p>"
                "<p>Best regards,<br>{{ agency.name }}</p>"
            ),
            placeholders_doc="{{ company.* }}, {{ agency.* }}",
        ),
        EmailTemplate(
            key="audit_delivery",
            name="Audit delivery",
            subject_template="Marketing audit for {{ company.name }} - ready",
            body_template=(
                "<p>Hello {{ company.contact_person or company.name }},</p>"
                "<p>Please find attached the marketing audit of your company. It includes:</p>"
                "<ul>"
                "<li>A score for 5 key areas (1-5)</li>"
                "<li>The main problems and opportunities</li>"
                "<li>A concrete 90-day action plan</li>"
                "</ul>"
                "<p>We will be happy to go through the results with you on a call.</p>"
                "<p>Best regards,<br>{{ agency.name }}</p>"
            ),
            placeholders_doc="{{ company.* }}, {{ agency.* }}, {{ audit.* }}",
        ),
    ]


def _english_contract_templates():
    return [
        ContractTemplate(
            key="seo_retainer",
            name="SEO retainer agreement",
            body_template=(
                "SEO SERVICES AGREEMENT\n\n"
                "Concluded on {{ today }} between:\n\n"
                "{{ agency.legal_name }}, Tax ID: {{ agency.nip }}, address: {{ agency.address }},\n"
                "hereinafter referred to as the Contractor,\n\n"
                "and\n\n"
                "{{ client.legal_name or client.name }}, Tax ID: {{ client.nip }}, address: {{ client.address }},\n"
                "hereinafter referred to as the Client.\n\n"
                "§ 1. SUBJECT OF THE AGREEMENT\n"
                "The Contractor undertakes to provide search engine optimization services for the website "
                "{{ client.website }} in Google, in line with the action plan attached to this agreement.\n\n"
                "§ 2. FEES\n"
                "The Contractor's monthly fee is {{ monthly_fee_net }} zł net "
                "({{ monthly_fee_gross }} zł gross), payable by day {{ billing_day }} of each month "
                "to the bank account: {{ agency.bank_account }}.\n\n"
                "§ 3. TERM\n"
                "This agreement is concluded for an indefinite period with one month's notice.\n\n"
                "§ 4. FINAL PROVISIONS\n"
                "{{ extra_clauses }}\n\n"
                "Signatures:\n\n"
                ".................................\t\t.................................\n"
                "Contractor\t\t\t\t\tClient"
            ),
            placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ monthly_fee_net }}, {{ monthly_fee_gross }}, {{ billing_day }}, {{ extra_clauses }}",
        ),
        ContractTemplate(
            key="website_build",
            name="Website build agreement",
            body_template=(
                "WEBSITE DESIGN AND DEVELOPMENT AGREEMENT\n\n"
                "Concluded on {{ today }} between:\n\n"
                "{{ agency.legal_name }}, Tax ID: {{ agency.nip }}, address: {{ agency.address }},\n"
                "hereinafter referred to as the Contractor,\n\n"
                "and\n\n"
                "{{ client.legal_name or client.name }}, Tax ID: {{ client.nip }}, address: {{ client.address }},\n"
                "hereinafter referred to as the Customer.\n\n"
                "§ 1. SUBJECT OF THE AGREEMENT\n"
                "The Contractor undertakes to design and launch a website "
                "at {{ domain }}, in line with the brief accepted by both parties.\n\n"
                "§ 2. FEES AND PAYMENTS\n"
                "The total fee is {{ total_net }} zł net ({{ total_gross }} zł gross) "
                "and is payable in the following stages:\n"
                "a) {{ payment_stage_1 }} - upon signing the agreement,\n"
                "b) {{ payment_stage_2 }} - upon acceptance of the graphic design,\n"
                "c) {{ payment_stage_3 }} - upon handover of the website.\n\n"
                "§ 3. DEADLINE\n"
                "The website will be launched by {{ deadline }}.\n\n"
                "§ 4. TRANSFER OF RIGHTS\n"
                "Upon payment of the full fee, the Contractor transfers to the Customer "
                "the economic copyrights to the delivered works (graphic design, code, content).\n\n"
                "§ 5. FINAL PROVISIONS\n"
                "{{ extra_clauses }}\n\n"
                "Signatures:\n\n"
                ".................................\t\t.................................\n"
                "Contractor\t\t\t\t\tCustomer"
            ),
            placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ domain }}, {{ total_net }}, {{ total_gross }}, {{ payment_stage_1..3 }}, {{ deadline }}",
        ),
        ContractTemplate(
            key="rodo",
            name="Data processing agreement (GDPR)",
            body_template=(
                "PERSONAL DATA PROCESSING AGREEMENT\n\n"
                "Concluded on {{ today }} between:\n\n"
                "{{ client.legal_name or client.name }}, Tax ID: {{ client.nip }}, address: {{ client.address }},\n"
                "hereinafter referred to as the Controller,\n\n"
                "and\n\n"
                "{{ agency.legal_name }}, Tax ID: {{ agency.nip }}, address: {{ agency.address }},\n"
                "hereinafter referred to as the Processor.\n\n"
                "§ 1. SUBJECT\n"
                "The Controller entrusts the Processor with the processing of personal data "
                "to the extent necessary to perform the main agreement of {{ main_contract_date }}.\n\n"
                "§ 2. CATEGORIES OF DATA\n"
                "Contact details of the Controller's customers: first name, last name, e-mail, phone, address.\n\n"
                "§ 3. OBLIGATIONS OF THE PROCESSOR\n"
                "The Processor undertakes to process the data only on the instructions "
                "of the Controller, to apply appropriate technical and organizational measures and "
                "to report personal data breaches within 24 hours.\n\n"
                "§ 4. TERM\n"
                "This agreement remains in force for the duration of the main agreement. When it ends, "
                "the Processor will return or delete the entrusted data.\n\n"
                "Signatures:\n\n"
                ".................................\t\t.................................\n"
                "Controller\t\t\t\tProcessor"
            ),
            placeholders_doc="{{ today }}, {{ main_contract_date }}, {{ agency.* }}, {{ client.* }}",
        ),
        ContractTemplate(
            key="nda",
            name="Non-disclosure agreement (NDA)",
            body_template=(
                "NON-DISCLOSURE AGREEMENT (NDA)\n\n"
                "Concluded on {{ today }} between:\n\n"
                "{{ agency.legal_name }}, Tax ID: {{ agency.nip }}, address: {{ agency.address }},\n"
                "and\n\n"
                "{{ client.legal_name or client.name }}, Tax ID: {{ client.nip }}, address: {{ client.address }}.\n\n"
                "§ 1. CONFIDENTIAL INFORMATION\n"
                "The parties undertake to keep confidential all business, technical "
                "and commercial information obtained in the course of their cooperation.\n\n"
                "§ 2. TERM\n"
                "The confidentiality obligation remains in force for {{ duration_years }} years from the date of signing.\n\n"
                "§ 3. EXCEPTIONS\n"
                "The obligation does not apply to information that is publicly available or obtained independently.\n\n"
                "§ 4. CONTRACTUAL PENALTY\n"
                "A breach of confidentiality results in a contractual penalty of {{ penalty }} zł.\n\n"
                "Signatures:\n\n"
                ".................................\t\t.................................\n"
                "Party A\t\t\t\t\tParty B"
            ),
            placeholders_doc="{{ today }}, {{ agency.* }}, {{ client.* }}, {{ duration_years }}, {{ penalty }}",
        ),
    ]


def _english_knowledge_articles():
    return [
        KnowledgeArticle(
            title="New client onboarding procedure",
            category="Onboarding",
            body=(
                "# Client onboarding - checklist\n\n"
                "## Day 0 (contract signed)\n"
                "- [ ] Main contract signed and archived in the client's files\n"
                "- [ ] GDPR agreement signed\n"
                "- [ ] Folder created in Dropbox/Drive\n"
                "- [ ] Welcome e-mail sent (template: welcome)\n\n"
                "## Days 1-3 (collecting access)\n"
                "- [ ] Google Business Profile - permissions for the agency\n"
                "- [ ] Google Search Console - user added\n"
                "- [ ] Google Analytics 4 - user added\n"
                "- [ ] WordPress admin - account for the agency\n"
                "- [ ] Hosting / DNS - credentials in Bitwarden\n\n"
                "## Days 4-7 (initial audit)\n"
                "- [ ] SEO audit (built into the app)\n"
                "- [ ] Competitor analysis (3 competitors)\n"
                "- [ ] PageSpeed report\n"
                "- [ ] 90-day plan prepared and sent\n"
            ),
            _tags=json.dumps(["onboarding", "checklist"], ensure_ascii=False),
            pinned=True,
        ),
        KnowledgeArticle(
            title="First sales call script",
            category="Sales",
            body=(
                "# First call with a client\n\n"
                "## Goal of the call\n"
                "Understand the client's situation and decide whether there is a fit (fit check).\n\n"
                "## Questions to ask\n"
                "1. How do you get new clients today?\n"
                "2. How much does it cost you to acquire one client?\n"
                "3. How much is one client worth (LTV)?\n"
                "4. What have you tried in marketing before, and why didn't it work?\n"
                "5. What results do you expect in 3 / 6 / 12 months?\n"
                "6. Who makes the decision? What does the decision process look like?\n\n"
                "## Red flags (weak lead)\n"
                "- Current activities are not measured\n"
                "- Expecting instant results\n"
                "- Budget < 1500 zł/month\n"
                "- No decision-making power\n"
            ),
            _tags=json.dumps(["sales", "call"], ensure_ascii=False),
            pinned=True,
        ),
        KnowledgeArticle(
            title="SEO audit checklist",
            category="Audit procedures",
            body=(
                "# What we check in an SEO audit\n\n"
                "## On-site (website)\n"
                "- Meta title and description on every subpage\n"
                "- H1-H3 heading structure\n"
                "- Internal linking\n"
                "- Schema markup (LocalBusiness / Product / Article)\n"
                "- HTTPS / SSL\n"
                "- Mobile friendly (Google test)\n"
                "- Core Web Vitals (PageSpeed)\n\n"
                "## Google Business Profile\n"
                "- Complete details (NAP)\n"
                "- Primary and additional categories\n"
                "- Photos, posts, reviews\n"
                "- Replies to reviews\n\n"
                "## Off-site\n"
                "- Directory listings (Panorama, PKT, Yelp)\n"
                "- NAP consistency across all sources\n"
                "- Link profile (Ahrefs/manual)\n"
            ),
            _tags=json.dumps(["audit", "checklist"], ensure_ascii=False),
        ),
        KnowledgeArticle(
            title="Monthly client report template",
            category="Reporting",
            body=(
                "# What the monthly report includes\n\n"
                "## Sections\n"
                "1. **Month summary** - what was done (max 5 points)\n"
                "2. **Metrics** - changes in rankings, traffic and conversions\n"
                "3. **Top keywords** - top 10 with the biggest changes\n"
                "4. **Problems and blockers** - what got in the way\n"
                "5. **Plan for next month** - 3-5 priority tasks\n\n"
                "## Rules\n"
                "- Max 2 PDF pages\n"
                "- Concrete numbers, not generalities\n"
                "- One chart per metrics section\n"
                "- Plain language, no industry jargon\n"
            ),
            _tags=json.dumps(["report", "communication"], ensure_ascii=False),
        ),
    ]
