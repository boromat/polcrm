"""
Wstrzykuje bogaty zestaw danych testowych do PolCRM.

Uruchomienie (z katalogu głównego repozytorium):
    python scripts/seed_test_data.py

Idempotentne: firmy oznaczone prefiksem "[TEST]" - powtórne uruchomienie NIE duplikuje.
Aby wyczyścić dane testowe: python scripts/seed_test_data.py --clean

Konta demo (tylko lokalnie, skrypt nie działa przy FLASK_ENV=production):
    anna@example.com    administrator
    tomasz@example.com  członek
    ola@example.com     członek
Hasło wszystkich kont demo: zmienna POLCRM_DEMO_PASSWORD, domyślnie "demo-polcrm".
"""

import os
import sys
from datetime import date, timedelta
from pathlib import Path

# Konsola Windows (cp1250) nie zna znakow typu strzalka - bez tego skrypt wywraca sie na print().
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

# ZABEZPIECZENIE: ten skrypt NIGDY nie moze zostac uruchomiony na produkcji.
# Wrzucilby fake'owe firmy "[TEST]" do prawdziwej bazy.
if os.environ.get("FLASK_ENV", "").lower() == "production":
    print("=" * 70)
    print("  BLAD: seed_test_data.py jest zablokowany na produkcji (FLASK_ENV=production).")
    print("  Ten skrypt tworzy fake'owe dane testowe - NIE uruchamiaj go na ")
    print("  prawdziwej bazie klientow.")
    print("=" * 70)
    sys.exit(1)

# Skrypt leży w scripts/, a moduły aplikacji w katalogu nadrzędnym.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import app  # noqa: E402
from models import (
    utcnow,
    db, Company, Package, Offer, Visit, Note,
    Payment, Expense, Subscription, Task, Project, ContentPost,
    KnowledgeArticle, ClientCredential, EmailLog,
    GscSnapshot, GaSnapshot, Audit, Competitor, Whiteboard, WhiteboardStroke,
    Mention, delete_company, delete_whiteboard,
)
import finance_helpers


TEST_PREFIX = "[TEST]"
DEMO_PASSWORD = os.environ.get("POLCRM_DEMO_PASSWORD", "demo-polcrm")
DEMO_USERS = [
    # (imię, e-mail, rola, kolor, motyw)
    ("Anna", "anna@example.com", "admin", "#6c5ce7", "colorful"),
    ("Tomasz", "tomasz@example.com", "member", "#10b981", "minimal"),
    ("Ola", "ola@example.com", "member", "#f59e0b", "colorful"),
]


def seed_demo_users():
    """Trzy konta demo z hasłem - zespół większy niż dwie osoby. Istniejących kont nie nadpisuje."""
    from models import User
    for name, email, role, color, theme in DEMO_USERS:
        user = User.query.filter_by(email=email).first()
        if user is None:
            user = User(name=name, email=email, role=role, initials=name[0], avatar_color=color,
                        default_theme=theme, language="pl")
            db.session.add(user)
        if not user.has_password:
            user.set_password(DEMO_PASSWORD)
    db.session.commit()

def _abonament(issued):
    """Tytuł płatności abonamentowej z miesiącem wystawienia (daty seeda są względne do dziś)."""
    return f"Abonament {finance_helpers.PL_MONTHS[issued.month - 1]} {issued.year}"


