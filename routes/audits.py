"""Website audits, PageSpeed scoring, PDF reports and competitors."""

from flask import (
    flash,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    url_for,
)

import i18n
from core import (
    app,
    get_api_key,
    get_gmaps,
)
from i18n import _
from models import (
    Audit,
    Company,
    Competitor,
    Settings,
    db,
)
from scoring import calculate_all_scores, score_competitor

# ── Audits ────────────────────────────────────────────────────

@app.route("/audits")
def audits_list():
    audits = Audit.query.join(Company).order_by(Audit.created_at.desc()).all()
    return render_template("audit/list.html", audits=audits)


@app.route("/audits/new/<int:company_id>", methods=["GET", "POST"])
def audit_new(company_id):
    company = db.get_or_404(Company, company_id)

    if request.method == "POST":
        audit = Audit(company_id=company_id, status="draft")
        api_key = get_api_key()
        scores = calculate_all_scores(company, api_key)
        audit.score_visibility = scores["visibility"]
        audit.score_offer = scores["offer"]
        audit.score_trust = scores["trust"]
        audit.score_conversion = scores["conversion"]
        audit.score_analytics = scores["analytics"]
        audit.score_overall = scores["overall"]

        ps = scores.get("pagespeed", {})
        audit.pagespeed_mobile = ps.get("mobile_score")
        audit.pagespeed_desktop = ps.get("desktop_score")
        audit.pagespeed_data = ps

        audit.section_context = {
            "auto_data": {
                "name": company.name, "address": company.address,
                "industry": company.industry, "category": company.primary_type,
                "rating": company.rating, "status": company.business_status,
            },
            "notes": "",
        }

        if company.website:
            audit.section_website = {
                "auto_data": {
                    "pagespeed_mobile": ps.get("mobile_score"),
                    "pagespeed_desktop": ps.get("desktop_score"),
                    "fcp": ps.get("fcp", ""), "lcp": ps.get("lcp", ""), "cls": ps.get("cls", ""),
                },
                "checklist": {
                    "mobile_responsive": False, "clear_offer": False, "visible_cta": False,
                    "contact_form": False, "trust_elements": False, "fast_loading": False,
                },
                "notes": "",
            }
        else:
            audit.section_website = {
                "auto_data": {"info": _("Firma nie posiada strony internetowej")},
                "checklist": {},
                "notes": _("Brak strony www - kluczowa rekomendacja do wdrożenia."),
            }

        audit.section_seo = {
            "checklist": {
                "keywords_in_title": False, "keywords_in_headings": False,
                "keywords_in_content": False, "subpages_per_service": False,
                "subpages_per_location": False, "internal_linking": False,
                "meta_with_location": False, "schema_local_business": False,
                "https_active": False, "mobile_friendly": False,
            },
            "notes": "" if company.website else _("Brak strony - SEO nie dotyczy."),
        }

        audit.section_gbp = {
            "auto_data": {
                "has_profile": bool(company.place_id), "rating": company.rating,
                "reviews_count": company.user_ratings_total, "phone": company.phone,
                "address": company.address, "business_status": company.business_status,
            },
            "checklist": {
                "complete_data": False, "correct_categories": False, "current_hours": False,
                "photos_added": False, "posts_published": False, "reviews_responded": False,
                "qa_responded": False, "nap_consistent": False,
            },
            "notes": "",
        }

        audit.section_directories = {
            "checklist": {
                "panorama_firm": False, "pkt_pl": False, "yelp": False,
                "industry_directories": False, "nap_directories_consistent": False,
                "nap_google_consistent": False,
            },
            "notes": "",
        }

        audit.section_competition = {"competitors": [], "notes": ""}
        audit.section_plan90 = {"actions": [], "notes": ""}
        audit.top_problems = []
        audit.top_opportunities = []
        audit.recommended_actions = []

        db.session.add(audit)
        if company.pipeline_stage == "lead":
            company.pipeline_stage = "audit"
        db.session.commit()
        flash(_("Utworzono audyt z auto-scoringiem."), "success")
        return redirect(url_for("audit_edit", id=audit.id))

    return render_template("audit/form.html", company=company, audit=None)


