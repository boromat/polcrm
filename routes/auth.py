"""Login, first-run setup, logout, own profile and password, theme switching, demo profile picker."""

from urllib.parse import urlparse

from flask import (
    abort,
    flash,
    g,
    redirect,
    render_template,
    request,
    session,
    url_for,
)

import auth
import i18n
from core import (
    AUTH_MODE,
    COOKIE_KW,
    LOGIN_LIMITER,
    PROFILE_COOKIE,
    THEME_COOKIE,
    VALID_THEMES,
    _safe_referrer,
    admin_exists,
    app,
    get_current_theme,
    get_current_user,
    login_user,
)
from i18n import _
from models import LANGUAGES, User, db

_AVATAR_COLORS = ("#6c5ce7", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6", "#8b5cf6")


def _safe_next(target):
    """Only same-site relative paths after login (no open redirect)."""
    if not target:
        return url_for("dashboard")
    parsed = urlparse(target)
    if parsed.scheme or parsed.netloc or not target.startswith("/") or target.startswith("//"):
        return url_for("dashboard")
    return target


def _initials(name):
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


# ── Logowanie hasłem ───────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if AUTH_MODE != "password":
        return redirect(url_for("choose_profile" if AUTH_MODE == "profile" else "dashboard"))
    if not admin_exists():
        return redirect(url_for("setup"))
    if get_current_user():
        return redirect(_safe_next(request.args.get("next")))

    error = None
    email = ""
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        ip = request.remote_addr or "?"
        if LOGIN_LIMITER.blocked(ip, email):
            error = _("Za dużo nieudanych prób. Spróbuj ponownie za kilkanaście minut.")
            return render_template("login.html", error=error, email=email), 429
        user = User.query.filter(db.func.lower(User.email) == email).first() if email else None
        if user and user.is_active and user.check_password(password):
            LOGIN_LIMITER.succeeded(ip, email)
            login_user(user)
            return redirect(_safe_next(request.form.get("next")))
        LOGIN_LIMITER.failed(ip, email)
        error = _("Nieprawidłowy e-mail lub hasło.")  # bez zdradzania, czy konto istnieje
    return render_template("login.html", error=error, email=email,
                           next=request.args.get("next", "")), (401 if error else 200)


@app.route("/setup", methods=["GET", "POST"])
def setup():
    """Pierwsze uruchomienie: zakłada konto admina. Działa tylko, gdy żadnego admina jeszcze nie ma."""
    if AUTH_MODE == "cloudflare" or admin_exists():
        abort(404)
    error = None
    form = {"name": "", "email": ""}
    if request.method == "POST":
        form = {"name": request.form.get("name", "").strip(), "email": request.form.get("email", "").strip().lower()}
        password = request.form.get("password", "")
        if not form["name"] or "@" not in form["email"]:
            error = _("Podaj imię i poprawny e-mail.")
        elif password != request.form.get("password2", ""):
            error = _("Hasła nie są takie same.")
        else:
            error = auth.password_problem(password, form["email"])
        if not error:
            user = User.query.filter(db.func.lower(User.email) == form["email"]).first() or User(email=form["email"])
            user.name = form["name"]
            user.initials = _initials(form["name"])
            user.role = "admin"
            user.is_active = True
            user.set_password(password)
            user.language = i18n.current_language()  # the language the setup page was shown in
            db.session.add(user)
            db.session.commit()
            if AUTH_MODE == "password":
                login_user(user)
            flash(_("Konto administratora utworzone. Dodaj resztę zespołu w Ustawienia → Zespół."), "success")
            return redirect(url_for("dashboard"))
    return render_template("setup.html", error=error, form=form, min_len=auth.MIN_PASSWORD_LENGTH)


@app.route("/wyloguj", methods=["POST"])  # tylko POST: link GET dawał się wywołać z obcej strony
def logout_profile():
    session.clear()
    resp = redirect(url_for("choose_profile" if AUTH_MODE == "profile" else "login"))
    resp.set_cookie(PROFILE_COOKIE, "", expires=0, **COOKIE_KW)
    resp.set_cookie(THEME_COOKIE, "", expires=0, **COOKIE_KW)
    return resp


# ── Własny profil i hasło ──────────────────────────────────────

@app.route("/profil", methods=["POST"])
def profile_update():
    user = get_current_user()
    name = request.form.get("name", "").strip()
    if name:
        user.name = name[:64]
        user.initials = (request.form.get("initials", "").strip() or _initials(name))[:4].upper()
    color = request.form.get("avatar_color", "")
    if color in _AVATAR_COLORS:
        user.avatar_color = color
    language = request.form.get("language", "")
    if language in LANGUAGES:
        user.language = language
        g.lang = language  # the confirmation below already in the new language
    db.session.commit()
    flash(_("Profil zapisany."), "success")
    return redirect(url_for("settings") + "#profile")


@app.route("/profil/haslo", methods=["POST"])
def profile_password():
    user = get_current_user()
    if user.has_password and not user.check_password(request.form.get("current_password", "")):
        flash(_("Obecne hasło jest nieprawidłowe."), "danger")
        return redirect(url_for("settings") + "#profile")
    new = request.form.get("new_password", "")
    if new != request.form.get("new_password2", ""):
        flash(_("Nowe hasła nie są takie same."), "danger")
        return redirect(url_for("settings") + "#profile")
    problem = auth.password_problem(new, user.email)
    if problem:
        flash(problem, "danger")
        return redirect(url_for("settings") + "#profile")
    user.set_password(new)
    db.session.commit()
    if AUTH_MODE == "password":
        login_user(user)  # nowy odcisk hasła w tej sesji, inne sesje wygasają
    flash(_("Hasło zmienione. Inne zalogowane sesje zostały wylogowane."), "success")
    return redirect(url_for("settings") + "#profile")


# ── Wybór profilu (tylko tryb demo AUTH_MODE=profile) ──────────

@app.route("/kim-jestes")
def choose_profile():
    if AUTH_MODE != "profile":
        abort(404)
    if not admin_exists():
        return redirect(url_for("setup"))
    users = User.query.filter_by(is_active=True).order_by(User.id).all()
    return render_template("choose_profile.html", users=users)


@app.route("/choose-profile/<int:user_id>", methods=["POST"])
def set_profile(user_id):
    if AUTH_MODE != "profile":
        abort(404)
    user = db.get_or_404(User, user_id)
    if not user.is_active:
        abort(404)
    resp = redirect(url_for("dashboard"))
    resp.set_cookie(PROFILE_COOKIE, str(user.id), max_age=60 * 60 * 24 * 90, **COOKIE_KW)
    resp.set_cookie(THEME_COOKIE, "", expires=0, **COOKIE_KW)
    flash(_("Witaj %(name)s!", name=user.name), "success")
    return resp


# ── Motyw ──────────────────────────────────────────────────────

@app.route("/toggle-theme", methods=["POST"])
def toggle_theme():
    """Przełącza motyw i zapisuje go od razu jako preferencję zalogowanej osoby."""
    user = get_current_user()
    current = get_current_theme(user)
    new_theme = "minimal" if current == "colorful" else "colorful"
    resp = redirect(_safe_referrer(url_for("dashboard")))
    if user:
        user.default_theme = new_theme
        db.session.commit()
        resp.set_cookie(THEME_COOKIE, "", expires=0, **COOKIE_KW)
    else:
        resp.set_cookie(THEME_COOKIE, new_theme, max_age=60 * 60 * 24 * 365, **COOKIE_KW)
    return resp


@app.route("/set-default-theme", methods=["POST"])
def set_default_theme():
    """Zachowane dla wstecznej zgodności. Przełącznik zapisuje motyw od razu."""
    user = get_current_user()
    theme = request.form.get("theme", "colorful")
    if theme in VALID_THEMES:
        user.default_theme = theme
        db.session.commit()
        flash(_("Motyw zapisany jako Twój domyślny: %(theme)s", theme=theme), "success")
    return redirect(_safe_referrer(url_for("settings")))


# ── Język interfejsu ───────────────────────────────────────────

@app.route("/jezyk/<lang>", methods=["POST"])
def set_ui_language(lang):
    """PL/EN: zalogowanej osobie zapisuje język w profilu, gościowi (logowanie) w ciasteczku."""
    if lang not in LANGUAGES:
        abort(404)
    user = get_current_user()
    if user is not None:
        user.language = lang
        db.session.commit()
    resp = redirect(_safe_referrer(url_for("dashboard")))
    resp.set_cookie(i18n.LANG_COOKIE, lang, max_age=60 * 60 * 24 * 365, **COOKIE_KW)
    return resp