def seed_demo_audit(company):
    """Gotowy audyt z wynikami i planem - tak, jak wygląda po auto-scoringu i uzupełnieniu checklist.
    Bez wywołań Google (auto-scoring w aplikacji pyta Places i PageSpeed)."""
    audit = Audit(company_id=company.id, status="ready",
                  score_visibility=3, score_offer=4, score_trust=4, score_conversion=2, score_analytics=2,
                  pagespeed_mobile=48, pagespeed_desktop=81)
    audit.pagespeed_data = {"mobile_score": 48, "desktop_score": 81, "fcp": "2.9 s", "lcp": "4.8 s", "cls": "0.12"}
    audit.section_context = {
        "auto_data": {"name": company.name, "address": company.address, "industry": company.industry,
                      "category": company.primary_type, "rating": company.rating,
                      "status": company.business_status},
        "notes": "Gabinet chce więcej pacjentów na implanty i wybielanie.",
    }
    audit.section_website = {
        "auto_data": {"pagespeed_mobile": 48, "pagespeed_desktop": 81, "fcp": "2.9 s", "lcp": "4.8 s", "cls": "0.12"},
        "checklist": {"mobile_responsive": True, "clear_offer": True, "visible_cta": False,
                      "contact_form": True, "trust_elements": False, "fast_loading": False},
        "notes": "Strona wolna na telefonie, brak widocznego przycisku rezerwacji.",
    }
    audit.section_seo = {
        "checklist": {"keywords_in_title": True, "keywords_in_headings": False, "keywords_in_content": True,
                      "subpages_per_service": False, "subpages_per_location": False, "internal_linking": False,
                      "meta_with_location": True, "schema_local_business": False, "https_active": True,
                      "mobile_friendly": True},
        "notes": "Jedna podstrona na wszystkie usługi.",
    }
    audit.section_gbp = {
        "auto_data": {"has_profile": True, "rating": company.rating, "reviews_count": company.user_ratings_total,
                      "phone": company.phone, "address": company.address, "business_status": company.business_status},
        "checklist": {"complete_data": True, "correct_categories": True, "current_hours": True,
                      "photos_added": False, "posts_published": False, "reviews_responded": True,
                      "qa_responded": False, "nap_consistent": True},
        "notes": "",
    }
    audit.section_directories = {
        "checklist": {"panorama_firm": True, "pkt_pl": False, "yelp": False, "industry_directories": True,
                      "nap_directories_consistent": False, "nap_google_consistent": True},
        "notes": "",
    }
    audit.section_competition = {"competitors": [], "notes": "Dwa gabinety w promieniu 1 km mają więcej opinii."}
    audit.section_plan90 = {
        "actions": ["Podstrony usług: implanty, wybielanie, ortodoncja", "Przycisk rezerwacji i szybsza strona mobilna",
                    "GA4 ze śledzeniem rezerwacji"],
        "notes": "",
    }
    audit.top_problems = ["Wolna strona na telefonie", "Brak śledzenia konwersji", "Mało zdjęć w wizytówce"]
    audit.top_opportunities = ["Frazy lokalne z usługą", "Opinie po wizycie", "Posty w wizytówce co tydzień"]
    audit.recommended_actions = ["Podstrony usług", "Kampania opinii", "Analityka rezerwacji"]
    audit.compute_overall()
    db.session.add(audit)
    db.session.flush()
    for name, rating, total, vis, trust, strengths in [
        (f"{TEST_PREFIX} Klinika Uśmiech", 4.8, 412, 5, 5, "Dużo opinii, osobne podstrony usług"),
        (f"{TEST_PREFIX} Stomatologia Centrum", 4.5, 268, 4, 4, "Rezerwacja online"),
    ]:
        db.session.add(Competitor(audit_id=audit.id, name=name, address=company.address, rating=rating,
                                  user_ratings_total=total, score_visibility=vis, score_trust=trust,
                                  strengths=strengths, weaknesses="Brak bloga"))
    print("Dodano 1 audyt z 2 konkurentami.")


def seed_demo_whiteboard(company):
    """Tablica z kilkoma karteczkami i strzałkami - plan kampanii."""
    board = Whiteboard(name=f"{TEST_PREFIX} Plan kampanii - dentysta", company_id=company.id,
                       description="Burza mózgów z klientem")
    db.session.add(board)
    db.session.flush()
    # (tekst, x, y, kolor karteczki - pole `color` jest jej tłem)
    stickies = [
        ("Miesiąc 1\nPodstrony usług: implanty, wybielanie", 120, 150, "#fde68a"),
        ("Miesiąc 2\nKampania opinii po wizycie", 520, 150, "#bbf7d0"),
        ("Miesiąc 3\nGA4 + śledzenie rezerwacji", 920, 150, "#bfdbfe"),
        ("Co tydzień\nPosty w wizytówce Google", 520, 430, "#fbcfe8"),
        ("Raport dla klienta\nco miesiąc", 1320, 150, "#ddd6fe"),
    ]
    for order, (text, x, y, color) in enumerate(stickies):
        db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="sticky", color=color,
                                        points=[[x, y]], text=text, width_box=260, height_box=150, font_size=20,
                                        stroke_order=order))
    arrows = [((390, 225), (510, 225)), ((790, 225), (910, 225)), ((1190, 225), (1310, 225)), ((650, 310), (650, 420))]
    for order, (a, b) in enumerate(arrows):
        db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="arrow", color="#6c5ce7", width=3,
                                        points=[list(a), list(b)], stroke_order=10 + order))
    db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="text", color="#111111", font_size=34,
                                    points=[[120, 70]], text="Plan na 90 dni - Dentysta Kowalski", stroke_order=20))
    db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="ellipse", color="#ef4444", width=3,
                                    points=[[1300, 400], [1600, 560]], stroke_order=21))
    db.session.add(WhiteboardStroke(whiteboard_id=board.id, tool="text", color="#ef4444", font_size=22,
                                    points=[[1345, 462]], text="Cel: +30% rezerwacji", stroke_order=22))
    print("Dodano 1 tablicę z 12 elementami.")


