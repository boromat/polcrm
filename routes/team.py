"""Team management (admin only): add people, change roles, deactivate, reset passwords."""

from flask import flash, redirect, request, url_for

import auth
from core import AUTH_MODE, admin_required, app, get_current_user, login_user
from i18n import _
from models import ROLES, User, db

_COLORS = ("#6c5ce7", "#10b981", "#f59e0b", "#ef4444", "#3b82f6", "#ec4899", "#14b8a6", "#8b5cf6")


def _back():
    return redirect(url_for("settings") + "#team")


def _initials(name):
    parts = [p for p in name.split() if p]
    return "".join(p[0] for p in parts[:2]).upper() or "?"


def _active_admins_other_than(user_id):
    return User.query.filter(User.role == "admin", User.is_active.is_(True), User.id != user_id).count()


@app.route("/zespol/nowy", methods=["POST"])
@admin_required
def team_add():
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "member")
    password = request.form.get("password", "")
    if not name or "@" not in email:
        flash(_("Podaj imię i poprawny e-mail."), "danger")
        return _back()
    if role not in ROLES:
        role = "member"
    if User.query.filter(db.func.lower(User.email) == email).first():
        flash(_("Osoba z tym e-mailem już jest w zespole."), "danger")
        return _back()
    user = User(name=name[:64], email=email, role=role, initials=_initials(name),
                avatar_color=_COLORS[User.query.count() % len(_COLORS)])
    if AUTH_MODE == "password":
        problem = auth.password_problem(password, email)
        if problem:
            flash(problem, "danger")
            return _back()
        user.set_password(password)
    db.session.add(user)
    db.session.commit()
    flash(_("Dodano: %(name)s. Przekaż tej osobie hasło startowe - może je zmienić w swoim profilu.", name=user.name), "success")
    return _back()


@app.route("/zespol/<int:user_id>", methods=["POST"])
@admin_required
def team_update(user_id):
    user = db.get_or_404(User, user_id)
    role = request.form.get("role", user.role)
    active = request.form.get("is_active") == "on"
    losing_admin = user.role == "admin" and user.is_active and (role != "admin" or not active)
    if losing_admin and not _active_admins_other_than(user.id):
        flash(_("To ostatni aktywny administrator - najpierw nadaj tę rolę komuś innemu."), "danger")
        return _back()
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip().lower()
    if name:
        user.name = name[:64]
    if email and "@" in email and email != (user.email or "").lower():
        if User.query.filter(db.func.lower(User.email) == email, User.id != user.id).first():
            flash(_("Ten e-mail ma już inna osoba w zespole."), "danger")
            return _back()
        user.email = email
    if role in ROLES:
        user.role = role
    user.is_active = active
    db.session.commit()
    flash(_("Zapisano: %(name)s.", name=user.name), "success")
    return _back()


@app.route("/zespol/<int:user_id>/haslo", methods=["POST"])
@admin_required
def team_password(user_id):
    user = db.get_or_404(User, user_id)
    password = request.form.get("password", "")
    problem = auth.password_problem(password, user.email)
    if problem:
        flash(problem, "danger")
        return _back()
    user.set_password(password)  # unieważnia sesje tej osoby (odcisk hasła w sesji)
    db.session.commit()
    if user.id == get_current_user().id and AUTH_MODE == "password":
        login_user(user)
    flash(_("Nowe hasło dla: %(name)s. Pozostałe sesje tej osoby zostały wylogowane.", name=user.name), "success")
    return _back()
