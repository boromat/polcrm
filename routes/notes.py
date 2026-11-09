"""Notes (personal, company and project notes)."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    _parse_int,
    app,
)
from i18n import _
from models import (
    NOTE_SCOPES,
    Company,
    Note,
    Project,
    db,
)

# ── Notes ─────────────────────────────────────────────────────

@app.route("/companies/<int:company_id>/notes", methods=["POST"])
def note_add(company_id):
    db.get_or_404(Company, company_id)
    n = Note(
        company_id=company_id,
        scope="company",
        title=request.form.get("title", "").strip(),
        content=request.form.get("content", "").strip(),
        note_type=request.form.get("note_type", "general"),
    )
    db.session.add(n)
    db.session.commit()
    flash(_("Dodano notatkę."), "success")
    return redirect(url_for("company_detail", id=company_id))


@app.route("/notes")
def notes_list():
    scope = request.args.get("scope", "")
    q = Note.query
    if scope in NOTE_SCOPES:
        q = q.filter_by(scope=scope)
    notes = q.order_by(Note.pinned.desc(), Note.created_at.desc()).all()
    return render_template("notes/list.html", notes=notes, scope=scope, scopes=NOTE_SCOPES)


@app.route("/notes/new", methods=["GET", "POST"])
def note_new():
    if request.method == "POST":
        scope = request.form.get("scope", "personal")
        company_id = _parse_int(request.form.get("company_id"))
        project_id = _parse_int(request.form.get("project_id"))
        n = Note(
            scope=scope,
            company_id=company_id if scope == "company" else None,
            project_id=project_id if scope == "project" else None,
            title=request.form.get("title", "").strip(),
            content=request.form.get("content", "").strip(),
            note_type=request.form.get("note_type", "general"),
            pinned="pinned" in request.form,
        )
        if not n.content:
            flash(_("Treść notatki nie może być pusta."), "danger")
            return redirect(url_for("note_new"))
        db.session.add(n)
        db.session.commit()
        flash(_("Notatka dodana."), "success")
        return redirect(url_for("notes_list", scope=scope))

    companies = Company.query.order_by(Company.name).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template("notes/form.html", note=None, companies=companies, projects=projects,
                           scopes=NOTE_SCOPES, preset_scope=request.args.get("scope", "personal"))


@app.route("/notes/<int:id>/edit", methods=["GET", "POST"])
def note_edit(id):
    n = db.get_or_404(Note, id)
    if request.method == "POST":
        n.title = request.form.get("title", "").strip()
        n.content = request.form.get("content", "").strip()
        n.note_type = request.form.get("note_type", n.note_type)
        n.pinned = "pinned" in request.form
        db.session.commit()
        flash(_("Notatka zapisana."), "success")
        return redirect(url_for("notes_list", scope=n.scope))
    companies = Company.query.order_by(Company.name).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template("notes/form.html", note=n, companies=companies, projects=projects,
                           scopes=NOTE_SCOPES, preset_scope=n.scope)


@app.route("/notes/<int:id>/delete", methods=["POST"])
def note_delete(id):
    n = db.get_or_404(Note, id)
    scope = n.scope
    db.session.delete(n)
    db.session.commit()
    flash(_("Notatka usunięta."), "success")
    return redirect(url_for("notes_list", scope=scope))
