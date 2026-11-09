"""Finances: payments, expenses, subscriptions, reports."""

from datetime import date

from flask import (
    flash,
    redirect,
    render_template,
    request,
    url_for,
)

import finance_helpers
import i18n
from core import (
    _parse_date,
    _parse_float,
    _parse_int,
    _safe_referrer,
    _vat_rate,
    app,
)
from models import (
    BILLING_CYCLES,
    EXPENSE_CATEGORIES,
    PAYMENT_KINDS,
    PAYMENT_STATUSES,
    Company,
    Expense,
    Payment,
    Subscription,
    db,
)
from i18n import _

# ═══════════════════════════════════════════════════════════════
#  FINANSE
# ═══════════════════════════════════════════════════════════════

@app.route("/finances")
def finances_index():
    today = date.today()
    bal = finance_helpers.monthly_balance(today.year, today.month)
    overdue = finance_helpers.overdue_payments_summary()
    cat_breakdown = finance_helpers.expense_category_breakdown(today.year, today.month)

    # Trend 6 ostatnich miesiecy (dla Chart.js)
    trend = []
    for i in range(5, -1, -1):
        y = today.year
        m = today.month - i
        while m <= 0:
            m += 12
            y -= 1
        b = finance_helpers.monthly_balance(y, m, allocate_overhead=False)
        trend.append({
            "label": f"{i18n.month_name(m)[:3]} {str(y)[-2:]}",
            "revenue": b["revenue_total"],
            "expense": b["expense_total"] + b["subscription_allocation"],
            "balance": b["balance"],
        })

    return render_template("finances/index.html", balance=bal, overdue=overdue,
                           category_breakdown=cat_breakdown, trend=trend)


# -- Payments --

@app.route("/finances/payments")
def finances_payments():
    status = request.args.get("status", "")
    company_id = _parse_int(request.args.get("company_id"))
    q = Payment.query
    if status in PAYMENT_STATUSES:
        q = q.filter_by(status=status)
    if company_id:
        q = q.filter_by(company_id=company_id)
    payments = q.order_by(Payment.issued_at.desc()).all()
    companies = Company.query.order_by(Company.name).all()
    return render_template("finances/payments_list.html", payments=payments,
                           companies=companies, status=status, selected_company_id=company_id,
                           statuses=PAYMENT_STATUSES, kinds=PAYMENT_KINDS)


@app.route("/finances/payments/new", methods=["GET", "POST"])
def payment_new():
    if request.method == "POST":
        p = Payment(
            company_id=int(request.form.get("company_id")),
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            amount_net=_parse_float(request.form.get("amount_net")) or 0,
            vat_rate=_vat_rate(request.form.get("vat_rate")),
            kind=request.form.get("kind", "one_time"),
            status=request.form.get("status", "unpaid"),
            period_month=_parse_int(request.form.get("period_month")),
            period_year=_parse_int(request.form.get("period_year")),
            issued_at=_parse_date(request.form.get("issued_at")) or date.today(),
            due_at=_parse_date(request.form.get("due_at")),
            paid_at=_parse_date(request.form.get("paid_at")),
            external_invoice_number=request.form.get("external_invoice_number", "").strip(),
        )
        p.payment_number = finance_helpers.next_payment_number()
        p.recompute_gross()
        db.session.add(p)
        db.session.commit()
        flash(_("Dodano płatność %(number)s.", number=p.payment_number), "success")
        return redirect(url_for("finances_payments"))
    companies = Company.query.order_by(Company.name).all()
    return render_template("finances/payment_form.html", payment=None, companies=companies,
                           kinds=PAYMENT_KINDS, statuses=PAYMENT_STATUSES,
                           preset_company_id=_parse_int(request.args.get("company_id")))


