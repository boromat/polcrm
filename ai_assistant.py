"""
AI Assistant - PolCRM.

Wykorzystuje OpenRouter (OpenAI-compatible API) z konfigurowalnym modelem.
Domyślnie: google/gemini-3.1-flash-lite-preview (tania opcja).
Fallback/alternatywa: anthropic/claude-haiku-4.5, openai/gpt-4o-mini, google/gemini-2.5-flash.

Asystent ma dostęp do bazy danych przez tool calling:
  - list_tasks, create_task, move_task
  - list_companies, get_company, update_pipeline_stage
  - get_finances_summary, list_overdue_payments, create_payment
  - add_note, search_global, list_calendar

Opcjonalnie (Ustawienia → AI Asystent) dane osobowe są maskowane przez polanon,
zanim cokolwiek trafi do OpenRouter - zob. privacy.py.
"""

import json
import logging
import os
from datetime import date, datetime, timedelta, timezone

import requests
from sqlalchemy import or_

import i18n
import privacy
from i18n import _

log = logging.getLogger(__name__)

# Domyślnie OpenRouter. Można wskazać inną bramkę z API zgodnym z OpenAI (np. LiteLLM albo
# lokalny model), wtedy dane w ogóle nie wychodzą do zewnętrznego dostawcy.
OPENROUTER_URL = os.environ.get(
    "OPENROUTER_URL", "https://openrouter.ai/api/v1/chat/completions"
).strip()
DEFAULT_MODEL = os.environ.get(
    "ASSISTANT_MODEL", "google/gemini-3.1-flash-lite-preview"
).strip()

SYSTEM_PROMPT = """Jesteś asystentem biznesowym agencji marketingowej w aplikacji PolCRM.
Masz dostęp do bazy: firm (CRM), zadań, finansów (faktury/koszty/subskrypcje), kalendarza, notatek.

ZASADY:
- Odpowiadaj po polsku, zwięźle, profesjonalnie.
- Używaj narzędzi, zanim zgadniesz. Jeśli użytkownik pyta "ile mam zaległych faktur" - wywołaj `list_overdue_payments`, a nie zmyślaj.
- Wartości pieniężne podawaj w formacie "1 234,56 zł".
- Daty po polsku (np. "15 kwietnia 2026").
- Gdy tworzysz coś (zadanie, płatność, notatkę) - potwierdź co zrobiłeś i daj link (np. "Utworzyłem zadanie #42 - zobacz: /tasks/42").
- Nie wykonuj akcji destrukcyjnych (usuwanie) - jeśli user tego chce, powiedz, żeby zrobił to ręcznie w UI.
- Jeśli user pyta o coś czego nie wiesz i nie masz narzędzia - szczerze powiedz.
- Gdy zadanie wymaga wielu kroków (np. "znajdź zaległe i dodaj im zadanie follow-up") - wykonaj je sekwencyjnie wywołując tools.
"""

# Ta sama treść dla osób z interfejsem po angielsku - wybierana w _run() wg języka żądania.
SYSTEM_PROMPT_EN = """You are the business assistant of a marketing agency in the PolCRM app.
You have access to the database: companies (CRM), tasks, finances (invoices/expenses/subscriptions), calendar, notes.

RULES:
- Answer in English, concisely and professionally.
- Use the tools before you guess. If the user asks "how many overdue invoices do I have", call `list_overdue_payments` instead of making things up.
- Give amounts of money in the format "1,234.56 zł".
- Write dates in English (e.g. "April 15, 2026").
- When you create something (a task, payment, note), confirm what you did and give a link (e.g. "I created task #42 - see: /tasks/42").
- Do not perform destructive actions (deleting) - if the user wants that, tell them to do it manually in the UI.
- If the user asks about something you do not know and have no tool for, say so honestly.
- When a request needs several steps (e.g. "find the overdue ones and add a follow-up task for each"), carry them out one after another by calling tools.
"""


def system_prompt(lang=None):
    """System prompt in the language of the current request (pl / en)."""
    return SYSTEM_PROMPT_EN if (lang or i18n.current_language()) == "en" else SYSTEM_PROMPT


