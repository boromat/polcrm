"""Web projects."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    _parse_date,
    _parse_float,
    _parse_int,
    app,
)
from i18n import _
from models import (
    PROJECT_KINDS,
    PROJECT_STATUSES,
    TASK_PRIORITIES,
    TASK_STATUSES,
    Company,
    Project,
    Task,
    db,
)

# ═══════════════════════════════════════════════════════════════
#  PROJEKTY
# ═══════════════════════════════════════════════════════════════

@app.route("/projects")
def projects_list():
    status = request.args.get("status", "")
    q = Project.query
    if status in PROJECT_STATUSES:
        q = q.filter_by(status=status)
    projects = q.order_by(Project.status, Project.deadline.asc().nullslast() if hasattr(Project.deadline.asc(), 'nullslast') else Project.deadline.asc()).all()
    return render_template("projects/list.html", projects=projects, status=status,
                           statuses=PROJECT_STATUSES)


@app.route("/projects/<int:id>")
def project_detail(id):
    p = db.get_or_404(Project, id)
    tasks = Task.query.filter_by(project_id=p.id).order_by(Task.status, Task.order_hint, Task.id).all()
    return render_template("projects/detail.html", project=p, tasks=tasks,
                           priorities=TASK_PRIORITIES, statuses=TASK_STATUSES)


@app.route("/projects/new", methods=["GET", "POST"])
def project_new():
    if request.method == "POST":
        p = Project(
            company_id=int(request.form.get("company_id")),
            name=request.form.get("name", "").strip(),
            kind=request.form.get("kind", "website"),
            domain=request.form.get("domain", "").strip(),
            cms=request.form.get("cms", "").strip(),
            hosting=request.form.get("hosting", "").strip(),
            budget_net=_parse_float(request.form.get("budget_net")),
            status=request.form.get("status", "planning"),
            started_at=_parse_date(request.form.get("started_at")),
            deadline=_parse_date(request.form.get("deadline")),
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(p)
        db.session.commit()
        flash(_("Projekt %(name)s dodany.", name=p.name), "success")
        return redirect(url_for("project_detail", id=p.id))
    companies = Company.query.order_by(Company.name).all()
    return render_template("projects/form.html", project=None, companies=companies,
                           kinds=PROJECT_KINDS, statuses=PROJECT_STATUSES,
                           preset_company_id=_parse_int(request.args.get("company_id")))


@app.route("/projects/<int:id>/edit", methods=["GET", "POST"])
def project_edit(id):
    p = db.get_or_404(Project, id)
    if request.method == "POST":
        p.company_id = int(request.form.get("company_id"))
        p.name = request.form.get("name", p.name).strip()
        p.kind = request.form.get("kind", p.kind)
        p.domain = request.form.get("domain", "").strip()
        p.cms = request.form.get("cms", "").strip()
        p.hosting = request.form.get("hosting", "").strip()
        p.budget_net = _parse_float(request.form.get("budget_net"))
        p.status = request.form.get("status", p.status)
        p.started_at = _parse_date(request.form.get("started_at"))
        p.deadline = _parse_date(request.form.get("deadline"))
        p.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash(_("Projekt zapisany."), "success")
        return redirect(url_for("project_detail", id=p.id))
    companies = Company.query.order_by(Company.name).all()
    return render_template("projects/form.html", project=p, companies=companies,
                           kinds=PROJECT_KINDS, statuses=PROJECT_STATUSES,
                           preset_company_id=p.company_id)


@app.route("/projects/<int:id>/delete", methods=["POST"])
def project_delete(id):
    p = db.get_or_404(Project, id)
    db.session.delete(p)
    db.session.commit()
    flash(_("Projekt usunięty."), "success")
    return redirect(url_for("projects_list"))
