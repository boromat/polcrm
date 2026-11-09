"""Content plan and publishing calendar."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    _parse_date,
    _parse_int,
    _safe_referrer,
    app,
)
from i18n import _
from models import (
    CONTENT_STATUSES,
    CONTENT_TYPES,
    Company,
    ContentPost,
    db,
    utcnow,
)

# ═══════════════════════════════════════════════════════════════
#  CONTENT CALENDAR
# ═══════════════════════════════════════════════════════════════

@app.route("/content")
def content_list():
    status = request.args.get("status", "")
    company_id = _parse_int(request.args.get("company_id"))
    q = ContentPost.query
    if status in CONTENT_STATUSES:
        q = q.filter_by(status=status)
    if company_id:
        q = q.filter_by(company_id=company_id)
    posts = q.order_by(ContentPost.deadline.asc().nullslast() if hasattr(ContentPost.deadline.asc(), 'nullslast') else ContentPost.deadline.asc()).all()
    companies = Company.query.order_by(Company.name).all()
    return render_template("content/list.html", posts=posts, status=status,
                           selected_company_id=company_id, companies=companies,
                           statuses=CONTENT_STATUSES, types=CONTENT_TYPES)


@app.route("/content/calendar")
def content_calendar():
    posts = ContentPost.query.filter(ContentPost.deadline != None).all()
    colors = {
        "idea": "#6b7280", "writing": "#3b82f6", "review": "#f59e0b",
        "approved": "#10b981", "published": "#8b5cf6",
    }
    events = []
    for p in posts:
        events.append({
            "id": p.id,
            "title": f"{p.company.name}: {p.title}",
            "start": p.deadline.isoformat() if p.deadline else None,
            "color": colors.get(p.status, "#6c5ce7"),
            "url": url_for("content_edit", id=p.id),
        })
    return render_template("content/calendar.html", events=events)


@app.route("/content/new", methods=["GET", "POST"])
def content_new():
    if request.method == "POST":
        kws = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        p = ContentPost(
            company_id=int(request.form.get("company_id")),
            title=request.form.get("title", "").strip(),
            content_type=request.form.get("content_type", "blog"),
            status=request.form.get("status", "idea"),
            deadline=_parse_date(request.form.get("deadline")),
            writer_name=request.form.get("writer_name", "").strip(),
            brief=request.form.get("brief", "").strip(),
            url=request.form.get("url", "").strip(),
        )
        p.keywords = kws
        db.session.add(p)
        db.session.commit()
        flash(_("Publikacja dodana do kalendarza."), "success")
        return redirect(url_for("content_list"))
    companies = Company.query.order_by(Company.name).all()
    return render_template("content/form.html", post=None, companies=companies,
                           statuses=CONTENT_STATUSES, types=CONTENT_TYPES,
                           preset_company_id=_parse_int(request.args.get("company_id")))


@app.route("/content/<int:id>/edit", methods=["GET", "POST"])
def content_edit(id):
    p = db.get_or_404(ContentPost, id)
    if request.method == "POST":
        kws = [k.strip() for k in request.form.get("keywords", "").split(",") if k.strip()]
        p.company_id = int(request.form.get("company_id"))
        p.title = request.form.get("title", p.title).strip()
        p.content_type = request.form.get("content_type", p.content_type)
        new_status = request.form.get("status", p.status)
        if new_status == "published" and p.status != "published":
            p.published_at = utcnow()
        p.status = new_status
        p.deadline = _parse_date(request.form.get("deadline"))
        p.writer_name = request.form.get("writer_name", "").strip()
        p.brief = request.form.get("brief", "").strip()
        p.url = request.form.get("url", "").strip()
        p.keywords = kws
        db.session.commit()
        flash(_("Publikacja zapisana."), "success")
        return redirect(url_for("content_list"))
    companies = Company.query.order_by(Company.name).all()
    return render_template("content/form.html", post=p, companies=companies,
                           statuses=CONTENT_STATUSES, types=CONTENT_TYPES,
                           preset_company_id=p.company_id)


@app.route("/content/<int:id>/delete", methods=["POST"])
def content_delete(id):
    p = db.get_or_404(ContentPost, id)
    db.session.delete(p)
    db.session.commit()
    flash(_("Publikacja usunięta."), "success")
    return redirect(url_for("content_list"))


@app.route("/content/<int:id>/status", methods=["POST"])
def content_status(id):
    p = db.get_or_404(ContentPost, id)
    new_status = request.form.get("status")
    if new_status in CONTENT_STATUSES:
        if new_status == "published" and p.status != "published":
            p.published_at = utcnow()
        p.status = new_status
        db.session.commit()
    return redirect(_safe_referrer(url_for("content_list")))