def clean_test_data():
    """Usuwa wszystkie firmy z prefiksem [TEST] (kaskadowo usuwa powiązane dane)."""
    with app.app_context():
        for board in Whiteboard.query.filter(Whiteboard.name.like(f"{TEST_PREFIX}%")).all():
            delete_whiteboard(board)
        test_ids = [c.id for c in Company.query.filter(Company.name.like(f"{TEST_PREFIX}%"))]
        count = len(test_ids)
        # Zadania przypięte do firm testowych poza projektami (delete_company tylko je odpina)
        loose = Task.query.filter(Task.company_id.in_(test_ids), Task.project_id.is_(None),
                                  Task.parent_task_id.is_(None)).all() if test_ids else []
        if loose:
            Mention.query.filter(Mention.task_id.in_([t.id for t in loose])).delete(synchronize_session=False)
            for t in loose:
                db.session.delete(t)  # z podzadaniami i komentarzami (kaskada w modelu)
            db.session.flush()
        for cid in test_ids:  # audits, projects, files... go with the company (models.delete_company)
            delete_company(db.session.get(Company, cid))
            db.session.flush()
        # Subskrypcje testowe
        test_subs = Subscription.query.filter(Subscription.name.like(f"{TEST_PREFIX}%")).all()
        for s in test_subs:
            db.session.delete(s)
        # Koszty bez alokacji do firmy (oznaczone prefiksem)
        test_exp = Expense.query.filter(Expense.title.like(f"{TEST_PREFIX}%")).all()
        for e in test_exp:
            db.session.delete(e)
        # Notatki osobiste testowe
        test_notes = Note.query.filter(Note.scope == "personal", Note.content.like(f"{TEST_PREFIX}%")).all()
        for n in test_notes:
            db.session.delete(n)
        # Zadania testowe (bez company_id)
        test_tasks = Task.query.filter(Task.company_id == None, Task.title.like(f"{TEST_PREFIX}%")).all()
        for t in test_tasks:
            db.session.delete(t)
        # Knowledge artykuły testowe
        test_kb = KnowledgeArticle.query.filter(KnowledgeArticle.title.like(f"{TEST_PREFIX}%")).all()
        for a in test_kb:
            db.session.delete(a)
        db.session.commit()
        print(f"Usunięto {count} firm testowych i powiązane dane.")


