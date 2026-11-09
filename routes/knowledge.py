"""Knowledge base / SOPs."""

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

from core import (
    _render_markdown,
    app,
)
from i18n import _
from models import KnowledgeArticle, db

# ═══════════════════════════════════════════════════════════════
#  BAZA WIEDZY / SOP
# ═══════════════════════════════════════════════════════════════

@app.route("/knowledge")
def knowledge_list():
    category = request.args.get("category", "")
    q = KnowledgeArticle.query
    if category:
        q = q.filter_by(category=category)
    articles = q.order_by(KnowledgeArticle.pinned.desc(), KnowledgeArticle.category, KnowledgeArticle.title).all()
    categories = [c[0] for c in db.session.query(KnowledgeArticle.category).distinct().all()]
    return render_template("knowledge/list.html", articles=articles, category=category, categories=categories)


@app.route("/knowledge/<int:id>")
def knowledge_detail(id):
    a = db.get_or_404(KnowledgeArticle, id)
    # Ta sama sanityzacja (bleach) co w notatkach - szablon wstawia wynik przez |safe.
    html_body = _render_markdown(a.body or "", mentions=False)
    return render_template("knowledge/detail.html", article=a, html_body=html_body)


@app.route("/knowledge/new", methods=["GET", "POST"])
def knowledge_new():
    if request.method == "POST":
        tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
        a = KnowledgeArticle(
            title=request.form.get("title", "").strip(),
            category=request.form.get("category", "Ogólne").strip() or "Ogólne",
            body=request.form.get("body", "").strip(),
            pinned="pinned" in request.form,
        )
        a.tags = tags
        if not a.title:
            flash(_("Tytuł jest wymagany."), "danger")
            return redirect(url_for("knowledge_new"))
        db.session.add(a)
        db.session.commit()
        flash(_("Artykuł dodany."), "success")
        return redirect(url_for("knowledge_detail", id=a.id))
    return render_template("knowledge/form.html", article=None)


@app.route("/knowledge/<int:id>/edit", methods=["GET", "POST"])
def knowledge_edit(id):
    a = db.get_or_404(KnowledgeArticle, id)
    if request.method == "POST":
        tags = [t.strip() for t in request.form.get("tags", "").split(",") if t.strip()]
        a.title = request.form.get("title", a.title).strip()
        a.category = request.form.get("category", a.category).strip()
        a.body = request.form.get("body", "").strip()
        a.pinned = "pinned" in request.form
        a.tags = tags
        db.session.commit()
        flash(_("Artykuł zapisany."), "success")
        return redirect(url_for("knowledge_detail", id=a.id))
    return render_template("knowledge/form.html", article=a)


@app.route("/knowledge/<int:id>/delete", methods=["POST"])
def knowledge_delete(id):
    a = db.get_or_404(KnowledgeArticle, id)
    db.session.delete(a)
    db.session.commit()
    flash(_("Artykuł usunięty."), "success")
    return redirect(url_for("knowledge_list"))
