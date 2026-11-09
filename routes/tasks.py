"""Tasks: list, kanban, detail with comments and files, mention inbox."""

import mimetypes
import uuid
from datetime import date, timedelta
from pathlib import Path

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    UPLOADS_DIR,
    _find_mentions,
    _log_audit,
    _parse_date,
    _parse_int,
    _render_markdown,
    _safe_referrer,
    app,
    get_current_user,
)
from i18n import _
from models import (
    TASK_PRIORITIES,
    TASK_STATUSES,
    AuditLog,
    ClientFile,
    Company,
    Mention,
    Project,
    Task,
    TaskComment,
    db,
    utcnow,
)

# ═══════════════════════════════════════════════════════════════
#  ZADANIA
# ═══════════════════════════════════════════════════════════════

@app.route("/tasks")
def tasks_list():
    scope = request.args.get("scope", "")  # today | week | overdue | all
    priority = request.args.get("priority", "")
    status = request.args.get("status", "")
    company_id = _parse_int(request.args.get("company_id"))
    view = request.args.get("view", "board")  # board | list | calendar
    if view not in ("board", "list", "calendar"):
        view = "board"

    q = Task.query.filter(Task.parent_task_id == None)  # hide subtasks from main list
    today = date.today()
    if scope == "today":
        q = q.filter(Task.status != "done", Task.deadline == today)
    elif scope == "week":
        q = q.filter(Task.status != "done", Task.deadline != None,
                     Task.deadline >= today, Task.deadline <= today + timedelta(days=7))
    elif scope == "overdue":
        q = q.filter(Task.status != "done", Task.deadline != None, Task.deadline < today)
    if priority in TASK_PRIORITIES:
        q = q.filter_by(priority=priority)
    if status in TASK_STATUSES:
        q = q.filter_by(status=status)
    if company_id:
        q = q.filter_by(company_id=company_id)

    tasks = q.order_by(Task.status.asc(), Task.deadline.asc().nullslast() if hasattr(Task.deadline.asc(), 'nullslast') else Task.deadline.asc()).all()
    companies = Company.query.order_by(Company.name).all()

    # Kanban pre-grouping (used when filters are off = "wszystkie")
    week_end = today + timedelta(days=7)
    kb = {"overdue": [], "today": [], "week": [], "later": [], "done": []}
    for t in tasks:
        if t.status == "done":
            kb["done"].append(t)
        elif t.deadline and t.deadline < today:
            kb["overdue"].append(t)
        elif t.deadline == today or (t.deadline is None and t.priority == "urgent"):
            kb["today"].append(t)
        elif t.deadline and today < t.deadline <= week_end:
            kb["week"].append(t)
        else:
            kb["later"].append(t)

    # Calendar view - JSON events
    calendar_events = []
    if view == "calendar":
        for t in tasks:
            if not t.deadline:
                continue
            color = "#94a3b8"
            if t.status == "done":
                color = "#34d399"
            elif t.is_overdue:
                color = "#f87171"
            elif t.priority == "urgent":
                color = "#ef4444"
            elif t.priority == "high":
                color = "#fbbf24"
            elif t.priority == "medium":
                color = "#a29bfe"
            calendar_events.append({
                "id": t.id,
                "title": t.title,
                "start": t.deadline.isoformat(),
                "url": f"/tasks/{t.id}",
                "backgroundColor": color,
                "borderColor": color,
            })

    return render_template("tasks/list.html", tasks=tasks, scope=scope, priority=priority,
                           status=status, selected_company_id=company_id,
                           priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                           companies=companies, kb=kb,
                           view=view, calendar_events=calendar_events)


