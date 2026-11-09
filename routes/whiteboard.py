"""Shared whiteboards (drawing, text, images) and their JSON API."""

import uuid
from datetime import timedelta

from flask import (
    abort,
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)
from werkzeug.utils import secure_filename

from core import (
    WHITEBOARD_IMG_DIR,
    _parse_int,
    app,
    get_current_user,
)
from i18n import _
from models import (
    WHITEBOARD_TOOLS,
    Company,
    Whiteboard,
    WhiteboardCursor,
    WhiteboardDeletion,
    WhiteboardStroke,
    db,
    delete_whiteboard,
    utcnow,
)

# ═══════════════════════════════════════════════════════════════
#  TABLICA (whiteboard) - wspoldzielone rysunki zespolu
# ═══════════════════════════════════════════════════════════════

def _stroke_to_dict(s):
    return {
        "id": s.id,
        "tool": s.tool,
        "color": s.color,
        "fill_color": s.fill_color or "",
        "width": s.width,
        "opacity": s.opacity,
        "points": s.points,
        "text": s.text or "",
        "font_size": s.font_size,
        "width_box": s.width_box or 0,
        "height_box": s.height_box or 0,
        "image_path": s.image_path or "",
        "stroke_order": s.stroke_order or 0,
        "author_id": s.author_user_id,
        "author_name": s.author.name if s.author else None,
        "author_color": s.author.avatar_color if s.author else "#6c5ce7",
    }


def _validate_points(points):
    if not isinstance(points, list) or not points:
        return None
    try:
        return [[float(p[0]), float(p[1])] for p in points
                if isinstance(p, (list, tuple)) and len(p) == 2]
    except (ValueError, TypeError):
        return None


@app.route("/tablica")
def whiteboard_list():
    company_id = _parse_int(request.args.get("company_id"))
    q = Whiteboard.query
    if company_id:
        q = q.filter_by(company_id=company_id)
    boards = q.order_by(Whiteboard.updated_at.desc()).all()
    companies = Company.query.order_by(Company.name).all()
    return render_template("whiteboard/list.html", boards=boards,
                           companies=companies, company_filter=company_id)


@app.route("/tablica/nowa", methods=["GET", "POST"])
def whiteboard_new():
    preset_company_id = _parse_int(request.args.get("company_id"))
    if request.method == "POST":
        name = (request.form.get("name") or "").strip() or _("Tablica bez nazwy")
        description = (request.form.get("description") or "").strip()
        bg_color = request.form.get("bg_color", "#ffffff")
        if bg_color not in ("#ffffff", "#0f0f1a", "#fef3c7"):
            bg_color = "#ffffff"
        company_id = _parse_int(request.form.get("company_id"))
        b = Whiteboard(name=name, description=description, bg_color=bg_color,
                       company_id=company_id)
        db.session.add(b)
        db.session.commit()
        flash(_("Utworzono tablice: %(name)s", name=b.name), "success")
        return redirect(url_for("whiteboard_detail", id=b.id))
    companies = Company.query.order_by(Company.name).all()
    return render_template("whiteboard/form.html", board=None, companies=companies,
                           preset_company_id=preset_company_id)


@app.route("/tablica/<int:id>", methods=["GET", "POST"])
def whiteboard_detail(id):
    b = db.get_or_404(Whiteboard, id)
    if request.method == "POST":
        b.name = (request.form.get("name") or b.name).strip()
        b.description = (request.form.get("description") or "").strip()
        b.company_id = _parse_int(request.form.get("company_id"))
        db.session.commit()
        flash(_("Zmiany zapisane."), "success")
        return redirect(url_for("whiteboard_detail", id=b.id))
    companies = Company.query.order_by(Company.name).all()
    return render_template("whiteboard/draw.html", board=b, companies=companies)


@app.route("/tablica/<int:id>/delete", methods=["POST"])
def whiteboard_delete(id):
    b = db.get_or_404(Whiteboard, id)
    delete_whiteboard(b)
    db.session.commit()
    flash(_("Tablica usunieta."), "success")
    return redirect(url_for("whiteboard_list"))


@app.route("/tablica/<int:id>/duplikuj", methods=["POST"])
def whiteboard_duplicate(id):
    """Sklonuj tablice (kopia wszystkich strokes pod nowa nazwa)."""
    orig = db.get_or_404(Whiteboard, id)
    copy = Whiteboard(
        name=_("%(name)s (kopia)", name=orig.name),
        description=orig.description,
        canvas_width=orig.canvas_width,
        canvas_height=orig.canvas_height,
        bg_color=orig.bg_color,
        company_id=orig.company_id,
    )
    db.session.add(copy)
    db.session.flush()  # zeby miec copy.id
    for s in orig.strokes:
        ns = WhiteboardStroke(
            whiteboard_id=copy.id,
            author_user_id=s.author_user_id,
            tool=s.tool,
            color=s.color,
            fill_color=s.fill_color,
            width=s.width,
            opacity=s.opacity,
            text=s.text,
            font_size=s.font_size,
            width_box=s.width_box,
            height_box=s.height_box,
            image_path=s.image_path,
            stroke_order=s.stroke_order,
        )
        ns.points = s.points
        db.session.add(ns)
    db.session.commit()
    flash(_("Sklonowano jako: %(name)s", name=copy.name), "success")
    return redirect(url_for("whiteboard_detail", id=copy.id))


