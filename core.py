"""
PolCRM - Hub Agencyjny (rozszerzony do pełnego zarządzania firmą SEO/WWW).

Marketing agency hub: company management, audits with auto-scoring,
PDF/HTML reports, service packages, CRM pipeline, visit calendar,
finances (payments, expenses, subscriptions), tasks, projects,
content calendar, client credentials links, email templates + SMTP sending,
contract templates + PDF + file uploads, knowledge base, GSC/GA integrations.
"""

import os
import shutil
from datetime import date, datetime, timedelta
from functools import wraps
from pathlib import Path
from urllib.parse import urlparse

# Wczytaj .env jesli istnieje - musi byc PRZED uzyciem os.environ
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

import googlemaps
from flask import (
    Flask,
    abort,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from flask_wtf.csrf import CSRFError, CSRFProtect

import auth
import finance_helpers
import i18n
from i18n import _
from models import (
    AuditLog,
    Mention,
    Settings,
    Task,
    User,
    db,
    ensure_schema,
    seed_defaults,
)

# ── Konfiguracja z ENV ─────────────────────────────────────────

def _env_bool(key, default=False):
    return os.environ.get(key, str(default)).strip().lower() in ("1", "true", "yes", "on")


IS_PRODUCTION = os.environ.get("FLASK_ENV", "development").lower() == "production"
# AUTH_MODE: password (domyślnie) | cloudflare | profile (demo). Stare CF_ACCESS_ENABLED=true = cloudflare.
AUTH_MODE = auth.resolve_auth_mode(
    os.environ.get("AUTH_MODE", ""), _env_bool("CF_ACCESS_ENABLED", False), IS_PRODUCTION)
CF_ACCESS_ENABLED = AUTH_MODE == "cloudflare"
LOGIN_LIMITER = auth.LoginRateLimiter()
ALLOWED_EMAILS = {
    e.strip().lower()
    for e in os.environ.get("ALLOWED_EMAILS", "").split(",")
    if e.strip()
}
if AUTH_MODE == "cloudflare" and not ALLOWED_EMAILS:
    # Druga warstwa kontroli jest wtedy pusta: wejdzie każdy, kogo przepuści polityka Access.
    print("[UWAGA] AUTH_MODE=cloudflare bez ALLOWED_EMAILS - aplikacja polega tylko na polityce Cloudflare Access.")
SESSION_COOKIE_SECURE = _env_bool("SESSION_COOKIE_SECURE", IS_PRODUCTION)


app = Flask(__name__)
# Język interfejsu (pl/en): {{ _('...') }} w szablonach, i18n._ w Pythonie - zob. i18n.py
app.jinja_env.add_extension("jinja2.ext.i18n")
app.jinja_env.install_gettext_callables(gettext=i18n.gettext, ngettext=i18n.ngettext, newstyle=True)

# SECRET_KEY - w prod MUSI byc z env; w dev fallback pozwala developowac bez .env
_secret = os.environ.get("FLASK_SECRET_KEY", "").strip()
if not _secret:
    if IS_PRODUCTION:
        raise RuntimeError(
            "FLASK_SECRET_KEY musi byc ustawiony w produkcji. "
            "Uruchom: python scripts/generate_keys.py i wklej do .env"
        )
    _secret = "dev-only-insecure-key-do-not-use-in-prod"
app.secret_key = _secret

# Domyślnie instance/hub.db; DATABASE_URL pozwala wskazać inną bazę (np. w testach).
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL", "sqlite:///hub.db")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 MB uploads

# Bezpieczne cookie sesji Flaska i CSRF
app.config["SESSION_COOKIE_HTTPONLY"] = True
app.config["SESSION_COOKIE_SECURE"] = SESSION_COOKIE_SECURE
app.config["SESSION_COOKIE_SAMESITE"] = "Lax"
app.config["PERMANENT_SESSION_LIFETIME"] = 60 * 60 * 24 * 30  # 30 dni

# CSRF
app.config["WTF_CSRF_TIME_LIMIT"] = None  # token wazny przez cala sesje
csrf = CSRFProtect(app)

db.init_app(app)

BASE_DIR = Path(__file__).parent
CSV_DIR = BASE_DIR / "output"
CSV_DIR.mkdir(exist_ok=True)
UPLOADS_DIR = BASE_DIR / "output" / "uploads"
UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
CONTRACTS_DIR = BASE_DIR / "output" / "contracts"
CONTRACTS_DIR.mkdir(parents=True, exist_ok=True)
WHITEBOARD_IMG_DIR = BASE_DIR / "output" / "whiteboard_images"
WHITEBOARD_IMG_DIR.mkdir(parents=True, exist_ok=True)

DETAIL_FIELDS = [
    "name", "formatted_address", "formatted_phone_number",
    "international_phone_number", "website", "geometry/location",
    "rating", "user_ratings_total", "business_status", "type",
    "url", "opening_hours",
]


# ── Init DB + backup + schema migration ───────────────────────

BACKUP_KEEP_COUNT = 10


def _backup_hub_db():
    """Copy instance/hub.db do instance/backup_YYYYMMDD_HHMMSS.db - raz na start.

    Rotuje: trzymamy ostatnie BACKUP_KEEP_COUNT backupow, starsze kasujemy.
    """
    db_path = BASE_DIR / "instance" / "hub.db"
    if not db_path.is_file():
        return
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup = BASE_DIR / "instance" / f"backup_{stamp}.db"
    if not backup.exists():
        try:
            shutil.copy2(db_path, backup)
        except Exception:
            pass

    # Rotacja - usun wszystkie backup_*.db oprocz N najnowszych
    try:
        backups = sorted(
            (BASE_DIR / "instance").glob("backup_*.db"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        )
        for old in backups[BACKUP_KEEP_COUNT:]:
            try:
                old.unlink()
            except OSError:
                pass
    except Exception:
        pass


with app.app_context():
    _backup_hub_db()
    db.create_all()
    ensure_schema()
    seed_defaults()
    # Auto-flip overdue flag on startup
    finance_helpers.mark_overdue_payments()


# ── Uwierzytelnianie (hasło / Cloudflare Access / profil demo) ─────

PROFILE_COOKIE = "polcrm_profile"
THEME_COOKIE = "polcrm_theme"
VALID_THEMES = ("colorful", "minimal")
COOKIE_KW = {
    "httponly": True,
    "secure": SESSION_COOKIE_SECURE,
    "samesite": "Lax",
}


def _cf_access_email():
    """Zwroc email z naglowka Cloudflare Access (jesli wlaczony i obecny).

    UWAGA: ufamy temu naglowkowi TYLKO gdy CF_ACCESS_ENABLED=true.
    W produkcji aplikacja musi byc wystawiona WYLACZNIE przez cloudflared tunnel
    (nasluch na 127.0.0.1), inaczej atakujacy moze sam ustawic ten naglowek.
    """
    if AUTH_MODE != "cloudflare":
        return None
    email = (request.headers.get("Cf-Access-Authenticated-User-Email") or "").strip().lower()
    if not email:
        return None
    if ALLOWED_EMAILS and email not in ALLOWED_EMAILS:
        return None
    return email


def get_current_user():
    """Zalogowana osoba albo None. Wynik jest zapamiętany na czas jednego żądania (flask.g),
    bo pytają o niego szablony, hooki i zdarzenie SQLAlchemy - wcześniej kilka zapytań na stronę.

    * cloudflare - e-mail z nagłówka Access; nieznany e-mail z listy dostaje konto członka
      (pierwsze konto w pustej bazie zostaje adminem),
    * password - identyfikator w podpisanej sesji Flaska + odcisk hasła (zmiana hasła wylogowuje),
    * profile - ciastko wyboru profilu (tylko demo).
    """
    if "_current_user" in g:
        return g._current_user
    g._current_user = user = _resolve_current_user()
    return user


def _resolve_current_user():
    if AUTH_MODE == "cloudflare":
        email = _cf_access_email()
        if not email:
            return None  # tożsamość wyłącznie z nagłówka - ciastka nie omijają ALLOWED_EMAILS
        user = User.query.filter(db.func.lower(User.email) == email).first()
        if not user:
            first = User.query.count() == 0
            user = User(name=email.split("@")[0].title(), email=email, initials=email[0].upper(),
                        role="admin" if first else "member")
            db.session.add(user)
            db.session.commit()
        return user if user.is_active else None

    if AUTH_MODE == "password":
        uid = session.get("uid")
        if not uid:
            return None
        user = db.session.get(User, uid)
        if not user or not user.is_active or session.get("pwf") != auth.session_fingerprint(user.password_hash):
            session.clear()
            return None
        return user

    uid = request.cookies.get(PROFILE_COOKIE)  # profile (demo)
    if not uid:
        return None
    try:
        user = db.session.get(User, int(uid))
    except (ValueError, TypeError):
        return None
    return user if user and user.is_active else None


def login_user(user):
    """Nowa sesja dla zalogowanej osoby (stara jest czyszczona - ochrona przed session fixation)."""
    session.clear()
    session.permanent = True
    session["uid"] = user.id
    session["pwf"] = auth.session_fingerprint(user.password_hash)
    user.last_login_at = datetime.now().replace(microsecond=0)
    db.session.commit()
    g._current_user = user


def admin_exists():
    return User.query.filter_by(role="admin", is_active=True).count() > 0


def admin_required(view):
    """Tylko admin: zespół, klucze API, SMTP, integracje, asystent AI."""
    @wraps(view)
    def wrapper(*args, **kwargs):
        user = get_current_user()
        if not user or not user.is_admin:
            if request.path.startswith("/api/"):
                return jsonify({"error": _("Tylko administrator może to zrobić.")}), 403
            abort(403, _("Tylko administrator może to zrobić."))
        return view(*args, **kwargs)
    return wrapper


def get_current_theme(user=None):
    """Theme jest zapisany per-uzytkownik w User.default_theme.
    Fallback: cookie (dla niezalogowanych) -> 'colorful'."""
    if user and user.default_theme in VALID_THEMES:
        return user.default_theme
    override = request.cookies.get(THEME_COOKIE)
    if override in VALID_THEMES:
        return override
    return "colorful"


def _safe_referrer(default_url):
    """Zwroc request.referrer tylko jesli wskazuje na ten sam host. Inaczej default."""
    ref = request.referrer
    if not ref:
        return default_url
    try:
        ref_host = urlparse(ref).netloc
        own_host = urlparse(request.host_url).netloc
        if ref_host and ref_host == own_host:
            return ref
    except Exception:
        pass
    return default_url


_PUBLIC_ENDPOINTS = ("static", "login", "setup", "choose_profile", "set_profile", "toggle_theme",
                     "oauth2callback", "set_ui_language", "web_manifest")


@app.before_request
def set_language():
    """Język tego żądania: profil zalogowanej osoby, potem ciastko, przeglądarka, DEFAULT_LANGUAGE."""
    lang = None
    if request.endpoint != "static":
        user = get_current_user()
        if user is not None and user.language in i18n.LANGUAGES:
            lang = user.language
    if lang is None:
        lang = request.cookies.get(i18n.LANG_COOKIE)
    if lang not in i18n.LANGUAGES:
        lang = request.accept_languages.best_match(i18n.LANGUAGES) or i18n.DEFAULT_LANGUAGE
    g.lang = lang


@app.before_request
def require_login():
    """Każda strona wymaga zalogowania. Pusta baza (brak admina) prowadzi do /setup."""
    if not request.endpoint or request.endpoint in _PUBLIC_ENDPOINTS:
        return None
    if get_current_user():
        return None
    if request.path.startswith("/api/"):
        return jsonify({"error": _("Sesja wygasła - zaloguj się ponownie.")}), 401
    if AUTH_MODE == "cloudflare":
        abort(403, _("Brak autoryzacji Cloudflare Access lub email spoza listy."))
    if not admin_exists():
        return redirect(url_for("setup"))
    if AUTH_MODE == "profile":
        return redirect(url_for("choose_profile"))
    return redirect(url_for("login", next=request.full_path.rstrip("?") if request.method == "GET" else None))


@app.errorhandler(CSRFError)
def _handle_csrf_error(e):
    if "lang" not in g:  # CSRFProtect odrzuca żądanie przed set_language - strona błędu w języku osoby
        set_language()
    return render_template("error.html", code=400, message=_("Blad CSRF: %(error)s", error=e.description)), 400


@app.before_request
def check_settings():
    """Wymagaj klucza Google API tylko dla rout ktore go faktycznie uzywaja
    (audyty, geocoding, GSC/GA). Reszta apki dziala bez API."""
    if not request.endpoint:
        return None
    # Routy ktore *wymagaja* Google Maps / GSC API
    needs_google_api = (
        "audit_",          # audit_new, audit_edit, audit_report, audit_pdf, audit_pagespeed, ...
        "audits_",         # audits_list, audits_new
        "company_geocode", # geocoding adresow firm
        "search",          # wyszukiwanie firm w Google Places (search, search_run, search_competitor)
    )
    if any(request.endpoint.startswith(r) for r in needs_google_api):
        s = Settings.get()
        if not s.google_api_key:
            flash(_("Ta sekcja wymaga klucza Google Maps API. Wklej go w Ustawieniach → Ogólne."), "warning")
            return redirect(url_for("settings"))


# ── Template globals ──────────────────────────────────────────

@app.context_processor
def inject_globals():
    today_d = date.today()
    overdue_tasks_count = Task.query.filter(
        Task.status != "done",
        Task.deadline != None,
        Task.deadline < today_d,
    ).count()
    tasks_today_count = Task.query.filter(
        Task.status != "done",
        db.or_(
            Task.deadline == today_d,
            db.and_(Task.deadline == None, Task.priority == "urgent"),
        ),
    ).count()
    tasks_week_count = Task.query.filter(
        Task.status != "done",
        Task.deadline != None,
        Task.deadline > today_d,
        Task.deadline <= today_d + timedelta(days=7),
    ).count()
    user = get_current_user()
    unread_mentions = 0
    if user:
        unread_mentions = Mention.query.filter(
            Mention.mentioned_user_id == user.id,
            Mention.read_at == None,
        ).count()
    # aktywni członkowie zespołu (wzmianki @Imię, awatary) - dowolna liczba osób
    all_users = User.query.filter_by(is_active=True).order_by(User.id).all() if user else []
    # Cache-busting wersja static assetow (mtime style.css)
    try:
        _css_mtime = int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "static", "css", "style.css")))
    except OSError:
        _css_mtime = 0
    try:
        _js_mtime = int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "static", "js", "app.js")))
    except OSError:
        _js_mtime = 0
    try:  # zbudowany Tailwind też musi unieważniać cache przeglądarki i service workera
        _tw_mtime = int(os.path.getmtime(os.path.join(os.path.dirname(__file__), "static", "css", "tailwind.css")))
    except OSError:
        _tw_mtime = 0
    static_version = max(_css_mtime, _js_mtime, _tw_mtime)

    return {
        "overdue_tasks_count": overdue_tasks_count,
        "tasks_today_count": tasks_today_count,
        "tasks_week_count": tasks_week_count,
        "today_date": today_d,
        "today": today_d,
        "current_user": user,
        "current_theme": get_current_theme(user),
        "unread_mentions_count": unread_mentions,
        "all_users": all_users,
        "static_version": static_version,
        "auth_mode": AUTH_MODE,
        "lang": i18n.current_language(),
        "js_i18n": i18n.js_catalog(i18n.current_language()),
    }