@app.route("/tasks/new", methods=["GET", "POST"])
def task_new():
    if request.method == "POST":
        t = Task(
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            priority=request.form.get("priority", "medium"),
            status=request.form.get("status", "todo"),
            deadline=_parse_date(request.form.get("deadline")),
            company_id=_parse_int(request.form.get("company_id")),
            project_id=_parse_int(request.form.get("project_id")),
            content_post_id=_parse_int(request.form.get("content_post_id")),
        )
        if not t.title:
            flash(_("Tytuł zadania jest wymagany."), "danger")
            return redirect(url_for("task_new"))
        db.session.add(t)
        db.session.commit()
        flash(_("Zadanie dodane."), "success")
        return redirect(url_for("tasks_list"))
    companies = Company.query.order_by(Company.name).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template("tasks/form.html", task=None, companies=companies, projects=projects,
                           priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                           preset_company_id=_parse_int(request.args.get("company_id")),
                           preset_project_id=_parse_int(request.args.get("project_id")))


@app.route("/tasks/<int:id>/edit", methods=["GET", "POST"])
def task_edit(id):
    t = db.get_or_404(Task, id)
    if request.method == "POST":
        t.title = request.form.get("title", t.title).strip()
        t.description = request.form.get("description", "").strip()
        t.priority = request.form.get("priority", t.priority)
        new_status = request.form.get("status", t.status)
        if new_status == "done" and t.status != "done":
            t.done_at = utcnow()
        t.status = new_status
        t.deadline = _parse_date(request.form.get("deadline"))
        t.company_id = _parse_int(request.form.get("company_id"))
        t.project_id = _parse_int(request.form.get("project_id"))
        t.content_post_id = _parse_int(request.form.get("content_post_id"))
        db.session.commit()
        flash(_("Zadanie zapisane."), "success")
        return redirect(url_for("tasks_list"))
    companies = Company.query.order_by(Company.name).all()
    projects = Project.query.order_by(Project.name).all()
    return render_template("tasks/form.html", task=t, companies=companies, projects=projects,
                           priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
                           preset_company_id=t.company_id, preset_project_id=t.project_id)


@app.route("/tasks/<int:id>/status", methods=["POST"])
def task_status(id):
    t = db.get_or_404(Task, id)
    new_status = request.form.get("status") or (request.get_json() or {}).get("status")
    if new_status in TASK_STATUSES:
        if new_status == "done" and t.status != "done":
            t.done_at = utcnow()
        t.status = new_status
        db.session.commit()
    if request.is_json:
        return jsonify({"ok": True, "status": t.status})
    return redirect(_safe_referrer(url_for("tasks_list")))


@app.route("/tasks/<int:id>/delete", methods=["POST"])
def task_delete(id):
    t = db.get_or_404(Task, id)
    db.session.delete(t)
    db.session.commit()
    flash(_("Zadanie usuniete."), "success")
    return redirect(_safe_referrer(url_for("tasks_list")))


@app.route("/api/tasks/move", methods=["POST"])
def api_task_move():
    """Drag & drop Kanban: przesuniecie zadania miedzy kolumnami zmienia deadline.
    Kolumny: overdue | today | week | later | done.
    done → ustawia status=done. Inne → status=todo (jezeli byl done)."""
    data = request.get_json() or {}
    task_id = data.get("task_id")
    column = data.get("column")
    if column not in {"overdue", "today", "week", "later", "done"}:
        return jsonify({"error": "Invalid column"}), 400
    t = db.session.get(Task, task_id)
    if not t:
        return jsonify({"error": "Task not found"}), 404

    today = date.today()
    if column == "done":
        if t.status != "done":
            t.status = "done"
            t.done_at = utcnow()
    else:
        # Przywroc todo jesli wracamy z done
        if t.status == "done":
            t.status = "todo"
            t.done_at = None
        if column == "overdue":
            t.deadline = today - timedelta(days=1)
        elif column == "today":
            t.deadline = today
        elif column == "week":
            t.deadline = today + timedelta(days=3)
        elif column == "later":
            t.deadline = today + timedelta(days=14)
    db.session.commit()
    return jsonify({"ok": True, "status": t.status, "deadline": t.deadline.isoformat() if t.deadline else None})