@app.route("/finances/payments/<int:id>/edit", methods=["GET", "POST"])
def payment_edit(id):
    p = db.get_or_404(Payment, id)
    if request.method == "POST":
        p.company_id = int(request.form.get("company_id"))
        p.title = request.form.get("title", "").strip()
        p.description = request.form.get("description", "").strip()
        p.amount_net = _parse_float(request.form.get("amount_net")) or 0
        p.vat_rate = _vat_rate(request.form.get("vat_rate"))
        p.kind = request.form.get("kind", p.kind)
        p.status = request.form.get("status", p.status)
        p.period_month = _parse_int(request.form.get("period_month"))
        p.period_year = _parse_int(request.form.get("period_year"))
        p.issued_at = _parse_date(request.form.get("issued_at")) or p.issued_at
        p.due_at = _parse_date(request.form.get("due_at"))
        p.paid_at = _parse_date(request.form.get("paid_at"))
        p.external_invoice_number = request.form.get("external_invoice_number", "").strip()
        p.recompute_gross()
        db.session.commit()
        flash(_("Zapisano płatność %(number)s.", number=p.payment_number), "success")
        return redirect(url_for("finances_payments"))
    companies = Company.query.order_by(Company.name).all()
    return render_template("finances/payment_form.html", payment=p, companies=companies,
                           kinds=PAYMENT_KINDS, statuses=PAYMENT_STATUSES,
                           preset_company_id=p.company_id)


@app.route("/finances/payments/<int:id>/mark-paid", methods=["POST"])
def payment_mark_paid(id):
    p = db.get_or_404(Payment, id)
    p.status = "paid"
    p.paid_at = _parse_date(request.form.get("paid_at", "")) or date.today()
    db.session.commit()
    flash(_("Płatność %(number)s oznaczona jako opłacona.", number=p.payment_number), "success")
    return redirect(_safe_referrer(url_for("finances_payments")))


@app.route("/finances/payments/<int:id>/delete", methods=["POST"])
def payment_delete(id):
    p = db.get_or_404(Payment, id)
    num = p.payment_number
    db.session.delete(p)
    db.session.commit()
    flash(_("Usunięto płatność %(number)s.", number=num), "success")
    return redirect(url_for("finances_payments"))


@app.route("/finances/payments/generate-retainers", methods=["POST"])
def payments_generate_retainers():
    year = _parse_int(request.form.get("year")) or date.today().year
    month = _parse_int(request.form.get("month")) or date.today().month
    count = finance_helpers.generate_monthly_retainers(year, month)
    if count:
        flash(_("Wygenerowano %(count)s płatności abonamentowych dla %(period)s.", count=count,
                period=f"{year}-{month:02d}"), "success")
    else:
        flash(_("Brak nowych abonamentów do wygenerowania (już są lub nie ma klientów retainer)."), "info")
    return redirect(url_for("finances_payments"))


# -- Expenses --

@app.route("/finances/expenses")
def finances_expenses():
    category = request.args.get("category", "")
    q = Expense.query
    if category in EXPENSE_CATEGORIES:
        q = q.filter_by(category=category)
    expenses = q.order_by(Expense.payment_date.desc()).all()
    return render_template("finances/expenses_list.html", expenses=expenses,
                           category=category, categories=EXPENSE_CATEGORIES)


@app.route("/finances/expenses/new", methods=["GET", "POST"])
def expense_new():
    if request.method == "POST":
        e = Expense(
            category=request.form.get("category", "seo_tools"),
            subcategory=request.form.get("subcategory", "").strip(),
            title=request.form.get("title", "").strip(),
            description=request.form.get("description", "").strip(),
            vendor=request.form.get("vendor", "").strip(),
            amount_net=_parse_float(request.form.get("amount_net")) or 0,
            vat_rate=_vat_rate(request.form.get("vat_rate")),
            payment_date=_parse_date(request.form.get("payment_date")) or date.today(),
            subscription_id=_parse_int(request.form.get("subscription_id")),
            client_id=_parse_int(request.form.get("client_id")),
        )
        e.recompute_gross()
        db.session.add(e)
        db.session.commit()
        flash(_("Dodano koszt."), "success")
        return redirect(url_for("finances_expenses"))
    companies = Company.query.order_by(Company.name).all()
    subscriptions = Subscription.query.order_by(Subscription.name).all()
    return render_template("finances/expense_form.html", expense=None, companies=companies,
                           subscriptions=subscriptions, categories=EXPENSE_CATEGORIES)