@app.route("/audits/<int:id>/edit", methods=["GET", "POST"])
def audit_edit(id):
    audit = db.get_or_404(Audit, id)
    company = audit.company

    if request.method == "POST":
        form = request.form
        seo = audit.section_seo or {}
        seo_cl = seo.get("checklist", {})
        for key in seo_cl:
            seo_cl[key] = f"seo_{key}" in form
        seo["checklist"] = seo_cl
        seo["notes"] = form.get("seo_notes", "")
        audit.section_seo = seo

        ws = audit.section_website or {}
        ws_cl = ws.get("checklist", {})
        for key in ws_cl:
            ws_cl[key] = f"ws_{key}" in form
        ws["checklist"] = ws_cl
        ws["notes"] = form.get("ws_notes", "")
        audit.section_website = ws

        gbp = audit.section_gbp or {}
        gbp_cl = gbp.get("checklist", {})
        for key in gbp_cl:
            gbp_cl[key] = f"gbp_{key}" in form
        gbp["checklist"] = gbp_cl
        gbp["notes"] = form.get("gbp_notes", "")
        audit.section_gbp = gbp

        dirs = audit.section_directories or {}
        dirs_cl = dirs.get("checklist", {})
        for key in dirs_cl:
            dirs_cl[key] = f"dir_{key}" in form
        dirs["checklist"] = dirs_cl
        dirs["notes"] = form.get("dir_notes", "")
        audit.section_directories = dirs

        actions = []
        for i in range(1, 4):
            a = form.get(f"action_{i}", "").strip()
            if a:
                actions.append(a)
        plan = audit.section_plan90 or {}
        plan["actions"] = actions
        plan["notes"] = form.get("plan_notes", "")
        audit.section_plan90 = plan

        problems = [form.get(f"problem_{i}", "").strip() for i in range(1, 4)]
        audit.top_problems = [p for p in problems if p]
        opps = [form.get(f"opportunity_{i}", "").strip() for i in range(1, 4)]
        audit.top_opportunities = [o for o in opps if o]
        recs = [form.get(f"recommendation_{i}", "").strip() for i in range(1, 4)]
        audit.recommended_actions = [r for r in recs if r]

        ctx = audit.section_context or {}
        ctx["notes"] = form.get("context_notes", "")
        audit.section_context = ctx
        audit.status = form.get("status", audit.status)
        audit.compute_overall()
        db.session.commit()
        flash(_("Audyt zapisany."), "success")
        return redirect(url_for("audit_edit", id=audit.id))

    competitors = Competitor.query.filter_by(audit_id=audit.id).all()
    return render_template(
        "audit/form.html", audit=audit, company=company,
        competitors=competitors, api_key=get_api_key(),
    )


@app.route("/audits/<int:id>/report")
def audit_report(id):
    audit = db.get_or_404(Audit, id)
    company = audit.company
    competitors = Competitor.query.filter_by(audit_id=audit.id).all()
    s = Settings.get()
    return render_template(
        "audit/report.html", audit=audit, company=company,
        competitors=competitors, settings=s,
    )


@app.route("/audits/<int:id>/pdf")
def audit_pdf(id):
    from pdf_report import generate_audit_pdf
    audit = db.get_or_404(Audit, id)
    company = audit.company
    competitors = Competitor.query.filter_by(audit_id=audit.id).all()
    s = Settings.get()
    pdf_path = generate_audit_pdf(audit, company, competitors, s)
    return send_file(pdf_path, mimetype="application/pdf", as_attachment=True,
                     download_name=_("audyt_%(name)s.pdf", name=company.name.replace(" ", "_")))


# ── Competitor API ────────────────────────────────────────────

@app.route("/api/search_competitor", methods=["POST"])
def api_search_competitor():
    data = request.get_json()
    keyword = data.get("keyword", "")
    lat = data.get("lat")
    lng = data.get("lng")

    gmaps = get_gmaps()
    if not gmaps:
        return jsonify({"error": _("Brak klucza API")}), 400

    try:
        resp = gmaps.places_nearby(
            location=(lat, lng), radius=5000, keyword=keyword, language=i18n.DEFAULT_LANGUAGE,
        )
        results = []
        for p in resp.get("results", [])[:10]:
            results.append({
                "place_id": p.get("place_id"), "name": p.get("name"),
                "address": p.get("vicinity", ""), "rating": p.get("rating"),
                "user_ratings_total": p.get("user_ratings_total"),
            })
        return jsonify({"results": results})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 500


@app.route("/api/add_competitor", methods=["POST"])
def api_add_competitor():
    data = request.get_json()
    audit_id = data.get("audit_id")
    audit = db.session.get(Audit, audit_id)
    if not audit:
        return jsonify({"error": "Audit not found"}), 404

    gmaps = get_gmaps()
    place_id = data.get("place_id")
    website = ""
    if gmaps and place_id:
        try:
            detail = gmaps.place(place_id=place_id, fields=["website"], language=i18n.DEFAULT_LANGUAGE)
            website = detail.get("result", {}).get("website", "")
        except Exception:
            pass

    comp = Competitor(
        audit_id=audit_id, name=data.get("name", ""), place_id=place_id or "",
        address=data.get("address", ""), website=website,
        rating=data.get("rating"), user_ratings_total=data.get("user_ratings_total"),
    )
    vis, trust = score_competitor(comp)
    comp.score_visibility = vis
    comp.score_trust = trust
    db.session.add(comp)
    db.session.commit()
    return jsonify({
        "ok": True, "id": comp.id, "website": website,
        "score_visibility": vis, "score_trust": trust,
    })


@app.route("/api/delete_competitor/<int:id>", methods=["POST"])
def api_delete_competitor(id):
    comp = db.get_or_404(Competitor, id)
    db.session.delete(comp)
    db.session.commit()
    return jsonify({"ok": True})