# ── Task detail (rich editor, subtaski, komentarze, timeline) ──

@app.route("/tasks/<int:id>", methods=["GET", "POST"])
def task_detail(id):
    t = db.get_or_404(Task, id)
    if request.method == "POST":
        old_title = t.title
        old_status = t.status
        old_priority = t.priority
        old_deadline = t.deadline
        old_description = t.description or ""

        t.title = request.form.get("title", t.title).strip()
        t.description = request.form.get("description", "").strip()
        t.priority = request.form.get("priority", t.priority)
        new_status = request.form.get("status", t.status)
        if new_status == "done" and t.status != "done":
            t.done_at = utcnow()
        t.status = new_status
        t.deadline = _parse_date(request.form.get("deadline"))
        t.company_id = _parse_int(request.form.get("company_id"))
        t.project_id = _parse_int(request.form.get("project_id"))

        # Audit log field changes
        if t.title != old_title:
            _log_audit("tasks", t.id, "update", "title", old_title, t.title)
        if t.status != old_status:
            _log_audit("tasks", t.id, "status_change", "status", old_status, t.status)
        if t.priority != old_priority:
            _log_audit("tasks", t.id, "update", "priority", old_priority, t.priority)
        if t.deadline != old_deadline:
            _log_audit("tasks", t.id, "update", "deadline",
                       old_deadline.isoformat() if old_deadline else "",
                       t.deadline.isoformat() if t.deadline else "")
        if (t.description or "") != old_description:
            _log_audit("tasks", t.id, "update", "description", "", _("(zmieniono opis)"))
            # Extract new mentions from description
            _find_mentions(t.description, "task_description", t.id, task_id=t.id,
                           snippet=t.title)

        db.session.commit()
        flash(_("Zadanie zaktualizowane."), "success")
        return redirect(url_for("task_detail", id=t.id))

    companies = Company.query.order_by(Company.name).all()
    projects = Project.query.order_by(Project.name).all()
    comments = TaskComment.query.filter_by(task_id=t.id).order_by(TaskComment.created_at).all()
    audit_entries = AuditLog.query.filter_by(table_name="tasks", record_id=t.id)\
        .order_by(AuditLog.created_at.desc()).limit(50).all()
    description_html = _render_markdown(t.description or "")
    return render_template(
        "tasks/detail.html",
        task=t, companies=companies, projects=projects,
        priorities=TASK_PRIORITIES, statuses=TASK_STATUSES,
        comments=comments,
        audit_entries=audit_entries,
        description_html=description_html,
    )


@app.route("/tasks/<int:id>/subtask", methods=["POST"])
def task_subtask_new(id):
    parent = db.get_or_404(Task, id)
    title = (request.form.get("title") or "").strip()
    if not title:
        flash(_("Podaj tytuł subtaska."), "warning")
        return redirect(url_for("task_detail", id=id))
    sub = Task(
        title=title,
        priority=request.form.get("priority", "medium"),
        status="todo",
        company_id=parent.company_id,
        project_id=parent.project_id,
        parent_task_id=parent.id,
    )
    db.session.add(sub)
    db.session.flush()
    _log_audit("tasks", parent.id, "update", "subtasks", "", f"+{title}")
    db.session.commit()
    return redirect(url_for("task_detail", id=id))


@app.route("/tasks/subtask/<int:sid>/toggle", methods=["POST"])
def task_subtask_toggle(sid):
    s = db.get_or_404(Task, sid)
    if s.status == "done":
        s.status = "todo"
        s.done_at = None
    else:
        s.status = "done"
        s.done_at = utcnow()
    db.session.commit()
    parent_id = s.parent_task_id or s.id
    return redirect(url_for("task_detail", id=parent_id))