# ── API endpointy (JSON) ──────────────────────────────────────

@app.route("/api/tablica/<int:id>/stroke", methods=["POST"])
def api_whiteboard_add_stroke(id):
    """Dodaj stroke dowolnego typu."""
    b = db.get_or_404(Whiteboard, id)
    data = request.get_json(silent=True) or {}

    tool = data.get("tool", "pen")
    if tool not in WHITEBOARD_TOOLS:
        return jsonify({"error": f"invalid tool: {tool}"}), 400

    points = _validate_points(data.get("points") or [])
    if points is None:
        return jsonify({"error": "invalid or missing points"}), 400

    user = get_current_user()

    # Oblicz stroke_order - nastepny po maksymalnym
    max_order = db.session.query(db.func.max(WhiteboardStroke.stroke_order))\
        .filter_by(whiteboard_id=b.id).scalar() or 0.0
    new_order = max_order + 1.0

    stroke = WhiteboardStroke(
        whiteboard_id=b.id,
        author_user_id=user.id if user else None,
        tool=tool,
        color=str(data.get("color", "#111111"))[:16],
        fill_color=str(data.get("fill_color", ""))[:16],
        width=float(data.get("width", 2.5)) if data.get("width") is not None else 2.5,
        opacity=float(data.get("opacity", 1.0)) if data.get("opacity") is not None else 1.0,
        text=str(data.get("text", ""))[:2000],
        font_size=float(data.get("font_size", 18.0)) if data.get("font_size") is not None else 18.0,
        width_box=float(data.get("width_box", 0)) if data.get("width_box") is not None else 0,
        height_box=float(data.get("height_box", 0)) if data.get("height_box") is not None else 0,
        image_path=str(data.get("image_path", ""))[:512],
        stroke_order=new_order,
    )
    stroke.points = points
    db.session.add(stroke)
    b.updated_at = utcnow()
    db.session.commit()

    return jsonify({
        "ok": True,
        "id": stroke.id,
        "stroke_order": new_order,
        "author": user.name if user else None,
        "author_color": user.avatar_color if user else "#6c5ce7",
    })


@app.route("/api/tablica/<int:id>/state")
def api_whiteboard_state(id):
    """Zwroc pelny stan tablicy + deletions + cursors (do pollingu)."""
    b = db.get_or_404(Whiteboard, id)
    since = _parse_int(request.args.get("since")) or 0
    del_since = _parse_int(request.args.get("del_since")) or 0

    q = WhiteboardStroke.query.filter_by(whiteboard_id=b.id, deleted=False)
    if since > 0:
        # zwroc strokes ktore sa nowe LUB zostaly zmienione
        q = q.filter(db.or_(
            WhiteboardStroke.id > since,
            WhiteboardStroke.updated_at > utcnow().replace(second=0, microsecond=0) - timedelta(seconds=2)
        ))
    strokes = q.order_by(WhiteboardStroke.stroke_order, WhiteboardStroke.id).all()

    deletions = WhiteboardDeletion.query.filter(
        WhiteboardDeletion.whiteboard_id == b.id,
        WhiteboardDeletion.id > del_since
    ).order_by(WhiteboardDeletion.id).all()

    # Aktywne kursory (nowsze niz 3 sekundy)
    cutoff = utcnow() - timedelta(seconds=3)
    active_cursors = WhiteboardCursor.query.filter(
        WhiteboardCursor.whiteboard_id == b.id,
        WhiteboardCursor.updated_at > cutoff,
    ).all()
    current_user = get_current_user()
    cursors = [{
        "user_id": c.user_id,
        "name": c.user.name if c.user else "?",
        "initials": c.user.initials if c.user else "?",
        "color": c.user.avatar_color if c.user else "#6c5ce7",
        "x": c.x, "y": c.y,
    } for c in active_cursors if (not current_user or c.user_id != current_user.id)]

    max_stroke_id = db.session.query(db.func.max(WhiteboardStroke.id))\
        .filter_by(whiteboard_id=b.id).scalar() or 0
    max_del_id = db.session.query(db.func.max(WhiteboardDeletion.id))\
        .filter_by(whiteboard_id=b.id).scalar() or 0

    return jsonify({
        "strokes": [_stroke_to_dict(s) for s in strokes],
        "deletions": [d.stroke_id for d in deletions],
        "cursors": cursors,
        "latest_id": max_stroke_id,
        "latest_del_id": max_del_id,
    })


