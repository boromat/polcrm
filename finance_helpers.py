"""Financial calculations: balance, overhead allocation, retainer generation."""

from calendar import monthrange
from datetime import date
from collections import defaultdict

import i18n
from models import (
    db, Company, Payment, Expense, Subscription, Settings,
)


# Polish month names (kept for callers like scripts/seed_test_data.py); the UI uses i18n.month_name()
PL_MONTHS = i18n.MONTHS_NOMINATIVE["pl"]


def retainer_title(month, year, company_name, lang=None):
    """Title of a generated retainer payment - a document for the client, so it is written in
    DEFAULT_LANGUAGE (not the language of whoever clicked): "Abonament Marzec 2026 - Firma"."""
    lang = lang or i18n.DEFAULT_LANGUAGE
    return i18n.gettext("Abonament %(month)s %(year)s - %(company)s", lang) % {
        "month": i18n.month_name(month, lang), "year": year, "company": company_name,
    }


def next_payment_number():
    """Generate P-YYYY-NNNN where NNNN is next index for current year."""
    year = date.today().year
    prefix = f"P-{year}-"
    last = (
        Payment.query
        .filter(Payment.payment_number.like(f"{prefix}%"))
        .order_by(Payment.payment_number.desc())
        .first()
    )
    if last and last.payment_number:
        try:
            n = int(last.payment_number.split("-")[-1]) + 1
        except ValueError:
            n = 1
    else:
        n = 1
    return f"{prefix}{n:04d}"


def month_bounds(year, month):
    start = date(year, month, 1)
    end = date(year, month, monthrange(year, month)[1])
    return start, end


def generate_monthly_retainers(year=None, month=None):
    """Create unpaid Payment rows for all retainer clients for given month.

    Idempotent: if a retainer payment already exists for (company, month, year, kind='retainer'),
    it is skipped. Returns count of newly created payments.
    """
    today = date.today()
    year = year or today.year
    month = month or today.month

    # Stawka z Ustawień (Finanse i dane prawne), a nie na sztywno 23% - np. 0 dla zwolnionych z VAT.
    settings = Settings.get()
    if settings.company_vat_payer is False:
        vat_rate = 0.0  # agencja zwolniona z VAT
    else:
        vat_rate = settings.default_vat_rate if settings.default_vat_rate is not None else 23.0

    created = 0
    for company in Company.query.filter_by(is_retainer=True).all():
        if not company.monthly_fee_net or company.monthly_fee_net <= 0:
            continue
        existing = Payment.query.filter_by(
            company_id=company.id, period_month=month, period_year=year, kind="retainer"
        ).first()
        if existing:
            continue

        day = max(1, min(company.billing_day or 1, monthrange(year, month)[1]))
        due = date(year, month, day)
        title = retainer_title(month, year, company.name)
        p = Payment(
            company_id=company.id,
            payment_number=next_payment_number(),
            title=title,
            amount_net=company.monthly_fee_net,
            vat_rate=vat_rate,
            kind="retainer",
            status="unpaid",
            period_month=month,
            period_year=year,
            issued_at=date(year, month, 1),
            due_at=due,
        )
        p.recompute_gross()
        db.session.add(p)
        created += 1

    if created:
        db.session.commit()
    return created


def mark_overdue_payments():
    """Flip status unpaid→overdue for past-due payments. Idempotent."""
    today = date.today()
    count = 0
    stale = Payment.query.filter(
        Payment.status == "unpaid",
        Payment.due_at != None,
        Payment.due_at < today,
    ).all()
    for p in stale:
        p.status = "overdue"
        count += 1
    if count:
        db.session.commit()
    return count


def monthly_balance(year, month, allocate_overhead=True):
    """
    Compute: revenue (paid payments), expenses (in month), subscription allocation,
    per-client breakdown.
    """
    start, end = month_bounds(year, month)

    # Revenue: paid payments with paid_at in month
    revenues = Payment.query.filter(
        Payment.status == "paid",
        Payment.paid_at != None,
        Payment.paid_at >= start,
        Payment.paid_at <= end,
    ).all()
    revenue_total = sum(p.amount_net or 0 for p in revenues)

    # Expenses with payment_date in month
    expenses = Expense.query.filter(
        Expense.payment_date >= start,
        Expense.payment_date <= end,
    ).all()
    expense_total = sum(e.amount_net or 0 for e in expenses)

    # Subscription allocation (amortized per month)
    sub_alloc_total = sum(s.monthly_allocation for s in Subscription.query.filter_by(is_active=True).all())

    # Per-client revenue
    revenue_by_client = defaultdict(float)
    for p in revenues:
        revenue_by_client[p.company_id] += (p.amount_net or 0)

    # Per-client direct expenses
    direct_expense_by_client = defaultdict(float)
    unassigned_expenses = 0.0
    for e in expenses:
        if e.client_id:
            direct_expense_by_client[e.client_id] += (e.amount_net or 0)
        else:
            unassigned_expenses += (e.amount_net or 0)

    # Allocate unassigned expenses + subscriptions as overhead, proportional to revenue
    overhead_pool = unassigned_expenses + sub_alloc_total
    per_client = []
    for company in Company.query.order_by(Company.name).all():
        rev = revenue_by_client.get(company.id, 0)
        direct = direct_expense_by_client.get(company.id, 0)
        overhead_share = 0.0
        if allocate_overhead and overhead_pool > 0 and revenue_total > 0 and rev > 0:
            overhead_share = overhead_pool * (rev / revenue_total)
        total_cost = direct + overhead_share
        margin = rev - total_cost
        if rev > 0 or direct > 0:
            per_client.append({
                "company": company,
                "revenue": round(rev, 2),
                "direct_expenses": round(direct, 2),
                "overhead_share": round(overhead_share, 2),
                "total_cost": round(total_cost, 2),
                "margin": round(margin, 2),
                "margin_pct": round((margin / rev * 100) if rev else 0, 1),
            })

    balance = revenue_total - expense_total - sub_alloc_total

    return {
        "year": year,
        "month": month,
        "month_label": i18n.month_name(month),  # follows the UI language
        "revenue_total": round(revenue_total, 2),
        "expense_total": round(expense_total, 2),
        "subscription_allocation": round(sub_alloc_total, 2),
        "unassigned_expenses": round(unassigned_expenses, 2),
        "balance": round(balance, 2),
        "per_client": per_client,
        "revenues": revenues,
        "expenses": expenses,
    }


def overdue_payments_summary():
    """Return count and total amount of overdue payments."""
    overdue = Payment.query.filter_by(status="overdue").all()
    return {
        "count": len(overdue),
        "total_gross": sum(p.amount_gross or 0 for p in overdue),
        "payments": overdue,
    }


def expense_category_breakdown(year, month):
    """Sum expenses by category in month."""
    start, end = month_bounds(year, month)
    rows = Expense.query.filter(
        Expense.payment_date >= start,
        Expense.payment_date <= end,
    ).all()
    buckets = defaultdict(float)
    for e in rows:
        buckets[e.category] += (e.amount_net or 0)
    return dict(buckets)
