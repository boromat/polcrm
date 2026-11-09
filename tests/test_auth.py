"""Password login, roles, team management, first-run setup and the auth helpers."""

import pytest

import auth
from conftest import DEMO_PASSWORD, login

# ── helpers (no app needed) ─────────────────────────────────────


def test_auth_mode_resolution():
    assert auth.resolve_auth_mode("", False, True) == "password"
    assert auth.resolve_auth_mode("", True, True) == "cloudflare"  # older CF_ACCESS_ENABLED=true
    assert auth.resolve_auth_mode("profile", False, False) == "profile"
    with pytest.raises(RuntimeError):
        auth.resolve_auth_mode("profile", False, True)  # demo picker never in production
    with pytest.raises(RuntimeError):
        auth.resolve_auth_mode("magic", False, False)


def test_password_policy():
    assert auth.password_problem("short")
    assert auth.password_problem("anna@example.com", "anna@example.com")
    assert auth.password_problem("a-long-enough-pass") is None


def test_rate_limiter_window_and_reset():
    now = [0.0]
    lim = auth.LoginRateLimiter(per_account=3, per_ip=10, window_seconds=60, clock=lambda: now[0])
    for _ in range(3):
        lim.failed("1.1.1.1", "a@example.com")
    assert lim.blocked("1.1.1.1", "a@example.com")
    assert not lim.blocked("1.1.1.1", "b@example.com")  # other account from the same IP still fine
    now[0] = 61
    assert not lim.blocked("1.1.1.1", "a@example.com")  # window passed


# ── login ───────────────────────────────────────────────────────


def test_login_success_and_wrong_password(seeded):
    c = seeded.test_client()
    bad = login(c, password="wrong-password-123")
    assert bad.status_code == 401
    assert "Nieprawidłowy e-mail lub hasło" in bad.get_data(as_text=True)
    assert "/login" in c.get("/").headers["Location"]
    ok = login(c)
    assert ok.status_code == 302
    assert c.get("/").status_code == 200


def test_login_is_rate_limited(seeded):
    import core

    core.LOGIN_LIMITER.reset()
    c = seeded.test_client()
    for _ in range(5):
        c.post("/login", data={"email": "anna@example.com", "password": "nope-nope-nope"})
    r = c.post("/login", data={"email": "anna@example.com", "password": DEMO_PASSWORD})
    assert r.status_code == 429  # even the right password waits after 5 failures
    core.LOGIN_LIMITER.reset()


def test_login_next_cannot_redirect_off_site(seeded):
    import core

    core.LOGIN_LIMITER.reset()
    c = seeded.test_client()
    r = c.post("/login", data={"email": "anna@example.com", "password": DEMO_PASSWORD, "next": "//evil.example/x"})
    assert r.headers["Location"].endswith("/")
    c.post("/wyloguj")
    r = c.post("/login", data={"email": "anna@example.com", "password": DEMO_PASSWORD, "next": "/tasks"})
    assert r.headers["Location"].endswith("/tasks")


def test_api_without_session_gets_json_401(seeded):
    r = seeded.test_client().get("/api/assistant/status")
    assert r.status_code == 401 and r.is_json


# ── roles and team ──────────────────────────────────────────────


def test_member_cannot_change_company_settings_or_team(seeded):
    c = seeded.test_client()
    assert login(c, "tomasz@example.com").status_code == 302
    page = c.get("/settings").get_data(as_text=True)
    assert 'id="profile"' in page and 'id="general"' not in page and 'id="team"' not in page
    assert c.post("/settings", data={"section": "general", "agency_name": "X"}).status_code == 403
    assert c.post("/zespol/nowy", data={"name": "X", "email": "x@example.com"}).status_code == 403
    assert c.get("/google-oauth/start").status_code == 403


def test_admin_adds_member_who_can_log_in_then_deactivates(seeded):
    from models import User, db

    admin = seeded.test_client()
    login(admin)
    r = admin.post("/zespol/nowy", data={"name": "Kasia Testowa", "email": "kasia@example.com",
                                         "role": "member", "password": "kasia-start-123"})
    assert r.status_code == 302
    with seeded.app_context():
        kasia = User.query.filter_by(email="kasia@example.com").one()
        kid = kasia.id
        assert kasia.role == "member" and kasia.has_password

    member = seeded.test_client()
    assert login(member, "kasia@example.com", "kasia-start-123").status_code == 302
    assert member.get("/tasks").status_code == 200

    # deactivation ends the existing session at once
    admin.post(f"/zespol/{kid}", data={"name": "Kasia Testowa", "email": "kasia@example.com", "role": "member"})
    assert "/login" in member.get("/tasks").headers["Location"]
    assert login(member, "kasia@example.com", "kasia-start-123").status_code == 401
    with seeded.app_context():
        db.session.delete(db.session.get(User, kid))
        db.session.commit()


def test_last_admin_cannot_be_demoted(seeded):
    from models import User

    c = seeded.test_client()
    login(c)
    with seeded.app_context():
        anna = User.query.filter_by(email="anna@example.com").one()
        others = User.query.filter(User.role == "admin", User.id != anna.id).count()
    assert others == 0
    c.post(f"/zespol/{anna.id}", data={"name": "Anna", "email": "anna@example.com", "role": "member", "is_active": "on"})
    with seeded.app_context():
        assert User.query.filter_by(email="anna@example.com").one().role == "admin"


def test_password_change_logs_out_other_sessions(seeded):
    from models import User, db

    first, second = seeded.test_client(), seeded.test_client()
    login(first, "ola@example.com")
    login(second, "ola@example.com")
    r = first.post("/profil/haslo", data={"current_password": DEMO_PASSWORD,
                                          "new_password": "ola-new-password-1", "new_password2": "ola-new-password-1"})
    assert r.status_code == 302
    assert first.get("/tasks").status_code == 200  # the session that changed it stays in
    assert "/login" in second.get("/tasks").headers["Location"]  # the other one is out
    with seeded.app_context():
        ola = User.query.filter_by(email="ola@example.com").one()
        ola.set_password(DEMO_PASSWORD)
        db.session.commit()


def test_dashboard_and_mentions_list_every_active_person(client, seeded):
    html = client.get("/").get_data(as_text=True)
    for name in ("Anna", "Tomasz", "Ola"):
        assert name in html


# ── first run ───────────────────────────────────────────────────


def test_setup_only_while_there_is_no_admin(seeded):
    from models import User, db

    c = seeded.test_client()
    assert c.get("/setup").status_code == 404  # an admin exists
    with seeded.app_context():
        admins = User.query.filter_by(role="admin").all()
        ids = [u.id for u in admins]
        for u in admins:
            u.role = "member"
        db.session.commit()
    try:
        assert "/setup" in c.get("/").headers["Location"]
        r = c.post("/setup", data={"name": "Nowa Admin", "email": "nowa@example.com",
                                   "password": "nowa-admin-pass", "password2": "nowa-admin-pass"})
        assert r.status_code == 302
        assert c.get("/").status_code == 200  # logged in right away
        assert c.get("/setup").status_code == 404  # closed once an admin exists
    finally:
        with seeded.app_context():
            for uid in ids:
                db.session.get(User, uid).role = "admin"
            nowa = User.query.filter_by(email="nowa@example.com").first()
            if nowa:
                db.session.delete(nowa)
            db.session.commit()
