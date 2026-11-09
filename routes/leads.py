"""Lead search in Google Places and CSV export."""

import time

import googlemaps
from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

import i18n
from core import (
    DETAIL_FIELDS,
    _parse_int,
    app,
    get_api_key,
)
from i18n import _
from models import (
    AuditLog,
    ClientCredential,
    Company,
    ContentPost,
    Contract,
    EmailTemplate,
    KnowledgeArticle,
    Note,
    Payment,
    Project,
    Task,
    User,
    db,
)

# ── Search (Google Places) ────────────────────────────────────

@app.route("/search")
def search():
    return render_template("search.html", api_key=get_api_key())


@app.route("/aktywnosci")
def activity_list():
    """Pelna historia aktywnosci (AuditLog) z paginacja."""
    page = max(1, _parse_int(request.args.get("page")) or 1)
    per_page = 100
    user_filter = _parse_int(request.args.get("user_id"))
    table_filter = (request.args.get("table") or "").strip()
    action_filter = (request.args.get("action") or "").strip()

    q = AuditLog.query
    if user_filter:
        q = q.filter(AuditLog.user_id == user_filter)
    if table_filter:
        q = q.filter(AuditLog.table_name == table_filter)
    if action_filter:
        q = q.filter(AuditLog.action == action_filter)

    total = q.count()
    entries = (q.order_by(AuditLog.created_at.desc())
                .offset((page - 1) * per_page)
                .limit(per_page)
                .all())
    total_pages = max(1, (total + per_page - 1) // per_page)

    users = User.query.order_by(User.name).all()
    tables = [t[0] for t in db.session.query(AuditLog.table_name)
              .distinct().order_by(AuditLog.table_name).all() if t[0]]
    actions = [a[0] for a in db.session.query(AuditLog.action)
               .distinct().order_by(AuditLog.action).all() if a[0]]

    return render_template("activity.html",
                           entries=entries, total=total,
                           page=page, total_pages=total_pages,
                           users=users, tables=tables, actions=actions,
                           user_filter=user_filter, table_filter=table_filter,
                           action_filter=action_filter,
                           table_labels=AuditLog.table_labels(), action_labels=AuditLog.action_labels())


@app.route("/szukaj-globalnie")
def global_search():
    """Globalna wyszukiwarka po lokalnej bazie - firmy, zadania, projekty,
    notatki, content, baza wiedzy, platnosci, dostepy, szablony maili, kontrakty."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return render_template("global_search.html", q="", groups=[], total=0)

    like = f"%{q}%"

    companies = Company.query.filter(
        db.or_(
            Company.name.ilike(like),
            Company.address.ilike(like),
            Company.industry.ilike(like),
            Company.contact_person.ilike(like),
            Company.contact_email.ilike(like),
            Company.phone.ilike(like),
            Company.website.ilike(like),
            Company.client_legal_name.ilike(like),
            Company.client_nip.ilike(like),
            Company.main_services.ilike(like),
        )
    ).limit(50).all()

    tasks = Task.query.filter(
        db.or_(Task.title.ilike(like), Task.description.ilike(like))
    ).limit(50).all()

    projects = Project.query.filter(
        db.or_(Project.name.ilike(like), Project.notes.ilike(like),
               Project.domain.ilike(like), Project.hosting.ilike(like))
    ).limit(50).all()

    notes = Note.query.filter(
        db.or_(Note.title.ilike(like), Note.content.ilike(like))
    ).limit(50).all()

    content_posts = ContentPost.query.filter(
        db.or_(ContentPost.title.ilike(like), ContentPost.brief.ilike(like),
               ContentPost._keywords.ilike(like), ContentPost.url.ilike(like),
               ContentPost.writer_name.ilike(like))
    ).limit(50).all()

    kb_articles = KnowledgeArticle.query.filter(
        db.or_(KnowledgeArticle.title.ilike(like), KnowledgeArticle.body.ilike(like),
               KnowledgeArticle.category.ilike(like))
    ).limit(50).all()

    payments = Payment.query.filter(
        db.or_(Payment.title.ilike(like), Payment.description.ilike(like),
               Payment.payment_number.ilike(like),
               Payment.external_invoice_number.ilike(like))
    ).limit(50).all()

    credentials = ClientCredential.query.filter(
        db.or_(ClientCredential.label.ilike(like),
               ClientCredential.login_url.ilike(like),
               ClientCredential.username_hint.ilike(like),
               ClientCredential.notes.ilike(like))
    ).limit(50).all()

    email_tpls = EmailTemplate.query.filter(
        db.or_(EmailTemplate.name.ilike(like), EmailTemplate.key.ilike(like),
               EmailTemplate.subject_template.ilike(like))
    ).limit(20).all()

    contracts = Contract.query.filter(
        db.or_(Contract.name.ilike(like), Contract.content_rendered.ilike(like),
               Contract.notes.ilike(like))
    ).limit(20).all()

    groups = [
        (_("Firmy"), "bi-building", "company_detail", "id", companies),
        (_("Zadania"), "bi-check2-square", "task_detail", "id", tasks),
        (_("Projekty"), "bi-diagram-3", "project_detail", "id", projects),
        (_("Notatki"), "bi-sticky", "note_edit", "id", notes),
        (_("Content"), "bi-file-text", "content_edit", "id", content_posts),
        (_("Baza wiedzy"), "bi-book", "knowledge_detail", "id", kb_articles),
        (_("Platnosci"), "bi-cash-coin", "payment_edit", "id", payments),
        (_("Dostepy klientow"), "bi-safe", None, None, credentials),
        (_("Szablony maili"), "bi-envelope", "email_template_edit", "id", email_tpls),
        (_("Kontrakty"), "bi-file-earmark-text", None, None, contracts),
    ]
    total = sum(len(g[4]) for g in groups)
    return render_template("global_search.html", q=q, groups=groups, total=total)


@app.route("/search/run", methods=["POST"])
def search_run():
    api_key = get_api_key()
    center_lat = request.form.get("center_lat", "").strip()
    center_lng = request.form.get("center_lng", "").strip()
    radius_m = request.form.get("radius_m", "5000").strip()
    keywords_raw = request.form.get("keywords", "").strip()
    max_places_raw = request.form.get("max_places_per_keyword", "").strip()
    min_rating_raw = request.form.get("min_rating", "").strip()
    only_open_now = "only_open_now" in request.form

    errors = []
    if not api_key:
        errors.append(_("Ustaw klucz API w Ustawieniach."))
    if not center_lat or not center_lng:
        errors.append(_("Współrzędne (lat / lng) są wymagane."))
    if not keywords_raw:
        errors.append(_("Podaj co najmniej jedno słowo kluczowe."))
    if errors:
        for e in errors:
            flash(e, "danger")
        return redirect(url_for("search"))

    try:
        lat, lng = float(center_lat), float(center_lng)
    except ValueError:
        flash(_("Współrzędne muszą być liczbami."), "danger")
        return redirect(url_for("search"))

    radius = int(radius_m) if radius_m.isdigit() else 5000
    keywords = [kw.strip() for kw in keywords_raw.splitlines() if kw.strip()]
    max_places = int(max_places_raw) if max_places_raw else None
    min_rating = float(min_rating_raw) if min_rating_raw else None

    try:
        gmaps = googlemaps.Client(key=api_key)
    except Exception as exc:
        flash(_("Błąd klienta Google Maps: %(error)s", error=exc), "danger")
        return redirect(url_for("search"))

    seen_ids = set()
    nearby = []
    for keyword in keywords:
        collected = 0
        try:
            response = gmaps.places_nearby(
                location=(lat, lng), radius=radius, keyword=keyword, language=i18n.DEFAULT_LANGUAGE,
            )
        except Exception as exc:
            flash(_("Błąd Nearby Search [%(keyword)s]: %(error)s", keyword=keyword, error=exc), "warning")
            continue

        while True:
            for place in response.get("results", []):
                pid = place.get("place_id")
                if not pid or pid in seen_ids:
                    continue
                seen_ids.add(pid)
                nearby.append({"place_id": pid, "source_keyword": keyword})
                collected += 1
                if max_places and collected >= max_places:
                    break
            if max_places and collected >= max_places:
                break
            next_token = response.get("next_page_token")
            if not next_token:
                break
            time.sleep(2)
            try:
                response = gmaps.places_nearby(
                    location=(lat, lng), radius=radius, keyword=keyword,
                    page_token=next_token, language=i18n.DEFAULT_LANGUAGE,
                )
            except Exception:
                break

    total_found = len(nearby)
    places = []
    for item in nearby:
        pid = item["place_id"]
        try:
            detail = gmaps.place(place_id=pid, fields=DETAIL_FIELDS, language=i18n.DEFAULT_LANGUAGE)
        except Exception:
            continue
        r = detail.get("result", {})
        if r.get("website"):
            continue
        rating = r.get("rating")
        if min_rating and (rating is None or rating < min_rating):
            continue
        oh = r.get("opening_hours")
        open_now = oh.get("open_now") if isinstance(oh, dict) else None
        if only_open_now and open_now is not True:
            continue

        geo = r.get("geometry", {}).get("location", {})
        types_list = r.get("types", [])
        places.append({
            "place_id": pid,
            "name": r.get("name", ""),
            "address": r.get("formatted_address", ""),
            "phone": r.get("formatted_phone_number", ""),
            "intl_phone": r.get("international_phone_number", ""),
            "lat": geo.get("lat"),
            "lng": geo.get("lng"),
            "rating": rating,
            "user_ratings_total": r.get("user_ratings_total"),
            "business_status": r.get("business_status", ""),
            "primary_type": types_list[0] if types_list else "",
            "google_maps_url": r.get("url", ""),
            "open_now": open_now,
            "source_keyword": item["source_keyword"],
        })

    existing_pids = set()
    if places:
        pids = [p["place_id"] for p in places]
        existing = Company.query.filter(Company.place_id.in_(pids)).all()
        existing_pids = {c.place_id for c in existing}

    return render_template(
        "results.html",
        places=places, total_found=total_found, keywords=keywords,
        existing_pids=existing_pids,
    )


@app.route("/api/add_to_hub", methods=["POST"])
def api_add_to_hub():
    data = request.get_json()
    place_id = data.get("place_id")

    if Company.query.filter_by(place_id=place_id).first():
        return jsonify({"ok": True, "msg": _("Firma już jest w hubie")})

    c = Company(
        place_id=place_id,
        name=data.get("name", ""),
        address=data.get("address", ""),
        phone=data.get("phone", ""),
        intl_phone=data.get("intl_phone", ""),
        lat=data.get("lat"),
        lng=data.get("lng"),
        rating=data.get("rating"),
        user_ratings_total=data.get("user_ratings_total"),
        business_status=data.get("business_status", ""),
        primary_type=data.get("primary_type", ""),
        google_maps_url=data.get("google_maps_url", ""),
        pipeline_stage="lead",
    )
    c.ensure_portal_token()
    db.session.add(c)
    db.session.commit()
    return jsonify({"ok": True, "id": c.id, "msg": _("Dodano do huba")})