@app.route("/api/tablica/<int:id>/strokes")
def api_whiteboard_strokes_legacy(id):
    """Legacy endpoint - zachowany dla kompatybilnosci (pierwszy load)."""
    b = db.get_or_404(Whiteboard, id)
    strokes = WhiteboardStroke.query.filter_by(whiteboard_id=b.id, deleted=False)\
        .order_by(WhiteboardStroke.stroke_order, WhiteboardStroke.id).all()
    max_id = strokes[-1].id if strokes else 0
    max_del = db.session.query(db.func.max(WhiteboardDeletion.id))\
        .filter_by(whiteboard_id=b.id).scalar() or 0
    return jsonify({
        "strokes": [_stroke_to_dict(s) for s in strokes],
        "latest_id": max_id,
        "latest_del_id": max_del,
    })


@app.route("/api/tablica/<int:id>/stroke/<int:sid>", methods=["PATCH", "POST"])
def api_whiteboard_update_stroke(id, sid):
    """Zaktualizuj stroke - font_size, color, text, points, fill_color, width,
    width_box/height_box, stroke_order (warstwy)."""
    b = db.get_or_404(Whiteboard, id)
    s = WhiteboardStroke.query.filter_by(id=sid, whiteboard_id=b.id, deleted=False).first_or_404()
    data = request.get_json(silent=True) or {}

    if "font_size" in data:
        try:
            fs = float(data["font_size"])
            if 4 <= fs <= 800:
                s.font_size = fs
        except (ValueError, TypeError):
            return jsonify({"error": "invalid font_size"}), 400

    if "width" in data:
        try:
            w = float(data["width"])
            if 0.5 <= w <= 200:
                s.width = w
        except (ValueError, TypeError):
            pass

    if "color" in data:
        s.color = str(data["color"])[:16]
    if "fill_color" in data:
        s.fill_color = str(data["fill_color"])[:16]
    if "text" in data:
        s.text = str(data["text"])[:2000]
    if "width_box" in data:
        try: s.width_box = float(data["width_box"])
        except (ValueError, TypeError): pass
    if "height_box" in data:
        try: s.height_box = float(data["height_box"])
        except (ValueError, TypeError): pass
    if "stroke_order" in data:
        try: s.stroke_order = float(data["stroke_order"])
        except (ValueError, TypeError): pass

    if "points" in data:
        pts = _validate_points(data["points"])
        if pts is None:
            return jsonify({"error": "invalid points"}), 400
        s.points = pts

    s.updated_at = utcnow()
    b.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "stroke": _stroke_to_dict(s)})


@app.route("/api/tablica/<int:id>/stroke/<int:sid>/delete", methods=["POST"])
def api_whiteboard_delete_stroke(id, sid):
    """Usun konkretny stroke (soft delete + propagacja do pollingu)."""
    b = db.get_or_404(Whiteboard, id)
    s = WhiteboardStroke.query.filter_by(id=sid, whiteboard_id=b.id, deleted=False).first_or_404()
    s.deleted = True
    db.session.add(WhiteboardDeletion(whiteboard_id=b.id, stroke_id=s.id))
    b.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "removed_id": sid})


@app.route("/api/tablica/<int:id>/stroke/<int:sid>/layer", methods=["POST"])
def api_whiteboard_layer(id, sid):
    """Warstwy: bring-to-front / send-to-back."""
    b = db.get_or_404(Whiteboard, id)
    s = WhiteboardStroke.query.filter_by(id=sid, whiteboard_id=b.id, deleted=False).first_or_404()
    data = request.get_json(silent=True) or {}
    action = data.get("action")

    if action == "front":
        max_order = db.session.query(db.func.max(WhiteboardStroke.stroke_order))\
            .filter_by(whiteboard_id=b.id).scalar() or 0
        s.stroke_order = max_order + 1.0
    elif action == "back":
        min_order = db.session.query(db.func.min(WhiteboardStroke.stroke_order))\
            .filter_by(whiteboard_id=b.id).scalar() or 0
        s.stroke_order = min_order - 1.0
    else:
        return jsonify({"error": "invalid action"}), 400

    s.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "stroke_order": s.stroke_order})


@app.route("/api/tablica/<int:id>/undo", methods=["POST"])
def api_whiteboard_undo(id):
    """Cofnij ostatni stroke biezacego uzytkownika (soft delete)."""
    b = db.get_or_404(Whiteboard, id)
    user = get_current_user()
    if not user:
        return jsonify({"error": _("brak uzytkownika")}), 401
    last = (WhiteboardStroke.query
            .filter_by(whiteboard_id=b.id, author_user_id=user.id, deleted=False)
            .order_by(WhiteboardStroke.id.desc())
            .first())
    if not last:
        return jsonify({"ok": True, "removed_id": None})
    last.deleted = True
    db.session.add(WhiteboardDeletion(whiteboard_id=b.id, stroke_id=last.id))
    b.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True, "removed_id": last.id})