@app.route("/finances/expenses/<int:id>/edit", methods=["GET", "POST"])
def expense_edit(id):
    e = db.get_or_404(Expense, id)
    if request.method == "POST":
        e.category = request.form.get("category", e.category)
        e.subcategory = request.form.get("subcategory", "").strip()
        e.title = request.form.get("title", "").strip()
        e.description = request.form.get("description", "").strip()
        e.vendor = request.form.get("vendor", "").strip()
        e.amount_net = _parse_float(request.form.get("amount_net")) or 0
        e.vat_rate = _vat_rate(request.form.get("vat_rate"))
        e.payment_date = _parse_date(request.form.get("payment_date")) or e.payment_date
        e.subscription_id = _parse_int(request.form.get("subscription_id"))
        e.client_id = _parse_int(request.form.get("client_id"))
        e.recompute_gross()
        db.session.commit()
        flash(_("Zapisano koszt."), "success")
        return redirect(url_for("finances_expenses"))
    companies = Company.query.order_by(Company.name).all()
    subscriptions = Subscription.query.order_by(Subscription.name).all()
    return render_template("finances/expense_form.html", expense=e, companies=companies,
                           subscriptions=subscriptions, categories=EXPENSE_CATEGORIES)


@app.route("/finances/expenses/<int:id>/delete", methods=["POST"])
def expense_delete(id):
    e = db.get_or_404(Expense, id)
    db.session.delete(e)
    db.session.commit()
    flash(_("Usunięto koszt."), "success")
    return redirect(url_for("finances_expenses"))


# -- Subscriptions --

@app.route("/finances/subscriptions")
def finances_subscriptions():
    subs = Subscription.query.order_by(Subscription.is_active.desc(), Subscription.name).all()
    return render_template("finances/subscriptions_list.html", subscriptions=subs)


@app.route("/finances/subscriptions/new", methods=["GET", "POST"])
def subscription_new():
    if request.method == "POST":
        sub = Subscription(
            name=request.form.get("name", "").strip(),
            vendor=request.form.get("vendor", "").strip(),
            amount_net=_parse_float(request.form.get("amount_net")) or 0,
            vat_rate=_vat_rate(request.form.get("vat_rate")),
            billing_cycle=request.form.get("billing_cycle", "monthly"),
            renewal_date=_parse_date(request.form.get("renewal_date")),
            category=request.form.get("category", "seo_tools"),
            is_active="is_active" in request.form,
            notes=request.form.get("notes", "").strip(),
        )
        db.session.add(sub)
        db.session.commit()
        flash(_("Dodano subskrypcję %(name)s.", name=sub.name), "success")
        return redirect(url_for("finances_subscriptions"))
    return render_template("finances/subscription_form.html", subscription=None,
                           cycles=BILLING_CYCLES, categories=EXPENSE_CATEGORIES)


@app.route("/finances/subscriptions/<int:id>/edit", methods=["GET", "POST"])
def subscription_edit(id):
    sub = db.get_or_404(Subscription, id)
    if request.method == "POST":
        sub.name = request.form.get("name", sub.name).strip()
        sub.vendor = request.form.get("vendor", "").strip()
        sub.amount_net = _parse_float(request.form.get("amount_net")) or 0
        sub.vat_rate = _vat_rate(request.form.get("vat_rate"))
        sub.billing_cycle = request.form.get("billing_cycle", sub.billing_cycle)
        sub.renewal_date = _parse_date(request.form.get("renewal_date"))
        sub.category = request.form.get("category", sub.category)
        sub.is_active = "is_active" in request.form
        sub.notes = request.form.get("notes", "").strip()
        db.session.commit()
        flash(_("Subskrypcja zapisana."), "success")
        return redirect(url_for("finances_subscriptions"))
    return render_template("finances/subscription_form.html", subscription=sub,
                           cycles=BILLING_CYCLES, categories=EXPENSE_CATEGORIES)


@app.route("/finances/subscriptions/<int:id>/delete", methods=["POST"])
def subscription_delete(id):
    sub = db.get_or_404(Subscription, id)
    db.session.delete(sub)
    db.session.commit()
    flash(_("Usunięto subskrypcję."), "success")
    return redirect(url_for("finances_subscriptions"))


# -- Internal Report --

@app.route("/finances/report/internal")
def finances_report_internal():
    today = date.today()
    year = _parse_int(request.args.get("year")) or today.year
    month = _parse_int(request.args.get("month")) or today.month
    allocate = request.args.get("allocate_overhead", "1") == "1"
    balance = finance_helpers.monthly_balance(year, month, allocate_overhead=allocate)
    return render_template("finances/report_internal.html", balance=balance, allocate=allocate,
                           year=year, month=month)
