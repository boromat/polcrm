"""Dashboard (Command Center)."""

from datetime import date, datetime, timedelta

from flask import jsonify, render_template

import finance_helpers
import i18n
from core import (
    app,
    get_current_user,
)
from i18n import _
from models import (
    PIPELINE_STAGES,
    Audit,
    AuditLog,
    Company,
    ContentPost,
    Note,
    Project,
    Task,
    User,
    Visit,
    db,
    utcnow,
)

# ═══════════════════════════════════════════════════════════════
#  ROUTES
# ═══════════════════════════════════════════════════════════════


@app.route("/manifest.webmanifest")
def web_manifest():
    """PWA manifest in the visitor's language. Public: browsers fetch it without cookies."""
    icon = {"src": "/static/icons/icon.svg", "sizes": "any"}
    shortcuts = [
        (_("Nowe zadanie"), _("Zadanie"), "/tasks/new"),
        (_("Nowa płatność"), _("Płatność"), "/finances/payments/new"),
        ("Pipeline", "Pipeline", "/pipeline"),
        (_("Finanse"), _("Finanse"), "/finances"),
    ]
    resp = jsonify({
        "name": "PolCRM",
        "short_name": "PolCRM",
        "description": _("CRM, finanse i content dla agencji marketingowej."),
        "start_url": "/",
        "scope": "/",
        "display": "standalone",
        "orientation": "any",
        "background_color": "#0a0a14",
        "theme_color": "#6c5ce7",
        "lang": i18n.current_language(),
        "dir": "ltr",
        "categories": ["business", "productivity"],
        "icons": [{**icon, "type": "image/svg+xml", "purpose": "any"}],
        "shortcuts": [{"name": n, "short_name": s, "url": u, "icons": [icon]} for n, s, u in shortcuts],
    })
    resp.mimetype = "application/manifest+json"
    return resp


# ── Dashboard ─────────────────────────────────────────────────