@app.route("/api/tablica/<int:id>/clear", methods=["POST"])
def api_whiteboard_clear(id):
    """Wyczysc cala tablice."""
    b = db.get_or_404(Whiteboard, id)
    alive = WhiteboardStroke.query.filter_by(whiteboard_id=b.id, deleted=False).all()
    for s in alive:
        s.deleted = True
        db.session.add(WhiteboardDeletion(whiteboard_id=b.id, stroke_id=s.id))
    b.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/tablica/<int:id>/cursor", methods=["POST"])
def api_whiteboard_cursor(id):
    """Aktualizuj pozycje kursora (heartbeat)."""
    db.get_or_404(Whiteboard, id)  # 404 jesli nie ma
    user = get_current_user()
    if not user:
        return jsonify({"ok": False}), 401
    data = request.get_json(silent=True) or {}
    try:
        x, y = float(data.get("x", 0)), float(data.get("y", 0))
    except (ValueError, TypeError):
        return jsonify({"error": "bad coords"}), 400

    cur = WhiteboardCursor.query.filter_by(whiteboard_id=id, user_id=user.id).first()
    if not cur:
        cur = WhiteboardCursor(whiteboard_id=id, user_id=user.id, x=x, y=y)
        db.session.add(cur)
    else:
        cur.x = x
        cur.y = y
        cur.updated_at = utcnow()
    db.session.commit()
    return jsonify({"ok": True})


@app.route("/api/tablica/<int:id>/paste-image", methods=["POST"])
def api_whiteboard_paste_image(id):
    """Wgraj obraz (base64 z clipboardu albo multipart)."""
    b = db.get_or_404(Whiteboard, id)
    user = get_current_user()

    data = request.get_json(silent=True) or {}
    b64 = data.get("image_base64", "")
    if not b64 or "," not in b64:
        return jsonify({"error": "no image"}), 400

    header, encoded = b64.split(",", 1)
    # header: data:image/png;base64
    mime = "image/png"
    if ":" in header and ";" in header:
        mime = header.split(":", 1)[1].split(";", 1)[0]
    ext = "png"
    if "jpeg" in mime or "jpg" in mime: ext = "jpg"
    elif "gif" in mime: ext = "gif"
    elif "webp" in mime: ext = "webp"

    import base64 as _b64
    try:
        img_bytes = _b64.b64decode(encoded)
    except Exception:
        return jsonify({"error": "bad base64"}), 400

    # Limit 8 MB
    if len(img_bytes) > 8 * 1024 * 1024:
        return jsonify({"error": "image too large (max 8MB)"}), 400

    filename = f"{uuid.uuid4().hex}.{ext}"
    target = WHITEBOARD_IMG_DIR / str(b.id)
    target.mkdir(parents=True, exist_ok=True)
    path = target / filename
    with open(path, "wb") as f:
        f.write(img_bytes)

    rel_path = f"{b.id}/{filename}"

    # Domyslne wymiary i pozycja
    try:
        x = float(data.get("x", b.canvas_width / 2 - 200))
        y = float(data.get("y", b.canvas_height / 2 - 150))
        w = float(data.get("width", 400))
        h = float(data.get("height", 300))
    except (ValueError, TypeError):
        x, y, w, h = 100, 100, 400, 300

    max_order = db.session.query(db.func.max(WhiteboardStroke.stroke_order))\
        .filter_by(whiteboard_id=b.id).scalar() or 0.0

    stroke = WhiteboardStroke(
        whiteboard_id=b.id,
        author_user_id=user.id if user else None,
        tool="image",
        image_path=rel_path,
        width_box=w,
        height_box=h,
        stroke_order=max_order + 1.0,
    )
    stroke.points = [[x, y]]
    db.session.add(stroke)
    b.updated_at = utcnow()
    db.session.commit()

    return jsonify({
        "ok": True,
        "stroke": _stroke_to_dict(stroke),
        "url": url_for("whiteboard_image", wid=b.id, filename=filename),
    })


@app.route("/tablica/<int:wid>/img/<filename>")
def whiteboard_image(wid, filename):
    """Serwuj obraz z output/whiteboard_images/<wid>/<filename>."""
    db.get_or_404(Whiteboard, wid)
    safe = secure_filename(filename)
    if not safe or safe != filename:
        abort(404)
    root = (WHITEBOARD_IMG_DIR / str(wid)).resolve()
    path = (root / safe).resolve()
    try:
        path.relative_to(root)
    except ValueError:
        abort(404)
    if not path.is_file():
        abort(404)
    return send_file(path)
