"""AI assistant JSON API (tool calling, optional PII masking)."""

import os

from flask import jsonify, request, session

import ai_assistant
import finance_helpers as _finance_helpers_module
import privacy
from core import (
    app,
    get_current_user,
)
from i18n import _
from models import (
    Company,
    ContentPost,
    Expense,
    Note,
    Payment,
    Project,
    Settings,
    Task,
    Visit,
    db,
)

_ASSISTANT_MODELS = {
    "Task": Task, "Company": Company, "Payment": Payment,
    "Expense": Expense, "Note": Note, "Visit": Visit,
    "ContentPost": ContentPost, "Project": Project,
}


_HISTORY_ENTRIES = 8          # 4 tury pytanie + odpowiedź
_HISTORY_ENTRY_CHARS = 600


@app.route("/api/assistant/chat", methods=["POST"])
def api_assistant_chat():
    s = Settings.get()
    has_key = bool(s.openrouter_api_key_encrypted) or bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    if not has_key:
        return jsonify({"error": _("Asystent nie ma klucza API. Wpisz go w Ustawienia → AI Asystent.")}), 503
    if not s.assistant_enabled:
        return jsonify({"error": _("Asystent jest wyłączony. Włącz go w Ustawienia → AI Asystent.")}), 503

    user = get_current_user()
    data = request.get_json() or {}
    message = (data.get("message") or "").strip()
    if not message:
        return jsonify({"error": _("Pusty komunikat")}), 400
    if len(message) > 4000:
        return jsonify({"error": _("Komunikat za długi (max 4000 znaków)")}), 400

    # Historia w sesji: ostatnie _HISTORY_ENTRIES wpisów (4 tury pytanie + odpowiedź)
    history = session.get("assistant_history", [])

    try:
        masker = ai_assistant.build_masker(s)
    except privacy.MaskingUnavailable as e:
        return jsonify({"error": _("Maskowanie danych osobowych jest włączone, ale nie działa: %(error)s. "
                                   "Nic nie zostało wysłane do AI.", error=e)}), 503

    result = ai_assistant.run_conversation(
        user_message=message,
        history=history,
        models=_ASSISTANT_MODELS,
        db=db,
        finance_helpers=_finance_helpers_module,
        user_id=user.id if user else None,
        masker=masker,
    )

    # Historia jest w podpisanym ciasteczku sesji (limit ~4 KB), więc trzymamy
    # tylko ostatnie wpisy i przycinamy długie odpowiedzi.
    history.append({"role": "user", "content": message[:_HISTORY_ENTRY_CHARS]})
    history.append({"role": "assistant", "content": (result["reply"] or "")[:_HISTORY_ENTRY_CHARS]})
    session["assistant_history"] = history[-_HISTORY_ENTRIES:]

    return jsonify({
        "reply": result["reply"],
        "tools_called": [t["name"] for t in result["tools_called"]],
        "error": result.get("error"),
        "masked": result.get("masked", 0),
    })


@app.route("/api/assistant/reset", methods=["POST"])
def api_assistant_reset():
    session.pop("assistant_history", None)
    return jsonify({"ok": True})


@app.route("/api/assistant/status")
def api_assistant_status():
    s = Settings.get()
    has_key_db = bool(s.openrouter_api_key_encrypted)
    has_key_env = bool(os.environ.get("OPENROUTER_API_KEY", "").strip())
    configured = (has_key_db or has_key_env) and s.assistant_enabled
    return jsonify({
        "configured": configured,
        "enabled": bool(s.assistant_enabled),
        "has_key": has_key_db or has_key_env,
        "model": s.assistant_model if configured else None,
        "pii_masking": bool(s.pii_masking_enabled),
    })