@app.route("/tasks/subtask/<int:sid>/delete", methods=["POST"])
def task_subtask_delete(sid):
    s = db.get_or_404(Task, sid)
    parent_id = s.parent_task_id
    db.session.delete(s)
    db.session.commit()
    if parent_id:
        return redirect(url_for("task_detail", id=parent_id))
    return redirect(url_for("tasks_list"))


@app.route("/tasks/<int:id>/comment", methods=["POST"])
def task_comment_new(id):
    t = db.get_or_404(Task, id)
    body = (request.form.get("body") or "").strip()
    if not body:
        flash(_("Komentarz nie może być pusty."), "warning")
        return redirect(url_for("task_detail", id=id))
    user = get_current_user()
    c = TaskComment(task_id=t.id, user_id=user.id if user else None, body=body)
    db.session.add(c)
    db.session.flush()
    _find_mentions(body, "task_comment", c.id, task_id=t.id, snippet=body)
    _log_audit("tasks", t.id, "comment", "", "", "", note=body[:120])
    db.session.commit()
    return redirect(url_for("task_detail", id=id))


@app.route("/comment/<int:cid>/delete", methods=["POST"])
def task_comment_delete(cid):
    c = db.get_or_404(TaskComment, cid)
    task_id = c.task_id
    db.session.delete(c)
    db.session.commit()
    return redirect(url_for("task_detail", id=task_id))


# ── Task files (upload / download / delete) ──

@app.route("/tasks/<int:id>/upload", methods=["POST"])
def task_file_upload(id):
    t = db.get_or_404(Task, id)
    f = request.files.get("file")
    if not f or not f.filename:
        flash(_("Wybierz plik do wgrania."), "danger")
        return redirect(url_for("task_detail", id=id))

    task_dir = UPLOADS_DIR / "tasks" / str(t.id)
    task_dir.mkdir(parents=True, exist_ok=True)
    ext = Path(f.filename).suffix
    stored_name = f"{uuid.uuid4().hex}{ext}"
    target_path = task_dir / stored_name
    f.save(target_path)

    user = get_current_user()
    cf = ClientFile(
        task_id=t.id,
        company_id=t.company_id,
        project_id=t.project_id,
        filename=f.filename,
        label=f.filename,
        stored_path=f"uploads/tasks/{t.id}/{stored_name}",
        mime=f.mimetype or (mimetypes.guess_type(f.filename)[0] or "application/octet-stream"),
        size_bytes=target_path.stat().st_size,
        category="other",
        uploaded_by_user_id=user.id if user else None,
    )
    db.session.add(cf)
    db.session.flush()
    _log_audit("tasks", t.id, "update", "files", "", f"+{f.filename}",
               note=_("Wgrano plik (%(size)s)", size=cf.size_human))
    db.session.commit()
    flash(_("Wgrano plik: %(name)s", name=f.filename), "success")
    return redirect(url_for("task_detail", id=id))


# ── Inbox (skrzynka mention) ──

@app.route("/inbox")
def inbox():
    user = get_current_user()
    if not user:
        return redirect(url_for("choose_profile"))
    mentions = Mention.query.filter_by(mentioned_user_id=user.id)\
        .order_by(Mention.created_at.desc()).limit(100).all()
    return render_template("inbox.html", mentions=mentions)


@app.route("/inbox/<int:mid>/read", methods=["POST"])
def inbox_mark_read(mid):
    m = db.get_or_404(Mention, mid)
    user = get_current_user()
    if user and m.mentioned_user_id == user.id and not m.read_at:
        m.read_at = utcnow()
        db.session.commit()
    # If destination is a task - redirect there
    if m.task_id:
        return redirect(url_for("task_detail", id=m.task_id))
    return redirect(url_for("inbox"))


@app.route("/inbox/read-all", methods=["POST"])
def inbox_read_all():
    user = get_current_user()
    if user:
        Mention.query.filter_by(mentioned_user_id=user.id, read_at=None)\
            .update({"read_at": utcnow()})
        db.session.commit()
    return redirect(url_for("inbox"))