# ── Helpers ────────────────────────────────────────────────────

def get_gmaps():
    s = Settings.get()
    if not s.google_api_key:
        return None
    return googlemaps.Client(key=s.google_api_key)


def get_api_key():
    return Settings.get().google_api_key


def _parse_date(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return date.fromisoformat(s)
    except ValueError:
        return None


def _parse_float(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return float(s.replace(",", "."))
    except ValueError:
        return None


def _vat_rate(raw, default=23.0):
    """Stawka VAT z formularza. Puste pole -> domyślne 23%, ale 0 (zw.) zostaje zerem."""
    value = _parse_float(raw)
    return default if value is None else value


def _parse_int(s):
    s = (s or "").strip()
    if not s:
        return None
    try:
        return int(s)
    except ValueError:
        return None


# ── Attribution + audit helpers ────────────────────────────────

def _set_audit_user(obj, is_new=False):
    """Set created_by_user_id on create, updated_by_user_id on update."""
    user = get_current_user()
    if not user:
        return
    if is_new and hasattr(obj, "created_by_user_id") and not getattr(obj, "created_by_user_id", None):
        obj.created_by_user_id = user.id
    if hasattr(obj, "updated_by_user_id"):
        obj.updated_by_user_id = user.id


def _log_audit(table_name, record_id, action="update", field="", old=None, new=None, note=""):
    """Append an AuditLog row tied to current user."""
    user = get_current_user()
    entry = AuditLog(
        table_name=table_name,
        record_id=record_id,
        user_id=user.id if user else None,
        action=action,
        field=field or "",
        old_value="" if old is None else str(old)[:500],
        new_value="" if new is None else str(new)[:500],
        note=note or "",
    )
    db.session.add(entry)


def _find_mentions(text, source_type, source_id, task_id=None, snippet=""):
    """Parse @Imię style mentions in text (any team member), create Mention rows (skip self)."""
    if not text:
        return []
    import re as _re
    current = get_current_user()
    users = {u.name.lower(): u for u in User.query.all()}
    found_ids = set()
    for m in _re.finditer(r"@([A-Za-zĄĆĘŁŃÓŚŹŻąćęłńóśźż]+)", text):
        name = m.group(1).lower()
        if name in users:
            u = users[name]
            if current and u.id == current.id:
                continue
            found_ids.add(u.id)
    created = []
    for uid in found_ids:
        row = Mention(
            mentioned_user_id=uid,
            author_user_id=current.id if current else None,
            source_type=source_type,
            source_id=source_id,
            task_id=task_id,
            snippet=(snippet or text)[:500],
        )
        db.session.add(row)
        created.append(row)
    return created


_BLEACH_TAGS = [
    "p", "br", "strong", "em", "b", "i", "u", "code", "pre", "blockquote",
    "ul", "ol", "li", "a", "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tr", "th", "td", "hr", "span",
]
_BLEACH_ATTRS = {
    "a": ["href", "title", "rel", "target"],
    "span": ["class"],
    "code": ["class"],
    "pre": ["class"],
    "th": ["align"],
    "td": ["align"],
}
_BLEACH_PROTOCOLS = ["http", "https", "mailto"]


def _render_markdown(text, mentions=True):
    """Server-side markdown -> HTML + sanityzacja bleach (obrona przed XSS).

    mentions=True zamienia @Imie na wyróżnione wzmianki (notatki, zadania, komentarze).
    """
    if not text:
        return ""
    import bleach as _bleach
    import markdown as _md
    raw_html = _md.markdown(text, extensions=["fenced_code", "tables", "nl2br"])
    if not mentions:
        return _bleach.clean(raw_html, tags=_BLEACH_TAGS, attributes=_BLEACH_ATTRS,
                             protocols=_BLEACH_PROTOCOLS, strip=True)
    import re as _re
    raw_html = _re.sub(
        r"@([A-Za-z\u0105\u0107\u0119\u0142\u0144\u00F3\u015B\u017A\u017C\u0104\u0106\u0118\u0141\u0143\u00D3\u015A\u0179\u017B]+)",
        r'<span class="mention">@\1</span>',
        raw_html,
    )
    clean = _bleach.clean(raw_html, tags=_BLEACH_TAGS, attributes=_BLEACH_ATTRS,
                          protocols=_BLEACH_PROTOCOLS, strip=True)
    return clean


# Jinja filter - markdown + @mention styling
@app.template_filter("markdown_mention")
def _jinja_markdown_mention(text):
    return _render_markdown(text or "")


@app.template_filter("pl_date")
def _jinja_pl_date(d):
    """Długa data w języku interfejsu: 'Piątek, 17 kwietnia 2026' / 'Friday, April 17, 2026'."""
    return i18n.format_long_date(d) if d else ""


@app.template_filter("pl_weekday")
def _jinja_pl_weekday(d):
    """Sama nazwa dnia tygodnia w języku interfejsu."""
    return i18n.weekday_name(d) if d else ""


# Auto-attribution via SQLAlchemy session events - no per-route wiring needed
from sqlalchemy import event as _sa_event


@_sa_event.listens_for(db.session, "before_flush")
def _auto_apply_attribution(sa_session, flush_context, instances):
    try:
        user = get_current_user()
    except Exception:
        user = None
    if not user:
        return
    for obj in sa_session.new:
        # Set created_by if field exists and unset
        if hasattr(obj, "created_by_user_id") and getattr(obj, "created_by_user_id", None) in (None, 0):
            try:
                obj.created_by_user_id = user.id
            except Exception:
                pass
        if hasattr(obj, "updated_by_user_id"):
            try:
                obj.updated_by_user_id = user.id
            except Exception:
                pass
    for obj in sa_session.dirty:
        if hasattr(obj, "updated_by_user_id"):
            try:
                obj.updated_by_user_id = user.id
            except Exception:
                pass
