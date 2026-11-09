"""Unit tests for the finance helpers and the audit scoring engine (no network, no API keys)."""

from datetime import date, timedelta

import finance_helpers as fh
import scoring


# ── scoring ─────────────────────────────────────────────────────

def _company(**kw):
    from models import Company

    return Company(name="Firma", **kw)


def test_scores_stay_in_range_for_an_empty_company(seeded):
    with seeded.app_context():
        scores = scoring.calculate_all_scores(_company(), api_key=None)  # no API key -> no network
    for key in ("visibility", "offer", "trust", "conversion", "analytics"):
        assert 1 <= scores[key] <= 5, (key, scores[key])


def test_visibility_rewards_a_complete_google_profile(seeded):
    with seeded.app_context():
        weak = scoring.score_visibility(_company())
        strong = scoring.score_visibility(_company(
            place_id="abc", website="firma.example", rating=4.7, user_ratings_total=120,
            business_status="OPERATIONAL"))
    assert weak == 1
    assert strong == 5


# ── finance helpers ─────────────────────────────────────────────

def test_month_bounds_handles_leap_years():
    assert fh.month_bounds(2028, 2) == (date(2028, 2, 1), date(2028, 2, 29))
    assert fh.month_bounds(2027, 2) == (date(2027, 2, 1), date(2027, 2, 28))


def test_generate_monthly_retainers_is_idempotent_and_uses_settings_vat(seeded):
    from models import Company, Payment, Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.default_vat_rate = 8.0
        db.session.commit()
        retainers = [c for c in Company.query.filter_by(is_retainer=True).all() if (c.monthly_fee_net or 0) > 0]
        assert retainers, "seed data should contain retainer clients"

        created = fh.generate_monthly_retainers(2030, 2)
        again = fh.generate_monthly_retainers(2030, 2)

        rows = Payment.query.filter_by(period_year=2030, period_month=2, kind="retainer").all()
        assert created == len(retainers) == len(rows)
        assert again == 0
        for p in rows:
            assert p.vat_rate == 8.0
            assert p.amount_gross == round(p.amount_net * 1.08, 2)
            assert p.issued_at == date(2030, 2, 1)
            assert p.due_at.month == 2 and p.due_at.day <= 28  # billing day clamped to the month
            assert p.title.lower().startswith("abonament luty 2030")
        s.default_vat_rate = 23.0
        db.session.commit()


def test_mark_overdue_payments(seeded):
    from models import Company, Payment, db

    with seeded.app_context():
        company = Company.query.first()
        p = Payment(company_id=company.id, title="Test zaległości", amount_net=100, vat_rate=23,
                    kind="one_time", status="unpaid", issued_at=date.today() - timedelta(days=30),
                    due_at=date.today() - timedelta(days=1))
        p.recompute_gross()
        db.session.add(p)
        db.session.commit()

        assert fh.mark_overdue_payments() >= 1
        assert db.session.get(Payment, p.id).status == "overdue"
        assert fh.mark_overdue_payments() == 0


def test_monthly_balance_counts_paid_revenue_and_expenses_in_the_month(seeded):
    from models import Company, Expense, Payment, db

    with seeded.app_context():
        before = fh.monthly_balance(2031, 3)
        company = Company.query.first()
        paid = Payment(company_id=company.id, title="Wdrożenie", amount_net=1000, vat_rate=23,
                       kind="one_time", status="paid", issued_at=date(2031, 3, 1),
                       due_at=date(2031, 3, 14), paid_at=date(2031, 3, 10))
        unpaid = Payment(company_id=company.id, title="Nieopłacone", amount_net=500, vat_rate=23,
                         kind="one_time", status="unpaid", issued_at=date(2031, 3, 1),
                         due_at=date(2031, 3, 30))
        cost = Expense(category="software", amount_net=200, vat_rate=23, payment_date=date(2031, 3, 5))
        for row in (paid, unpaid, cost):
            if hasattr(row, "recompute_gross"):
                row.recompute_gross()
            db.session.add(row)
        db.session.commit()

        after = fh.monthly_balance(2031, 3)
        assert after["revenue_total"] - before["revenue_total"] == 1000  # unpaid does not count
        assert after["expense_total"] - before["expense_total"] == 200
        assert after["balance"] == round(
            after["revenue_total"] - after["expense_total"] - after["subscription_allocation"], 2)
        assert after["month_label"] == "Marzec"


def test_retainers_without_vat_when_agency_is_not_a_vat_payer(seeded):
    from models import Payment, Settings, db

    with seeded.app_context():
        s = Settings.get()
        s.company_vat_payer = False
        db.session.commit()
        fh.generate_monthly_retainers(2030, 5)
        rows = Payment.query.filter_by(period_year=2030, period_month=5, kind="retainer").all()
        assert rows and all(p.vat_rate == 0.0 and p.amount_gross == p.amount_net for p in rows)
        s.company_vat_payer = True
        db.session.commit()