# ═══════════════════════════════════════════════════════════════════
#  TOOL DEFINITIONS (OpenAI/OpenRouter format)
# ═══════════════════════════════════════════════════════════════════

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_tasks",
            "description": "Pobierz listę zadań. Filtruj po scope (today/week/overdue/all) i priorytecie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "scope": {
                        "type": "string",
                        "enum": ["today", "week", "overdue", "all"],
                        "description": "Zakres zadań. 'today'=dziś, 'week'=najbliższe 7 dni, 'overdue'=po terminie, 'all'=wszystkie aktywne.",
                    },
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                    },
                    "company_id": {"type": "integer"},
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_task",
            "description": "Utwórz nowe zadanie.",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {
                        "type": "string",
                        "enum": ["low", "medium", "high", "urgent"],
                        "default": "medium",
                    },
                    "deadline": {
                        "type": "string",
                        "description": "YYYY-MM-DD lub 'today', 'tomorrow', 'next_week'",
                    },
                    "company_id": {"type": "integer"},
                },
                "required": ["title"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "move_task",
            "description": "Przesuń zadanie do innej kolumny Kanban (zmienia deadline).",
            "parameters": {
                "type": "object",
                "properties": {
                    "task_id": {"type": "integer"},
                    "column": {
                        "type": "string",
                        "enum": ["overdue", "today", "week", "later", "done"],
                    },
                },
                "required": ["task_id", "column"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_companies",
            "description": "Pobierz listę firm. Opcjonalnie filtruj po nazwie lub etapie pipeline'u.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Fragment nazwy"},
                    "stage": {
                        "type": "string",
                        "enum": ["lead", "audit", "contact", "visit", "offer", "client"],
                    },
                    "limit": {"type": "integer", "default": 20},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_company",
            "description": "Pobierz szczegóły firmy (dane kontaktowe, retainer, ostatni audyt, ostatnie płatności).",
            "parameters": {
                "type": "object",
                "properties": {"company_id": {"type": "integer"}},
                "required": ["company_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_pipeline_stage",
            "description": "Zmień etap pipeline'u firmy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "stage": {
                        "type": "string",
                        "enum": ["lead", "audit", "contact", "visit", "offer", "client"],
                    },
                },
                "required": ["company_id", "stage"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_finances_summary",
            "description": "Podsumowanie finansowe miesiąca: przychody, koszty, bilans, MRR, kategorie kosztów.",
            "parameters": {
                "type": "object",
                "properties": {
                    "year": {"type": "integer"},
                    "month": {"type": "integer", "minimum": 1, "maximum": 12},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_overdue_payments",
            "description": "Lista zaległych płatności.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_payment",
            "description": "Utwórz nową płatność (fakturę) dla firmy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "company_id": {"type": "integer"},
                    "title": {"type": "string"},
                    "amount_net": {"type": "number"},
                    "vat_rate": {"type": "number", "default": 23},
                    "kind": {
                        "type": "string",
                        "enum": ["one_time", "retainer", "addon", "project_milestone"],
                        "default": "one_time",
                    },
                    "due_at": {"type": "string", "description": "YYYY-MM-DD"},
                },
                "required": ["company_id", "title", "amount_net"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_note",
            "description": "Dodaj notatkę (globalną lub przypisaną do firmy).",
            "parameters": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "content": {"type": "string"},
                    "company_id": {"type": "integer"},
                    "note_type": {"type": "string", "default": "general"},
                },
                "required": ["content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_global",
            "description": "Przeszukaj wszystko (firmy, zadania, notatki, projekty) po słowie kluczowym.",
            "parameters": {
                "type": "object",
                "properties": {"query": {"type": "string"}},
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_calendar",
            "description": "Nadchodzące wizyty i publikacje content w zakresie dni.",
            "parameters": {
                "type": "object",
                "properties": {
                    "days_ahead": {"type": "integer", "default": 14},
                },
            },
        },
    },
]


# ═══════════════════════════════════════════════════════════════════
#  TOOL HANDLERS
# ═══════════════════════════════════════════════════════════════════

# Każde narzędzie: (args z modelu, słownik modeli, db[, ...]) -> dict serializowalny do JSON.
# Argumenty przychodzą już odmaskowane (privacy.Masker.restore_data), a wynik jest maskowany
# przed wysłaniem do modelu - same narzędzia nie muszą wiedzieć o polanonie.

def _parse_deadline(s):
    """Termin z argumentu modelu: 'YYYY-MM-DD', 'today', 'tomorrow' albo 'next_week' -> date albo None."""
    if not s:
        return None
    s = s.strip().lower()
    today = date.today()
    if s == "today": return today
    if s == "tomorrow": return today + timedelta(days=1)
    if s == "next_week": return today + timedelta(days=7)
    try:
        return datetime.strptime(s, "%Y-%m-%d").date()
    except ValueError:
        return None


def _task_to_dict(t):
    """Zadanie w formie JSON dla modelu (bez opisu, z linkiem do UI)."""
    return {
        "id": t.id,
        "title": t.title,
        "status": t.status,
        "priority": t.priority,
        "deadline": t.deadline.isoformat() if t.deadline else None,
        "company_id": t.company_id,
        "company_name": t.company.name if t.company else None,
        "url": f"/tasks/{t.id}",
    }


def tool_list_tasks(args, models, db):
    """list_tasks: aktywne zadania wg zakresu (today/week/overdue/all) i priorytetu."""
    Task = models["Task"]
    q = Task.query.filter(Task.parent_task_id == None)
    scope = args.get("scope", "all")
    today = date.today()
    if scope == "today":
        q = q.filter(Task.status != "done", Task.deadline == today)
    elif scope == "week":
        q = q.filter(Task.status != "done", Task.deadline != None,
                     Task.deadline >= today, Task.deadline <= today + timedelta(days=7))
    elif scope == "overdue":
        q = q.filter(Task.status != "done", Task.deadline != None, Task.deadline < today)
    else:
        q = q.filter(Task.status != "done")
    if args.get("priority"):
        q = q.filter_by(priority=args["priority"])
    if args.get("company_id"):
        q = q.filter_by(company_id=args["company_id"])
    limit = min(args.get("limit", 20), 100)
    tasks = q.order_by(Task.deadline.asc()).limit(limit).all()
    return {"count": len(tasks), "tasks": [_task_to_dict(t) for t in tasks]}


def tool_create_task(args, models, db, user_id=None):
    """create_task: nowe zadanie (opcjonalnie z terminem, priorytetem i firmą); autor = bieżący profil."""
    Task = models["Task"]
    t = Task(
        title=args["title"],
        description=args.get("description", ""),
        priority=args.get("priority", "medium"),
        status="todo",
        deadline=_parse_deadline(args.get("deadline")),
        company_id=args.get("company_id"),
    )
    if user_id and hasattr(Task, "created_by_user_id"):
        t.created_by_user_id = user_id
    db.session.add(t)
    db.session.commit()
    return {"ok": True, "task_id": t.id, "url": f"/tasks/{t.id}",
            "message": f"Utworzono zadanie #{t.id}: {t.title}"}


def tool_move_task(args, models, db):
    """move_task: przesuwa zadanie między kolumnami kanbanu, czyli zmienia termin albo status."""
    Task = models["Task"]
    t = db.session.get(Task, args["task_id"])
    if not t:
        return {"error": "Zadanie nie istnieje"}
    col = args["column"]
    today = date.today()
    if col == "done":
        t.status = "done"; t.done_at = datetime.now(timezone.utc).replace(tzinfo=None)
    else:
        if t.status == "done":
            t.status = "todo"; t.done_at = None
        if col == "overdue": t.deadline = today - timedelta(days=1)
        elif col == "today": t.deadline = today
        elif col == "week": t.deadline = today + timedelta(days=3)
        elif col == "later": t.deadline = today + timedelta(days=14)
    db.session.commit()
    return {"ok": True, "status": t.status, "deadline": t.deadline.isoformat() if t.deadline else None}


def tool_list_companies(args, models, db):
    """list_companies: firmy z filtrem po nazwie/branży i etapie pipeline (limit 50)."""
    Company = models["Company"]
    q = Company.query
    if args.get("query"):
        like = f"%{args['query']}%"
        q = q.filter(or_(Company.name.ilike(like), Company.industry.ilike(like)))
    if args.get("stage"):
        q = q.filter_by(pipeline_stage=args["stage"])
    limit = min(args.get("limit", 20), 50)
    rows = q.order_by(Company.name).limit(limit).all()
    return {
        "count": len(rows),
        "companies": [
            {
                "id": c.id, "name": c.name, "industry": c.industry,
                "pipeline_stage": c.pipeline_stage,
                "is_retainer": c.is_retainer,
                "monthly_fee_net": c.monthly_fee_net,
                "url": f"/companies/{c.id}",
            } for c in rows
        ],
    }


def tool_get_company(args, models, db):
    """get_company: karta firmy z kontaktem, retainerem, ostatnim audytem i 5 ostatnimi płatnościami."""
    Company = models["Company"]
    c = db.session.get(Company, args["company_id"])
    if not c:
        return {"error": "Firma nie istnieje"}
    latest_audit = None
    if hasattr(c, "audits") and c.audits:
        la = sorted(c.audits, key=lambda a: a.created_at or datetime.min, reverse=True)[:1]
        if la:
            latest_audit = {"id": la[0].id, "score_overall": la[0].score_overall}
    recent_payments = []
    if hasattr(c, "payments"):
        for p in sorted(c.payments, key=lambda p: p.issued_at or date.min, reverse=True)[:5]:
            recent_payments.append({
                "id": p.id, "title": p.title, "status": p.status,
                "amount_gross": p.amount_gross, "due_at": p.due_at.isoformat() if p.due_at else None,
            })
    return {
        "id": c.id, "name": c.name, "industry": c.industry,
        "contact_email": getattr(c, "contact_email", None),
        "phone": getattr(c, "phone", None),
        "website": getattr(c, "website", None),
        "pipeline_stage": c.pipeline_stage,
        "is_retainer": c.is_retainer,
        "monthly_fee_net": c.monthly_fee_net,
        "next_action": getattr(c, "next_action", None),
        "next_action_date": c.next_action_date.isoformat() if getattr(c, "next_action_date", None) else None,
        "rating": getattr(c, "rating", None),
        "latest_audit": latest_audit,
        "recent_payments": recent_payments,
        "url": f"/companies/{c.id}",
    }


def tool_update_pipeline_stage(args, models, db):
    """update_pipeline_stage: zmienia etap firmy w lejku sprzedaży."""
    Company = models["Company"]
    c = db.session.get(Company, args["company_id"])
    if not c:
        return {"error": "Firma nie istnieje"}
    c.pipeline_stage = args["stage"]
    db.session.commit()
    return {"ok": True, "company_id": c.id, "stage": c.pipeline_stage}


def tool_get_finances_summary(args, models, db, finance_helpers):
    """get_finances_summary: bilans miesiąca (przychody, koszty, subskrypcje, MRR) z finance_helpers."""
    today = date.today()
    year = args.get("year") or today.year
    month = args.get("month") or today.month
    bal = finance_helpers.monthly_balance(year, month)
    overdue = finance_helpers.overdue_payments_summary()
    cat = finance_helpers.expense_category_breakdown(year, month)
    return {
        "year": year, "month": month, "month_label": bal["month_label"],
        "revenue_total": bal["revenue_total"],
        "expense_total": bal["expense_total"],
        "subscription_allocation": bal["subscription_allocation"],
        "balance": bal["balance"],
        "overdue_count": overdue["count"],
        "overdue_total_gross": overdue["total_gross"],
        "expense_categories": cat,
    }


def tool_list_overdue_payments(args, models, db):
    """list_overdue_payments: zaległe płatności (status overdue) z sumą brutto i terminami."""
    Payment = models["Payment"]
    rows = Payment.query.filter_by(status="overdue").all()
    return {
        "count": len(rows),
        "total_gross": sum(p.amount_gross or 0 for p in rows),
        "payments": [
            {
                "id": p.id, "payment_number": p.payment_number, "title": p.title,
                "company_id": p.company_id,
                "company_name": p.company.name if p.company else None,
                "amount_gross": p.amount_gross,
                "due_at": p.due_at.isoformat() if p.due_at else None,
                "url": f"/finances/payments/{p.id}/edit",
            } for p in rows
        ],
    }


def tool_create_payment(args, models, db, finance_helpers, user_id=None):
    """create_payment: nowa płatność (faktura) z numerem P-RRRR-NNNN i przeliczeniem brutto."""
    Payment = models["Payment"]
    p = Payment(
        company_id=args["company_id"],
        title=args["title"],
        amount_net=float(args["amount_net"]),
        vat_rate=float(args.get("vat_rate", 23)),
        kind=args.get("kind", "one_time"),
        status="unpaid",
        issued_at=date.today(),
        due_at=_parse_deadline(args.get("due_at")) or (date.today() + timedelta(days=14)),
    )
    p.payment_number = finance_helpers.next_payment_number()
    p.recompute_gross()
    if user_id and hasattr(Payment, "created_by_user_id"):
        p.created_by_user_id = user_id
    db.session.add(p)
    db.session.commit()
    return {"ok": True, "payment_id": p.id, "payment_number": p.payment_number,
            "amount_gross": p.amount_gross,
            "url": f"/finances/payments/{p.id}/edit",
            "message": f"Utworzono płatność {p.payment_number}"}


def tool_add_note(args, models, db, user_id=None):
    """add_note: notatka osobista albo przypięta do firmy."""
    Note = models["Note"]
    n = Note(
        title=args.get("title", "")[:200],
        content=args["content"],
        company_id=args.get("company_id"),
        note_type=args.get("note_type", "general"),
    )
    if user_id and hasattr(Note, "created_by_user_id"):
        n.created_by_user_id = user_id
    if hasattr(Note, "scope"):
        n.scope = "company" if args.get("company_id") else "personal"
    db.session.add(n)
    db.session.commit()
    return {"ok": True, "note_id": n.id,
            "url": f"/notes/{n.id}/edit" if not args.get("company_id") else f"/companies/{args['company_id']}",
            "message": "Dodano notatkę"}


def tool_search_global(args, models, db):
    """search_global: wyszukiwanie po firmach, zadaniach, notatkach i projektach."""
    q = args["query"].strip()
    if not q:
        return {"results": []}
    like = f"%{q}%"
    Company = models["Company"]; Task = models["Task"]; Note = models["Note"]
    results = []
    for c in Company.query.filter(Company.name.ilike(like)).limit(5).all():
        results.append({"type": "company", "id": c.id, "title": c.name, "url": f"/companies/{c.id}"})
    for t in Task.query.filter(Task.title.ilike(like)).limit(5).all():
        results.append({"type": "task", "id": t.id, "title": t.title, "url": f"/tasks/{t.id}"})
    for n in Note.query.filter(or_(Note.title.ilike(like), Note.content.ilike(like))).limit(5).all():
        results.append({"type": "note", "id": n.id, "title": n.title or n.content[:80], "url": f"/notes/{n.id}/edit"})
    return {"count": len(results), "results": results}


def tool_list_calendar(args, models, db):
    """list_calendar: nadchodzące wizyty i publikacje contentu w zadanym zakresie dni."""
    Visit = models.get("Visit")
    ContentPost = models.get("ContentPost")
    today = date.today()
    days = args.get("days_ahead", 14)
    end = today + timedelta(days=days)
    visits = []
    content = []
    if Visit:
        rows = Visit.query.filter(
            Visit.scheduled_at >= datetime.combine(today, datetime.min.time()),
            Visit.scheduled_at <= datetime.combine(end, datetime.max.time()),
        ).order_by(Visit.scheduled_at).all()
        for v in rows:
            visits.append({
                "id": v.id, "company_name": v.company.name if v.company else None,
                "scheduled_at": v.scheduled_at.isoformat(),
                "type_label": getattr(v, "type_label", None),
                "url": f"/visits/{v.id}",
            })
    if ContentPost:
        rows = ContentPost.query.filter(
            ContentPost.deadline >= today, ContentPost.deadline <= end,
        ).order_by(ContentPost.deadline).all()
        for p in rows:
            content.append({
                "id": p.id, "title": p.title, "deadline": p.deadline.isoformat(),
                "company_name": p.company.name if p.company else None,
                "status": p.status,
                "url": f"/content/{p.id}/edit",
            })
    return {"visits": visits, "content_posts": content}


# ═══════════════════════════════════════════════════════════════════
#  DISPATCH
# ═══════════════════════════════════════════════════════════════════

def execute_tool(name, args, models, db, finance_helpers, user_id=None):
    """Wywołaj narzędzie po nazwie. Zawsze zwraca dict gotowy do json.dumps;
    błąd narzędzia wraca do modelu jako {"error": ...}, a nie jako wyjątek, żeby pętla
    mogła kontynuować (model zwykle poprawia argumenty w kolejnym kroku)."""
    try:
        if name == "list_tasks": return tool_list_tasks(args, models, db)
        if name == "create_task": return tool_create_task(args, models, db, user_id)
        if name == "move_task": return tool_move_task(args, models, db)
        if name == "list_companies": return tool_list_companies(args, models, db)
        if name == "get_company": return tool_get_company(args, models, db)
        if name == "update_pipeline_stage": return tool_update_pipeline_stage(args, models, db)
        if name == "get_finances_summary": return tool_get_finances_summary(args, models, db, finance_helpers)
        if name == "list_overdue_payments": return tool_list_overdue_payments(args, models, db)
        if name == "create_payment": return tool_create_payment(args, models, db, finance_helpers, user_id)
        if name == "add_note": return tool_add_note(args, models, db, user_id)
        if name == "search_global": return tool_search_global(args, models, db)
        if name == "list_calendar": return tool_list_calendar(args, models, db)
        return {"error": f"Nieznane narzędzie: {name}"}
    except Exception as e:
        return {"error": f"Błąd wykonania {name}: {str(e)}"}


# ═══════════════════════════════════════════════════════════════════
#  CHAT (OpenRouter, odpowiedź bez streamingu)
# ═══════════════════════════════════════════════════════════════════

def _build_context_prefix(lang=None):
    """Szybki kontekst - dzisiejsza data, dzień tygodnia (po polsku albo po angielsku)."""
    today = date.today()
    if (lang or i18n.current_language()) == "en":
        return f"Today: {today.isoformat()} ({i18n.WEEKDAYS['en'][today.weekday()]})."
    DNI = ["poniedziałek", "wtorek", "środa", "czwartek", "piątek", "sobota", "niedziela"]
    return f"Dzisiaj: {today.isoformat()} ({DNI[today.weekday()]})."


def _resolve_api_key():
    """Zrodlo klucza w kolejnosci: Settings (DB, zaszyfrowane Fernet) -> ENV."""
    # 1. Settings z bazy (UI w Ustawienia → AI Asystent)
    try:
        from models import Settings
        from email_sender import decrypt_password
        s = Settings.get()
        if s.openrouter_api_key_encrypted:
            try:
                k = decrypt_password(s.openrouter_api_key_encrypted)
                if k:
                    return k.strip()
            except Exception:
                pass
    except Exception:
        pass
    # 2. ENV (legacy / fallback)
    return os.environ.get("OPENROUTER_API_KEY", "").strip()


def _resolve_model():
    """Model w kolejnosci: Settings.assistant_model -> ENV -> default."""
    try:
        from models import Settings
        s = Settings.get()
        if s.assistant_model:
            return s.assistant_model
    except Exception:
        pass
    return DEFAULT_MODEL


def call_model(messages, model=None, tools=TOOLS, api_key=None):
    """Synchroniczne wywołanie OpenRouter. Zwraca dict z choices[0].message."""
    api_key = (api_key or "").strip() or _resolve_api_key()
    if not api_key:
        raise RuntimeError(_("Brak klucza OpenRouter - wpisz go w Ustawienia → AI Asystent."))
    model = model or _resolve_model()

    payload = {
        "model": model,
        "messages": messages,
        "tools": tools,
        "tool_choice": "auto",
        "temperature": 0.3,
        "max_tokens": 1024,
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": os.environ.get("APP_URL", "http://localhost:4666"),
        "X-Title": "PolCRM",
    }
    r = requests.post(OPENROUTER_URL, json=payload, headers=headers, timeout=60)
    if r.status_code != 200:
        raise RuntimeError(f"OpenRouter {r.status_code}: {r.text[:500]}")
    return r.json()


def build_masker(settings=None):
    """Masker for one request when PII masking is switched on in Settings, otherwise None.

    Raises privacy.MaskingUnavailable when masking is on but polanon cannot run, so the caller
    can refuse to contact the model.
    """
    if settings is None:
        from models import Settings
        settings = Settings.get()
    if not getattr(settings, "pii_masking_enabled", False):
        return None
    with_ner = bool(getattr(settings, "pii_masking_ner", False))
    privacy.ensure_available(with_ner)  # najpierw polanon: bez niego nie ma po co czytać bazy
    from models import Company
    terms = privacy.client_terms(Company.query.with_entities(Company.name, Company.client_legal_name).all())
    return privacy.polanon_masker(with_ner=with_ner, terms=terms)


def run_conversation(user_message, history, models, db, finance_helpers, user_id=None,
                     max_iterations=6, masker=None, call=None):
    """
    Pełny cykl: wywołuje model, wykonuje tools, zwraca finalną odpowiedź tekstową.

    history: lista [{role, content}] z poprzednich tur (z prawdziwymi wartościami).
    masker:  privacy.Masker albo None. Gdy jest podany, do modelu idą tylko tokeny
             (pytanie, historia i wyniki narzędzi), a argumenty narzędzi i odpowiedź
             są odtwarzane lokalnie. Błąd maskowania = nic nie wychodzi do modelu.
    call:    funkcja wywołująca model (domyślnie call_model) - podmieniana w testach.

    Zwraca: {"reply": str, "tools_called": [...], "error": None | str, "masked": int}
    """
    call = call or call_model
    tools_called = []
    try:
        return _run(user_message, history, models, db, finance_helpers, user_id,
                    max_iterations, masker, call, tools_called)
    except privacy.MaskingUnavailable as e:
        return {
            "reply": _("Maskowanie danych osobowych (polanon) jest włączone, ale nie działa: "
                       "%(error)s. Nic nie zostało wysłane do AI. Napraw to albo wyłącz maskowanie "
                       "w Ustawienia → AI Asystent.", error=e),
            "tools_called": tools_called,
            "error": "masking_unavailable",
            "masked": 0,
        }


def _run(user_message, history, models, db, finance_helpers, user_id,
         max_iterations, masker, call, tools_called):
    out = masker.mask if masker else (lambda t: t)          # real -> tokens (to the model)
    back = masker.restore if masker else (lambda t: t)      # tokens -> real (from the model)

    lang = i18n.current_language()
    system = system_prompt(lang) + "\n\n" + _build_context_prefix(lang)
    if masker:
        system += privacy.tokens_note(lang)
    messages = [{"role": "system", "content": system}]
    for h in history[-10:]:  # ostatnie 10 wpisów, żeby nie rozdmuchać kontekstu
        if h.get("role") in ("user", "assistant"):
            messages.append({"role": h["role"], "content": out(h.get("content", ""))})
    messages.append({"role": "user", "content": out(user_message)})

    def _result(reply, error=None):
        return {"reply": reply, "tools_called": tools_called, "error": error,
                "masked": len(masker.mapping) if masker else 0}

    for _iteration in range(max_iterations):
        try:
            resp = call(messages)
        except Exception as e:
            return _result(_("Błąd API: %(error)s", error=e), str(e))

        choices = resp.get("choices") or []
        if not choices:
            return _result(_("Brak odpowiedzi od modelu."), "empty choices")
        msg = choices[0].get("message") or {}

        tool_calls = msg.get("tool_calls") or []
        if tool_calls:
            messages.append({
                "role": "assistant",
                "content": msg.get("content") or "",
                "tool_calls": tool_calls,
            })
            for tc in tool_calls:
                fn = tc.get("function", {})
                name = fn.get("name", "")
                try:
                    args = json.loads(fn.get("arguments", "{}") or "{}")
                except json.JSONDecodeError:
                    args = {}
                if masker:
                    args = masker.restore_data(args)
                result = execute_tool(name, args, models, db, finance_helpers, user_id)
                tools_called.append({"name": name, "args": args, "result": result})
                sent = masker.mask_data(result) if masker else result
                messages.append({
                    "role": "tool",
                    "tool_call_id": tc.get("id"),
                    "content": json.dumps(sent, ensure_ascii=False, default=str),
                })
            continue

        reply = msg.get("content") or ""
        if masker:
            unknown = masker.unknown_tokens(reply)
            if unknown:
                log.warning("polanon: %d token(s) in the answer are not in the mapping", len(unknown))
        return _result(back(reply))

    return _result(_("Przerwano po %(n)s iteracjach narzędzi - za skomplikowane zadanie.", n=max_iterations),
                   "max_iterations")
