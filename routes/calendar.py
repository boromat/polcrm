"""Visit calendar and legacy CSV download."""

from datetime import date, datetime, timedelta

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

from core import (
    CSV_DIR,
    _parse_date,
    app,
)
from i18n import _
from models import (
    Company,
    ContentPost,
    Task,
    Visit,
    db,
    utcnow,
)

# ── Calendar / Visits ─────────────────────────────────────────

@app.route("/calendar")
def calendar():
    # Enabled event types (toggle via query params)
    show_visits = request.args.get("visits", "1") != "0"
    show_tasks = request.args.get("tasks", "1") != "0"
    show_content_deadlines = request.args.get("content_dl", "1") != "0"
    show_content_pub = request.args.get("content_pub", "1") != "0"

    visits = Visit.query.order_by(Visit.scheduled_at).all()
    events = []

    # 1) Wizyty - cyjan
    if show_visits:
        for v in visits:
            events.append({
                "id": f"visit-{v.id}",
                "title": f"🤝 {v.company.name} - {v.type_label}",
                "start": v.scheduled_at.isoformat(),
                "end": (v.scheduled_at + timedelta(minutes=v.duration_minutes)).isoformat(),
                "backgroundColor": "#22d3ee",
                "borderColor": "#22d3ee",
                "url": url_for("visit_detail", id=v.id),
                "classNames": ["cal-ev-visit"],
                "extendedProps": {"type": "visit"},
            })

    # 2) Task deadliny - amber (urgent=red, overdue=red, done=emerald)
    if show_tasks:
        today = date.today()
        tasks_with_deadline = Task.query.filter(Task.deadline != None).all()
        for t in tasks_with_deadline:
            if t.status == "done":
                color = "#34d399"
            elif t.deadline < today:
                color = "#ef4444"  # overdue
            elif t.priority == "urgent":
                color = "#f87171"
            else:
                color = "#fbbf24"  # amber warning
            events.append({
                "id": f"task-{t.id}",
                "title": f"✓ {t.title}",
                "start": t.deadline.isoformat(),
                "allDay": True,
                "backgroundColor": color,
                "borderColor": color,
                "url": url_for("task_detail", id=t.id),
                "classNames": ["cal-ev-task"],
                "extendedProps": {"type": "task"},
            })

    # 3) Content deadliny - pink
    if show_content_deadlines:
        posts_dl = ContentPost.query.filter(
            ContentPost.deadline != None,
            ContentPost.status != "published",
        ).all()
        for p in posts_dl:
            events.append({
                "id": f"content-dl-{p.id}",
                "title": f"📝 {p.title}",
                "start": p.deadline.isoformat(),
                "allDay": True,
                "backgroundColor": "#ec4899",
                "borderColor": "#ec4899",
                "url": url_for("content_edit", id=p.id),
                "classNames": ["cal-ev-content-dl"],
                "extendedProps": {"type": "content_deadline"},
            })

    # 4) Content publikacje - zielony
    if show_content_pub:
        posts_pub = ContentPost.query.filter(ContentPost.published_at != None).all()
        for p in posts_pub:
            events.append({
                "id": f"content-pub-{p.id}",
                "title": f"✨ {p.title}",
                "start": p.published_at.isoformat(),
                "allDay": False,
                "backgroundColor": "#10b981",
                "borderColor": "#10b981",
                "url": url_for("content_edit", id=p.id),
                "classNames": ["cal-ev-content-pub"],
                "extendedProps": {"type": "content_publish"},
            })

    filters = {
        "visits": show_visits,
        "tasks": show_tasks,
        "content_dl": show_content_deadlines,
        "content_pub": show_content_pub,
    }
    return render_template("calendar.html", events=events, visits=visits, filters=filters)


@app.route("/visits/new/<int:company_id>", methods=["POST"])
def visit_new(company_id):
    db.get_or_404(Company, company_id)
    dt = request.form.get("scheduled_at", "")
    v = Visit(
        company_id=company_id,
        scheduled_at=datetime.fromisoformat(dt) if dt else utcnow(),
        duration_minutes=int(request.form.get("duration_minutes", "60")),
        visit_type=request.form.get("visit_type", "consultation"),
        status="planned",
    )
    db.session.add(v)
    c = db.session.get(Company, company_id)
    if c.pipeline_stage in ("audit", "contact"):
        c.pipeline_stage = "visit"
    db.session.commit()
    flash(_("Wizyta zaplanowana."), "success")
    return redirect(url_for("company_detail", id=company_id))


@app.route("/visits/<int:id>", methods=["GET", "POST"])
def visit_detail(id):
    v = db.get_or_404(Visit, id)
    if request.method == "POST":
        v.status = request.form.get("status", v.status)
        v.notes = request.form.get("notes", "").strip()
        v.outcome = request.form.get("outcome", "").strip()
        v.follow_up_action = request.form.get("follow_up_action", "").strip()
        v.follow_up_date = _parse_date(request.form.get("follow_up_date", ""))
        v.prep_report_printed = "prep_report_printed" in request.form
        v.prep_screenshots = "prep_screenshots" in request.form
        v.prep_offer_template = "prep_offer_template" in request.form
        v.prep_questions = "prep_questions" in request.form
        dt = request.form.get("scheduled_at", "").strip()
        if dt:
            v.scheduled_at = datetime.fromisoformat(dt)
        db.session.commit()
        flash(_("Wizyta zaktualizowana."), "success")
        return redirect(url_for("visit_detail", id=v.id))
    return render_template("calendar_detail.html", visit=v)


@app.route("/visit-guide")
def visit_guide():
    return render_template("visit_guide.html")


# ── CSV Download (legacy) ─────────────────────────────────────

@app.route("/download/<path:filename>")
def download(filename):
    # Sanityzacja nazwy + upewnienie sie, ze wynikowa sciezka zostaje w CSV_DIR
    safe = secure_filename(filename)
    if not safe or safe != filename:
        abort(404)
    csv_path = (CSV_DIR / safe).resolve()
    try:
        csv_path.relative_to(CSV_DIR.resolve())
    except ValueError:
        abort(404)
    if not csv_path.is_file():
        flash(_("Plik CSV nie zostal znaleziony."), "danger")
        return redirect(url_for("dashboard"))
    return send_file(csv_path, mimetype="text/csv", as_attachment=True, download_name=safe)