def seed():
    with app.app_context():
        seed_demo_users()
        # Sprawdź czy już jest
        existing = Company.query.filter(Company.name.like(f"{TEST_PREFIX}%")).count()
        if existing > 0:
            print(f"Dane testowe już istnieją ({existing} firm). Uruchom --clean żeby usunąć i wstawić od nowa.")
            return

        today = date.today()
        now = utcnow()

        # ═══ SUBSKRYPCJE ═══════════════════════════════════════════
        subs_data = [
            (f"{TEST_PREFIX} Ahrefs Standard", "Ahrefs Pte Ltd", 449, "monthly", today + timedelta(days=22), "seo_tools"),
            (f"{TEST_PREFIX} Senuto PRO", "Senuto Sp. z o.o.", 299, "monthly", today + timedelta(days=5), "seo_tools"),
            (f"{TEST_PREFIX} Hostinger VPS", "Hostinger", 49, "monthly", today + timedelta(days=15), "office_transport"),
            (f"{TEST_PREFIX} Canva Pro", "Canva", 99, "yearly", today + timedelta(days=210), "marketing"),
            (f"{TEST_PREFIX} ChatGPT Team", "OpenAI", 100, "monthly", today + timedelta(days=8), "seo_tools"),
        ]
        subs_map = {}
        for name, vendor, amt, cycle, renewal, cat in subs_data:
            s = Subscription(name=name, vendor=vendor, amount_net=amt, vat_rate=23,
                             billing_cycle=cycle, renewal_date=renewal, category=cat,
                             is_active=True, notes="Dane testowe")
            db.session.add(s)
            db.session.flush()
            subs_map[name] = s
        print(f"Dodano {len(subs_data)} subskrypcji testowych.")

        # ═══ FIRMY (klienci) ═══════════════════════════════════════
        companies_data = [
            {
                "name": f"{TEST_PREFIX} Dentysta Kowalski",
                "industry": "gabinet stomatologiczny",
                "address": "ul. Piękna 12, 00-001 Warszawa",
                "phone": "+48 500 000 001",
                "website": "dentysta-kowalski.example",
                "contact_person": "Jan Kowalski",
                "contact_email": "kontakt@dentysta-kowalski.example",
                "pipeline_stage": "client",
                "is_retainer": True,
                "monthly_fee_net": 1500,
                "billing_day": 10,
                "retainer_started_at": today - timedelta(days=90),
                "client_legal_name": "Gabinet Stomatologiczny Jan Kowalski",
                "client_nip": "1234567890",
                "client_address": "ul. Piękna 12, 00-001 Warszawa",
                "gsc_site_url": "sc-domain:dentysta-kowalski.example",
                "ga_property_id": "400123456",
                "rating": 4.8,
                "user_ratings_total": 87,
            },
            {
                "name": f"{TEST_PREFIX} Auto Serwis Nowak",
                "industry": "warsztat samochodowy",
                "address": "ul. Warsztatowa 5, 02-200 Warszawa",
                "phone": "+48 500 000 002",
                "website": "auto-nowak.example",
                "contact_person": "Piotr Nowak",
                "contact_email": "piotr@auto-nowak.example",
                "pipeline_stage": "client",
                "is_retainer": True,
                "monthly_fee_net": 2200,
                "billing_day": 15,
                "retainer_started_at": today - timedelta(days=150),
                "client_legal_name": "AUTO-NOWAK Piotr Nowak",
                "client_nip": "1234567899",
                "client_address": "ul. Warsztatowa 5, 02-200 Warszawa",
                "rating": 4.6,
                "user_ratings_total": 124,
            },
            {
                "name": f"{TEST_PREFIX} Kancelaria Wiśniewska",
                "industry": "usługi prawne",
                "address": "al. Jerozolimskie 100, 00-800 Warszawa",
                "phone": "+48 500 000 003",
                "contact_person": "Anna Wiśniewska",
                "contact_email": "a.wisniewska@kancelaria-w.example",
                "pipeline_stage": "offer",
                "is_retainer": False,
                "rating": 4.9,
                "user_ratings_total": 45,
                "next_action": "wysłać ofertę PREMIUM po rozmowie z mec.",
                "next_action_date": today + timedelta(days=2),
            },
            {
                "name": f"{TEST_PREFIX} Pizzeria Bella",
                "industry": "gastronomia",
                "address": "ul. Smaczna 7, 03-300 Warszawa",
                "phone": "+48 500 000 004",
                "contact_person": "Marco Rossi",
                "pipeline_stage": "visit",
                "next_action": "wizyta w środę 11:00 - prezentacja audytu",
                "next_action_date": today + timedelta(days=3),
                "rating": 4.2,
                "user_ratings_total": 210,
            },
            {
                "name": f"{TEST_PREFIX} Siłownia FitZone",
                "industry": "fitness",
                "address": "ul. Sportowa 22, 01-100 Warszawa",
                "pipeline_stage": "lead",
                "next_action": "zadzwonić - zebrać info o konkurencji",
                "next_action_date": today - timedelta(days=2),
                "rating": 4.4,
                "user_ratings_total": 68,
            },
            {
                "name": f"{TEST_PREFIX} Salon Fryzjerski Elegance",
                "industry": "usługi beauty",
                "address": "ul. Modna 3, 00-500 Warszawa",
                "contact_person": "Magdalena Kowal",
                "pipeline_stage": "audit",
                "rating": 5.0,
                "user_ratings_total": 32,
            },
        ]
        companies = []
        for data in companies_data:
            c = Company(**data, created_at=now - timedelta(days=180))
            c.ensure_portal_token()
            db.session.add(c)
            db.session.flush()
            companies.append(c)
        print(f"Dodano {len(companies)} firm testowych.")

        c_dentist, c_auto, c_kancelaria, c_pizza, c_silownia, c_salon = companies

        # ═══ PŁATNOŚCI (dla retainerów) ═════════════════════════════
        payments_data = [
            # Dentysta - 3 miesiące historii: 2 paid, 1 overdue
            (c_dentist, _abonament(today - timedelta(days=80)), 1500, "retainer", "paid",
             today - timedelta(days=80), today - timedelta(days=82), today - timedelta(days=78)),
            (c_dentist, _abonament(today - timedelta(days=50)), 1500, "retainer", "paid",
             today - timedelta(days=50), today - timedelta(days=52), today - timedelta(days=48)),
            (c_dentist, _abonament(today - timedelta(days=20)), 1500, "retainer", "paid",
             today - timedelta(days=20), today - timedelta(days=22), today - timedelta(days=18)),
            (c_dentist, _abonament(today - timedelta(days=5)), 1500, "retainer", "unpaid",
             today - timedelta(days=5), today + timedelta(days=5), None),
            (c_dentist, "Sesja zdjęciowa GBP", 500, "addon", "paid",
             today - timedelta(days=40), today - timedelta(days=40), today - timedelta(days=38)),
            # Auto - 1 paid, 1 overdue, 1 unpaid
            (c_auto, _abonament(today - timedelta(days=45)), 2200, "retainer", "paid",
             today - timedelta(days=45), today - timedelta(days=47), today - timedelta(days=43)),
            (c_auto, _abonament(today - timedelta(days=30)), 2200, "retainer", "overdue",
             today - timedelta(days=30), today - timedelta(days=10), None),
            (c_auto, _abonament(today - timedelta(days=1)), 2200, "retainer", "unpaid",
             today - timedelta(days=1), today + timedelta(days=14), None),
            (c_auto, "Dodatkowe 3 teksty blog", 900, "addon", "paid",
             today - timedelta(days=20), today - timedelta(days=20), today - timedelta(days=15)),
            # Kancelaria - etap projektu (jednorazowe)
            (c_kancelaria, "Audyt SEO - 1. etap", 1000, "project_milestone", "paid",
             today - timedelta(days=15), today - timedelta(days=15), today - timedelta(days=10)),
        ]
        for company, title, amt, kind, status, issued, due, paid in payments_data:
            p = Payment(
                company_id=company.id, title=title,
                amount_net=amt, vat_rate=23, kind=kind, status=status,
                issued_at=issued, due_at=due, paid_at=paid,
                period_year=today.year,
                period_month=issued.month if issued else today.month,
                payment_number=finance_helpers.next_payment_number(),
            )
            p.recompute_gross()
            db.session.add(p)
            db.session.flush()
        print(f"Dodano {len(payments_data)} płatności testowych.")

        # ═══ KOSZTY ═════════════════════════════════════════════════
        expenses_data = [
            ("seo_tools", "Ahrefs", f"{TEST_PREFIX} Ahrefs Standard (kwiecień)", 449, today - timedelta(days=5), subs_map.get(f"{TEST_PREFIX} Ahrefs Standard"), None),
            ("seo_tools", "Senuto", f"{TEST_PREFIX} Senuto PRO (kwiecień)", 299, today - timedelta(days=8), subs_map.get(f"{TEST_PREFIX} Senuto PRO"), None),
            ("subcontractor", "Copywriter", f"{TEST_PREFIX} 3 teksty blog - Anna N.", 900, today - timedelta(days=10), None, c_auto),
            ("subcontractor", "Linkbuilder", f"{TEST_PREFIX} 5 guest postów", 1500, today - timedelta(days=20), None, c_dentist),
            ("subcontractor", "Grafik", f"{TEST_PREFIX} Set kreacji social", 600, today - timedelta(days=15), None, None),
            ("marketing", "Google Ads", f"{TEST_PREFIX} Kampania własna agencji", 400, today - timedelta(days=12), None, None),
            ("marketing", "Canva", f"{TEST_PREFIX} Canva Pro (rocznie)", 99, today - timedelta(days=30), subs_map.get(f"{TEST_PREFIX} Canva Pro"), None),
            ("office_transport", "Hostinger", f"{TEST_PREFIX} Hostinger VPS (kwiecień)", 49, today - timedelta(days=7), subs_map.get(f"{TEST_PREFIX} Hostinger VPS"), None),
            ("office_transport", "Paliwo", f"{TEST_PREFIX} Dojazd do klientów - wizyty", 220, today - timedelta(days=3), None, None),
            ("office_transport", "Internet biuro", f"{TEST_PREFIX} Abonament LTE", 89, today - timedelta(days=14), None, None),
        ]
        for cat, subcat, title, amt, pay_date, sub, client in expenses_data:
            e = Expense(
                category=cat, subcategory=subcat, title=title, vendor=subcat,
                amount_net=amt, vat_rate=23, payment_date=pay_date,
                subscription_id=sub.id if sub else None,
                client_id=client.id if client else None,
            )
            e.recompute_gross()
            db.session.add(e)
        print(f"Dodano {len(expenses_data)} kosztów testowych.")

        # ═══ ZADANIA ════════════════════════════════════════════════
        tasks_data = [
            # Dziś
            ("Zadzwonić do Wiśniewskiej - domknąć ofertę", "urgent", "todo", today, c_kancelaria.id, None),
            ("Wygenerować raport miesięczny Dentysta", "high", "in_progress", today, c_dentist.id, None),
            (f"{TEST_PREFIX} Zaktualizować własną stronę agencji", "medium", "todo", today, None, None),
            # Jutro / ten tydzień
            ("Przygotować ofertę PREMIUM dla Kancelarii", "high", "todo", today + timedelta(days=1), c_kancelaria.id, None),
            ("Publikacja 2 tekstów na bloga Auto Nowak", "medium", "in_progress", today + timedelta(days=3), c_auto.id, None),
            ("Odpowiedzieć na 8 opinii GBP - Dentysta", "medium", "todo", today + timedelta(days=4), c_dentist.id, None),
            # Przeterminowane
            ("Follow-up po wizycie - Pizzeria Bella", "high", "todo", today - timedelta(days=3), c_pizza.id, None),
            ("Sprawdzić nowe linki dla Auto Nowak", "low", "todo", today - timedelta(days=1), c_auto.id, None),
            # Bez deadline
            (f"{TEST_PREFIX} Wymyślić nowy landing dla agencji", "low", "todo", None, None, None),
            # Zrobione
            ("Audyt SEO dla Kancelarii", "high", "done", today - timedelta(days=10), c_kancelaria.id, None),
            ("Onboarding kliencki - Dentysta", "medium", "done", today - timedelta(days=85), c_dentist.id, None),
            # W blokadzie
            ("Publikacja landing page Pizzerii - czekamy na brief", "medium", "blocked", today + timedelta(days=7), c_pizza.id, None),
        ]
        for title, prio, status, deadline, company_id, project_id in tasks_data:
            t = Task(
                title=title, priority=prio, status=status, deadline=deadline,
                company_id=company_id, project_id=project_id,
                done_at=now if status == "done" else None,
            )
            db.session.add(t)
        print(f"Dodano {len(tasks_data)} zadań testowych.")

        # ═══ PROJEKTY ══════════════════════════════════════════════
        projects_data = [
            (c_pizza, "Strona WWW + zamawianie online", "website", "pizzabella.example", "WordPress", "Hostinger", 8500, "active", today - timedelta(days=20), today + timedelta(days=30)),
            (c_dentist, "Kampania content Q2 2026", "content_campaign", "", "", "", 3000, "active", today - timedelta(days=5), today + timedelta(days=85)),
            (c_kancelaria, "Nowa strona kancelarii", "website", "kancelaria-wisniewska.example", "WordPress", "OVH", 12000, "planning", today + timedelta(days=7), today + timedelta(days=60)),
        ]
        projects = []
        for company, name, kind, domain, cms, host, budget, status, start, dl in projects_data:
            p = Project(
                company_id=company.id, name=name, kind=kind, domain=domain,
                cms=cms, hosting=host, budget_net=budget, status=status,
                started_at=start, deadline=dl,
                notes="Projekt testowy - dane wygenerowane seederem.",
            )
            db.session.add(p)
            db.session.flush()
            projects.append(p)
        print(f"Dodano {len(projects)} projektów testowych.")

        proj_pizza, proj_dentist, proj_kanc = projects

        # Zadania dla projektu Pizzy
        pizza_tasks = [
            ("Brief i zebranie wymagań", "high", "done", today - timedelta(days=20)),
            ("Projekt graficzny (makieta Figma)", "high", "done", today - timedelta(days=12)),
            ("Development front-end", "medium", "in_progress", today + timedelta(days=7)),
            ("Integracja zamówień online", "high", "todo", today + timedelta(days=14)),
            ("Testy i wdrożenie", "urgent", "todo", today + timedelta(days=28)),
        ]
        for title, prio, status, dl in pizza_tasks:
            db.session.add(Task(
                title=title, priority=prio, status=status, deadline=dl,
                company_id=c_pizza.id, project_id=proj_pizza.id,
                done_at=now if status == "done" else None,
            ))
        print(f"Dodano {len(pizza_tasks)} zadań dla projektu Pizza.")

        # ═══ CONTENT POSTS ══════════════════════════════════════════
        content_data = [
            (c_dentist, "10 powodów dlaczego warto wybielać zęby u dentysty", ["wybielanie zębów warszawa", "stomatolog"], "blog", "published", today - timedelta(days=30), "Anna Kowalczyk"),
            (c_dentist, "Jak wygląda implant zęba - krok po kroku", ["implanty zębowe", "dentysta"], "blog", "approved", today + timedelta(days=5), "Anna Kowalczyk"),
            (c_dentist, "Ortodoncja dla dorosłych", ["ortodonta warszawa", "aparat ortodontyczny"], "blog", "writing", today + timedelta(days=12), "Anna Kowalczyk"),
            (c_auto, "Kiedy wymienić rozrząd?", ["rozrząd", "serwis samochodowy"], "blog", "published", today - timedelta(days=10), "Tomek Biuro"),
            (c_auto, "Przygotowanie samochodu na lato", ["klimatyzacja", "opony letnie"], "blog", "review", today + timedelta(days=2), "Tomek Biuro"),
            (c_pizza, "Landing: zamów online z dowozem", ["pizza warszawa dowóz"], "landing", "idea", today + timedelta(days=14), ""),
        ]
        for company, title, keywords, ctype, status, deadline, writer in content_data:
            cp = ContentPost(
                company_id=company.id, title=title, content_type=ctype,
                status=status, deadline=deadline, writer_name=writer,
                brief="Brief testowy wygenerowany seederem.",
                published_at=now - timedelta(days=5) if status == "published" else None,
            )
            cp.keywords = keywords
            db.session.add(cp)
        print(f"Dodano {len(content_data)} publikacji content.")

        # ═══ DOSTĘPY (credentials) ══════════════════════════════════
        creds_data = [
            (c_dentist, "WordPress admin", "https://dentysta-kowalski.example/wp-admin", "admin-agencja", "bitwarden://item?id=abc-123"),
            (c_dentist, "Google Search Console", "https://search.google.com/search-console", "seo@agencja.example", "bitwarden://item?id=gsc-dentist"),
            (c_dentist, "Google Analytics 4", "https://analytics.google.com", "seo@agencja.example", "bitwarden://item?id=ga-dentist"),
            (c_dentist, "Google Business Profile", "https://business.google.com", "manager", "bitwarden://item?id=gbp-dentist"),
            (c_auto, "WordPress admin", "https://auto-nowak.example/wp-admin", "admin", "onepassword://vault/main/item/auto-wp"),
            (c_auto, "Hosting cPanel", "https://cpanel.hostinger.com", "auto_nowak", "onepassword://vault/main/item/auto-host"),
            (c_auto, "Domena (rejestrator)", "https://nazwa.pl", "piotr@auto-nowak.example", "onepassword://vault/main/item/auto-dns"),
            (c_pizza, "WordPress admin (developing)", "https://stg.pizzabella.example/wp-admin", "dev", "bitwarden://item?id=pizza-stg"),
        ]
        for company, label, url, username, vault in creds_data:
            db.session.add(ClientCredential(
                company_id=company.id, label=label, login_url=url,
                username_hint=username, vault_link=vault,
                notes="Dane testowe - to nie są prawdziwe linki do sejfu.",
            ))
        print(f"Dodano {len(creds_data)} dostępów testowych.")

        # ═══ NOTATKI ════════════════════════════════════════════════
        notes_data = [
            # Osobiste
            (None, None, "personal", "general", "Pomysł na content", f"{TEST_PREFIX} Pomysł: seria tekstów Jak zweryfikować agencję SEO - dobra do pozyskania B2B leadów.", True),
            (None, None, "personal", "todo", "", f"{TEST_PREFIX} Zaktualizować cennik pakietów. Ostatnia zmiana 6 miesięcy temu.", False),
            (None, None, "personal", "idea", "", f"{TEST_PREFIX} Rozważyć wprowadzenie pakietu STARTER 800 zł/mc dla mikrofirm.", False),
            # Firmowe
            (c_dentist.id, None, "company", "call", "Rozmowa z Kowalskim 14.04", "Jan dopytywał o bloga. Wolałby krótsze teksty (600-800 słów zamiast 1200). Przekazać Annie.", False),
            (c_auto.id, None, "company", "meeting", "Spotkanie 08.04", "Omówiliśmy plan na Q2: 6 tekstów, 10 linków, odpowiedzi na opinie 2x/tydzień. Piotr akceptuje budżet +900 na content.", True),
            # Projektowe
            (c_pizza.id, proj_pizza.id if proj_pizza else None, "project", "general", "Brief Pizzy", "Makieta Figma: link w plikach firmy. Szef chce sekcję 'Sala eventowa' na końcu home page.", False),
            (c_kancelaria.id, proj_kanc.id if proj_kanc else None, "project", "follow_up", "Warunki kancelarii", "Czekamy na feedback Wiśniewskiej ws. kolorystyki (czerń/gold vs. granat/biel).", False),
        ]
        for cid, pid, scope, ntype, title, content, pinned in notes_data:
            db.session.add(Note(
                company_id=cid, project_id=pid, scope=scope, note_type=ntype,
                title=title, content=content, pinned=pinned,
            ))
        print(f"Dodano {len(notes_data)} notatek testowych.")

        # ═══ OFERTY ════════════════════════════════════════════════
        packages = Package.query.filter_by(is_active=True).all()
        if packages:
            pkg_growth = next((p for p in packages if p.name == "GROWTH"), packages[0])
            pkg_premium = next((p for p in packages if p.name == "PREMIUM"), packages[0])
            offers_data = [
                (c_kancelaria, pkg_premium, None, "Oferta PREMIUM z rabatem 10%", "sent"),
                (c_pizza, pkg_growth, None, "Oferta GROWTH - wdrożenie w 60 dni", "draft"),
            ]
            for company, pkg, custom_price, notes, status in offers_data:
                o = Offer(
                    company_id=company.id, package_id=pkg.id,
                    custom_price=custom_price, custom_notes=notes,
                    status=status,
                    sent_at=now if status in ("sent", "accepted") else None,
                )
                db.session.add(o)
            print(f"Dodano {len(offers_data)} ofert testowych.")

        # ═══ WIZYTY ════════════════════════════════════════════════
        visits_data = [
            (c_pizza, now + timedelta(days=3, hours=2), 90, "consultation", "planned"),
            (c_kancelaria, now + timedelta(days=7, hours=-1), 60, "closing", "planned"),
            (c_dentist, now - timedelta(days=20, hours=4), 60, "follow_up", "completed"),
        ]
        for company, when, duration, vtype, status in visits_data:
            db.session.add(Visit(
                company_id=company.id, scheduled_at=when,
                duration_minutes=duration, visit_type=vtype, status=status,
                notes=f"Notatki wizyty (testowe) - {vtype}",
                outcome="Klient pozytywnie nastawiony" if status == "completed" else "",
            ))
        print(f"Dodano {len(visits_data)} wizyt testowych.")

        # ═══ GSC / GA snapshots (mock) ═════════════════════════════
        gsc = GscSnapshot(
            company_id=c_dentist.id,
            date_range_start=today - timedelta(days=30),
            date_range_end=today - timedelta(days=2),
            total_clicks=1248, total_impressions=34567,
            avg_ctr=3.61, avg_position=12.4,
        )
        gsc.top_queries = [
            {"query": "dentysta warszawa piękna", "clicks": 180, "impressions": 2100, "ctr": 8.57, "position": 4.2},
            {"query": "stomatolog warszawa śródmieście", "clicks": 120, "impressions": 3400, "ctr": 3.53, "position": 8.1},
            {"query": "wybielanie zębów warszawa cena", "clicks": 89, "impressions": 1200, "ctr": 7.42, "position": 6.8},
            {"query": "implanty zębowe warszawa", "clicks": 67, "impressions": 890, "ctr": 7.53, "position": 5.4},
            {"query": "dobry dentysta warszawa", "clicks": 56, "impressions": 2340, "ctr": 2.39, "position": 14.2},
        ]
        gsc.top_pages = [
            {"page": "https://dentysta-kowalski.example/", "clicks": 420, "impressions": 8900},
            {"page": "https://dentysta-kowalski.example/oferta/implanty", "clicks": 220, "impressions": 3400},
            {"page": "https://dentysta-kowalski.example/cennik", "clicks": 180, "impressions": 5200},
        ]
        db.session.add(gsc)

        ga = GaSnapshot(
            company_id=c_dentist.id,
            date_range_start=today - timedelta(days=30),
            date_range_end=today,
            users=2340, sessions=3120, engaged_sessions=2100,
            conversions=78, avg_engagement_time=142.5,
        )
        ga.top_sources = [
            {"source": "Organic Search", "sessions": 1840},
            {"source": "Direct", "sessions": 680},
            {"source": "Organic Social", "sessions": 340},
            {"source": "Referral", "sessions": 180},
            {"source": "Paid Search", "sessions": 80},
        ]
        ga.top_pages = [
            {"page": "/", "sessions": 1420},
            {"page": "/oferta/implanty", "sessions": 540},
            {"page": "/kontakt", "sessions": 380},
            {"page": "/blog/wybielanie-zebow", "sessions": 290},
        ]
        db.session.add(ga)
        print("Dodano mock GSC + GA snapshot dla Dentysty.")

        # ═══ EMAIL LOG ══════════════════════════════════════════════
        logs_data = [
            (c_dentist, "welcome", c_dentist.contact_email, "Witamy w agencji - kolejne kroki",
             "<p>Dzień dobry Janie, dziękujemy za zaufanie...</p>", "sent", now - timedelta(days=89)),
            (c_dentist, "payment_reminder", c_dentist.contact_email, "Przypomnienie P-2026-0004",
             "<p>Przypominamy o płatności abonamentu kwiecień 2026.</p>", "sent", now - timedelta(days=2)),
            (c_kancelaria, "audit_delivery", c_kancelaria.contact_email, "Audyt - Kancelaria Wiśniewska",
             "<p>W załączeniu audyt marketingowy.</p>", "sent", now - timedelta(days=9)),
            (c_pizza, "follow_up_after_visit", "marco@pizzabella.example", "Podsumowanie naszego spotkania",
             "<p>Dziękujemy za spotkanie...</p>", "failed", now - timedelta(days=15)),
        ]
        for company, tpl_key, to_addr, subj, body, status, sent_at in logs_data:
            log = EmailLog(
                company_id=company.id, template_key=tpl_key,
                to_address=to_addr, subject_rendered=subj,
                body_rendered=body, status=status, sent_at=sent_at,
                error_message="Adres odbiorcy nie istnieje" if status == "failed" else "",
            )
            db.session.add(log)
        print(f"Dodano {len(logs_data)} wpisów w historii maili.")

        # ═══ ARTYKUŁY WIEDZY DODATKOWE ═════════════════════════════
        extra_kb = [
            (f"{TEST_PREFIX} Cennik usług - matryca decyzyjna",
             "Sprzedaż",
             "# Jak wyceniać?\n\n## Stawki orientacyjne\n- **START** 1500 zł/mc - mikrofirmy (1-5 osób)\n- **GROWTH** 3500 zł/mc - SMB (6-20 osób)\n- **PREMIUM** 5000+ zł/mc - większe marki\n\n## Czynniki modyfikujące\n- Konkurencyjność branży (+20% dla TOP 5 trudnych)\n- Budżet klienta (LTV > 50k = możliwa nizsza marża startowa)\n- Trudny temat / niszowa wiedza (+15%)\n",
             ["cennik", "sprzedaż"], False),
            (f"{TEST_PREFIX} Checklist: pierwsze 48h po podpisaniu umowy",
             "Onboarding",
             "# Pierwsze 48h\n\n- [ ] Email powitalny wysłany\n- [ ] Umowa RODO podpisana\n- [ ] Dostępy: GBP, GSC, GA4\n- [ ] Folder Dropbox utworzony\n- [ ] Faktura proforma wystawiona\n- [ ] Slack/WhatsApp grupa utworzona\n- [ ] Kickoff call zaplanowany (do 7 dni)\n",
             ["onboarding", "checklist"], True),
        ]
        for title, cat, body, tags, pinned in extra_kb:
            a = KnowledgeArticle(title=title, category=cat, body=body, pinned=pinned)
            a.tags = tags
            db.session.add(a)
        print(f"Dodano {len(extra_kb)} dodatkowych artykułów wiedzy.")

        seed_demo_audit(c_dentist)
        seed_demo_whiteboard(c_dentist)

        db.session.commit()
        print("\n" + "=" * 60)
        print("[OK] Dane testowe wstrzykniete pomyslnie.")
        print("=" * 60)
        print("\nOtwórz http://localhost:4666 i sprawdź:")
        print("  - Dashboard → zadania na dziś (3) + przeterminowane (2)")
        print("  - Finanse → bilans, przychody (10), koszty (10), subskrypcje (5)")
        print("  - Zadania → 17 zadań w różnych stanach")
        print("  - Projekty → 3 projekty (w tym Pizza z 5 podzadaniami)")
        print("  - Content → 6 publikacji")
        print("  - Firmy → 6 firm [TEST]")
        print("  - Notatki → 7 notatek (3 osobiste, 2 firmowe, 2 projektowe)")
        print("  - Baza wiedzy → 6 artykułów (4 defaultowe + 2 testowe)")
        print("  - Historia maili → 4 wpisy")
        print("  - Dentysta → analityka (GSC + GA), 4 dostępy, 5 płatności")


if __name__ == "__main__":
    if "--clean" in sys.argv:
        clean_test_data()
    else:
        seed()