@app.route("/")
def dashboard():
    today = date.today()
    week_end = today + timedelta(days=7)
    now_dt = utcnow()

    # Tasks - grouped for kanban
    tasks_today = Task.query.filter(
        Task.status != "done",
        db.or_(
            Task.deadline == today,
            db.and_(Task.deadline == None, Task.priority == "urgent"),
        ),
    ).order_by(Task.priority.desc()).limit(10).all()

    tasks_overdue = Task.query.filter(
        Task.status != "done",
        Task.deadline != None,
        Task.deadline < today,
    ).order_by(Task.deadline).limit(10).all()

    tasks_week = Task.query.filter(
        Task.status != "done",
        Task.deadline != None,
        Task.deadline > today,
        Task.deadline <= week_end,
    ).order_by(Task.deadline).limit(10).all()

    # Core stats
    total_companies = Company.query.count()
    total_audits = Audit.query.count()

    # Finance
    balance = finance_helpers.monthly_balance(today.year, today.month, allocate_overhead=False)
    overdue = finance_helpers.overdue_payments_summary()

    # Upcoming visits + content (for kanban upcoming column + bottom bento)
    upcoming_visits = (
        Visit.query
        .filter(Visit.scheduled_at >= utcnow(), Visit.status == "planned")
        .order_by(Visit.scheduled_at)
        .limit(5)
        .all()
    )
    upcoming_content = ContentPost.query.filter(
        ContentPost.status != "published",
        ContentPost.deadline != None,
        ContentPost.deadline <= week_end,
    ).order_by(ContentPost.deadline).limit(6).all()

    # Attention
    attention = (
        Company.query
        .filter(
            Company.next_action_date != None,
            Company.next_action_date <= today,
            Company.next_action != "",
        )
        .order_by(Company.next_action_date)
        .limit(5)
        .all()
    )

    # Recent personal notes
    recent_personal_notes = (
        Note.query.filter_by(scope="personal")
        .order_by(Note.created_at.desc())
        .limit(5)
        .all()
    )

    # Pipeline counts
    stage_totals = dict(db.session.query(Company.pipeline_stage, db.func.count(Company.id))
                        .group_by(Company.pipeline_stage).all())
    pipeline_counts = {stage: stage_totals.get(stage, 0) for stage in PIPELINE_STAGES}

    # Extended metrics (MRR / projects / content pipeline)
    mrr_total = float(
        db.session.query(db.func.coalesce(db.func.sum(Company.monthly_fee_net), 0))
        .filter(Company.is_retainer == True).scalar() or 0
    )
    mrr_count = Company.query.filter(Company.is_retainer == True, Company.monthly_fee_net > 0).count()
    active_projects = Project.query.filter_by(status="active").count()
    planning_projects = Project.query.filter_by(status="planning").count()
    content_wip = ContentPost.query.filter(ContentPost.status.in_(["writing", "review"])).count()
    content_ideas = ContentPost.query.filter_by(status="idea").count()

    # Recent activity (audit log entries - kto co zrobil). 30 na dashboardzie,
    # pelna historia na /aktywnosci.
    recent_activity = AuditLog.query.order_by(AuditLog.created_at.desc()).limit(30).all()

    # ── Command Center metrics ────────────────────────────────────
    # Heatmap 7 dni × 24 godziny (poniedzialek..niedziela) aktywnosci z AuditLogu.
    heatmap_start = datetime.combine(today - timedelta(days=6), datetime.min.time())
    heatmap_logs = AuditLog.query.filter(AuditLog.created_at >= heatmap_start).all()
    heatmap = [[0] * 24 for _day in range(7)]
    for log in heatmap_logs:
        day_off = (log.created_at.date() - heatmap_start.date()).days
        if 0 <= day_off < 7:
            heatmap[day_off][log.created_at.hour] += 1
    heatmap_max = max((cell for row in heatmap for cell in row), default=0) or 1

    # Peak hours - znajdz okno 2h z najwieksza aktywnoscia
    hour_totals = [0] * 24
    for row in heatmap:
        for h, v in enumerate(row):
            hour_totals[h] += v
    peak_start = 14
    peak_best = -1
    for h in range(23):
        s = hour_totals[h] + hour_totals[h + 1]
        if s > peak_best:
            peak_best = s; peak_start = h
    heatmap_peak = f"{peak_start:02d}-{peak_start + 2:02d}" if peak_best > 0 else "-"

    avg_daily_activity = sum(hour_totals) / 7.0

    # Serie 7-dniowe do sparkline (przeterminowane + zadania + finanse uproszczone)
    def _daily_counts(query_factory):
        out = []
        for i in range(6, -1, -1):
            d = today - timedelta(days=i)
            out.append(query_factory(d))
        return out

    # Optymalizacja: zamiast osobnego zapytania na każdy dzień (7 + 7 + do 60 zapytań)
    # pobieramy dane raz i liczymy w Pythonie. Wyniki są identyczne.
    open_deadlines = [row[0] for row in db.session.query(Task.deadline).filter(
        Task.status != "done",
        Task.deadline != None,
        Task.deadline < today,
    ).all()]
    spark_overdue = _daily_counts(lambda d: sum(1 for dl in open_deadlines if dl < d))

    done_per_day = {}
    for (day, n) in db.session.query(db.func.date(Task.done_at), db.func.count(Task.id)).filter(
        Task.status == "done",
        Task.done_at != None,
        Task.done_at >= datetime.combine(today - timedelta(days=61), datetime.min.time()),
    ).group_by(db.func.date(Task.done_at)).all():
        done_per_day[str(day)[:10]] = n
    spark_week_done = _daily_counts(lambda d: done_per_day.get(d.isoformat(), 0))

    # Streak - ile ostatnich dni mialo zamkniete zadania
    streak_days = 0
    probe = today
    for _step in range(60):
        any_done = probe.isoformat() in done_per_day
        if not any_done:
            if probe == today:
                probe -= timedelta(days=1)
                continue
            break
        streak_days += 1
        probe -= timedelta(days=1)

    completed_this_week = Task.query.filter(
        Task.status == "done",
        Task.done_at != None,
        Task.done_at >= datetime.combine(today - timedelta(days=today.weekday()), datetime.min.time()),
    ).count()
    prev_week_start = today - timedelta(days=today.weekday() + 7)
    prev_week_end = prev_week_start + timedelta(days=7)
    completed_last_week = Task.query.filter(
        Task.status == "done",
        Task.done_at != None,
        Task.done_at >= datetime.combine(prev_week_start, datetime.min.time()),
        Task.done_at <  datetime.combine(prev_week_end,   datetime.min.time()),
    ).count()
    weekly_goal = max(completed_last_week + 5, 20)

    # "Puls zespołu" - każda aktywna osoba, zalogowana pierwsza. Dwa zapytania niezależnie od
    # wielkości zespołu (wcześniej 3 zapytania na osobę i sztywny limit dwóch osób).
    pulse_users = []
    cu = get_current_user()
    user_list = User.query.filter_by(is_active=True).order_by(User.id).all()
    if cu is not None:
        user_list.sort(key=lambda u: u.id != cu.id)
    open_tasks = db.session.query(Task.created_by_user_id, Task.updated_by_user_id, Task.deadline).filter(
        Task.status != "done").all()
    last_seen_by_user = dict(db.session.query(AuditLog.user_id, db.func.max(AuditLog.created_at))
                             .filter(AuditLog.user_id != None).group_by(AuditLog.user_id).all())
    for u in user_list:
        mine = [t for t in open_tasks if u.id in (t.created_by_user_id, t.updated_by_user_id)]
        active_count = len(mine)
        overdue_count = sum(1 for t in mine if t.deadline is not None and t.deadline < today)
        last_seen = last_seen_by_user.get(u.id)
        online = last_seen is not None and (now_dt - last_seen).total_seconds() < 30 * 60
        pulse_users.append({
            "user": u,
            "active": active_count,
            "overdue": overdue_count,
            "online": online,
            "last_seen": last_seen,
            "load_pct": min(100, active_count * 10),
            "is_me": (cu is not None and cu.id == u.id),
        })

    # Firmy + ich "zdrowie" (prosty heurystyczny score 0..1)
    firm_rows = (Company.query
                 .order_by(Company.updated_at.desc() if hasattr(Company, 'updated_at') else Company.id.desc())
                 .limit(6).all())
    firms_health = []
    for c in firm_rows:
        open_tasks = Task.query.filter_by(company_id=c.id).filter(Task.status != "done").count()
        overdue_tasks = Task.query.filter_by(company_id=c.id).filter(
            Task.status != "done",
            Task.deadline != None,
            Task.deadline < today,
        ).count()
        score = 0.9
        if overdue_tasks:
            score -= min(0.5, 0.1 * overdue_tasks)
        if c.next_action_date and c.next_action_date < today:
            score -= 0.2
        if c.is_retainer:
            score += 0.05
        score = max(0.15, min(1.0, score))
        firms_health.append({
            "company": c,
            "health": score,
            "tasks": open_tasks,
            "overdue": overdue_tasks,
        })

    # Miesieczne serie bilansu - ostatnie 6 miesiecy (income, balance)
    finance_trend = []
    for offset in range(5, -1, -1):
        y = today.year
        m = today.month - offset
        while m <= 0:
            m += 12; y -= 1
        b = finance_helpers.monthly_balance(y, m, allocate_overhead=False)
        finance_trend.append({
            "label": f"{m:02d}",
            "income": float(b.get("revenue_total", 0) or 0),
            "costs": float(b.get("expense_total", 0) or 0),
            "balance": float(b.get("balance", 0) or 0),
        })

    return render_template(
        "dashboard.html",
        tasks_today=tasks_today,
        tasks_overdue=tasks_overdue,
        tasks_week=tasks_week,
        total_companies=total_companies,
        total_audits=total_audits,
        balance=balance,
        overdue=overdue,
        overdue_summary=overdue,
        upcoming_visits=upcoming_visits,
        upcoming_content=upcoming_content,
        attention=attention,
        recent_personal_notes=recent_personal_notes,
        pipeline_counts=pipeline_counts,
        stages=PIPELINE_STAGES,
        mrr_total=mrr_total,
        mrr_count=mrr_count,
        active_projects=active_projects,
        planning_projects=planning_projects,
        content_wip=content_wip,
        content_ideas=content_ideas,
        recent_activity=recent_activity,
        heatmap=heatmap,
        heatmap_max=heatmap_max,
        heatmap_peak=heatmap_peak,
        avg_daily_activity=avg_daily_activity,
        spark_overdue=spark_overdue,
        spark_week_done=spark_week_done,
        streak_days=streak_days,
        completed_this_week=completed_this_week,
        completed_last_week=completed_last_week,
        weekly_goal=weekly_goal,
        pulse_users=pulse_users,
        firms_health=firms_health,
        finance_trend=finance_trend,
    )
