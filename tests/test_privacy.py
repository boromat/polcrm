"""PII masking in the assistant loop, tested with a fake anonymizer (no polanon needed).

The fake masks a fixed list of values, which is enough to check the contract that matters:
what reaches the model, what reaches the tools and what reaches the user.
"""

import json

import pytest

import ai_assistant
import privacy

SECRETS = {
    "Jan Kowalski": "OSOBA",
    "kontakt@dentysta-kowalski.example": "EMAIL",
    "+48 501 234 567": "TELEFON",
}


def fake_anonymize(text, mapping):
    mapping = dict(mapping)
    by_value = {v: k for k, v in mapping.items()}
    for value, label in SECRETS.items():
        if value in text:
            token = by_value.get(value)
            if token is None:
                n = 1 + sum(1 for t in mapping if t.startswith(f"<{label}_"))
                token = f"<{label}_{n}>"
                mapping[token] = value
                by_value[value] = token
            text = text.replace(value, token)
    return text, mapping


def make_masker():
    return privacy.Masker(anonymize=fake_anonymize)


class FakeModel:
    """Scripted OpenRouter: returns the queued responses and records every request."""

    def __init__(self, *responses):
        self.responses = list(responses)
        self.requests = []

    def __call__(self, messages):
        self.requests.append(json.loads(json.dumps(messages)))
        return self.responses.pop(0)

    def sent_text(self):
        return json.dumps(self.requests, ensure_ascii=False)


def answer(text):
    return {"choices": [{"message": {"content": text}}]}


def tool_call(name, args, call_id="call_1"):
    return {
        "choices": [
            {
                "message": {
                    "content": "",
                    "tool_calls": [
                        {
                            "id": call_id,
                            "type": "function",
                            "function": {"name": name, "arguments": json.dumps(args, ensure_ascii=False)},
                        },
                    ],
                }
            }
        ]
    }


# ── Masker ──────────────────────────────────────────────────────


def test_mask_and_restore_round_trip():
    m = make_masker()
    masked = m.mask("Zadzwoń do Jan Kowalski: +48 501 234 567")
    assert masked == "Zadzwoń do <OSOBA_1>: <TELEFON_1>"
    assert m.restore("Gotowe, <OSOBA_1> oddzwoni.") == "Gotowe, Jan Kowalski oddzwoni."


def test_tokens_stay_consistent_across_texts():
    m = make_masker()
    assert m.mask("Jan Kowalski") == "<OSOBA_1>"
    assert m.mask("Spotkanie: Jan Kowalski") == "Spotkanie: <OSOBA_1>"
    assert len(m.mapping) == 1


def test_mask_data_keeps_keys_numbers_and_structure():
    m = make_masker()
    data = {"id": 7, "contact": "Jan Kowalski", "tags": ["vip", "Jan Kowalski"], "fee": 1500.0, "x": None}
    assert m.mask_data(data) == {
        "id": 7,
        "contact": "<OSOBA_1>",
        "tags": ["vip", "<OSOBA_1>"],
        "fee": 1500.0,
        "x": None,
    }


def test_restore_data_in_nested_tool_arguments():
    m = make_masker()
    m.mask("Jan Kowalski")
    assert m.restore_data({"content": "Oddzwonić do <OSOBA_1>", "company_id": 3}) == {
        "content": "Oddzwonić do Jan Kowalski",
        "company_id": 3,
    }


def test_unknown_tokens_are_left_untouched_and_reported():
    m = make_masker()
    m.mask("Jan Kowalski")
    assert m.restore("<OSOBA_1> i <OSOBA_9>") == "Jan Kowalski i <OSOBA_9>"
    assert m.unknown_tokens("<OSOBA_1> i <OSOBA_9>") == ["<OSOBA_9>"]


# ── A person named again in another case (polanon 0.4) ────────


def test_a_token_with_a_case_comes_back_declined_in_the_answer():
    """polanon 0.4 masks a person named again in another case as <OSOBA_1:celownik>, and the model
    writes the token as it got it. The restore read only tokens without a case, so the user saw
    the token itself instead of the name."""
    m = make_masker()
    m.mask("Jan Kowalski zamówił audyt.")
    reply = "Wysłałem <OSOBA_1:celownik> ofertę."
    assert m.restore(reply) == "Wysłałem Janowi Kowalskiemu ofertę."
    assert m.unknown_tokens(reply) == []


def test_a_token_with_a_case_in_tool_arguments_gives_the_name_as_written():
    """A tool searches the database, which holds the name as it was written, not declined."""
    m = make_masker()
    m.mask("Jan Kowalski")
    assert m.restore_data({"query": "<OSOBA_1:dopełniacz>", "limit": 5}) == {"query": "Jan Kowalski", "limit": 5}


def test_an_unknown_token_with_a_case_is_left_and_reported():
    m = make_masker()
    m.mask("Jan Kowalski")
    assert m.restore("<OSOBA_9:celownik>") == "<OSOBA_9:celownik>"
    assert m.unknown_tokens("<OSOBA_1:celownik> i <OSOBA_9:celownik>") == ["<OSOBA_9:celownik>"]


def test_anonymizer_crash_becomes_masking_unavailable():
    def broken(text, mapping):
        raise ValueError("boom")

    m = privacy.Masker(anonymize=broken)
    with pytest.raises(privacy.MaskingUnavailable):
        m.mask("Jan Kowalski")


# ── run_conversation with masking ──────────────────────────────


def test_model_never_sees_real_values(monkeypatch):
    seen_args = []

    def fake_execute(name, args, *a, **kw):
        seen_args.append(args)
        return {
            "companies": [
                {
                    "id": 1,
                    "name": "Gabinet",
                    "contact_person": "Jan Kowalski",
                    "contact_email": "kontakt@dentysta-kowalski.example",
                }
            ]
        }

    monkeypatch.setattr(ai_assistant, "execute_tool", fake_execute)
    model = FakeModel(
        tool_call("list_companies", {"query": "<OSOBA_1>"}),
        answer("Kontakt: <OSOBA_1>, <EMAIL_1>."),
    )
    history = [
        {"role": "user", "content": "Kto to +48 501 234 567?"},
        {"role": "assistant", "content": "To numer, który podał Jan Kowalski."},
    ]
    result = ai_assistant.run_conversation(
        "Znajdź firmę Jan Kowalski", history, models={}, db=None, finance_helpers=None, masker=make_masker(), call=model
    )

    sent = model.sent_text()
    for value in SECRETS:
        assert value not in sent, f"{value!r} leaked to the model"
    assert "<OSOBA_1>" in sent and "<EMAIL_1>" in sent
    assert "ZAMASKOWANE" in model.requests[0][0]["content"]  # system prompt explains tokens
    # the tool got the real value back, the user got the real answer back
    assert seen_args == [{"query": "Jan Kowalski"}]
    assert result["reply"] == "Kontakt: Jan Kowalski, kontakt@dentysta-kowalski.example."
    assert result["error"] is None
    assert result["masked"] == 3
    # the local trace keeps real values (it never leaves the server)
    assert result["tools_called"][0]["result"]["companies"][0]["contact_person"] == "Jan Kowalski"


def test_a_token_with_a_case_reaches_the_tool_as_written_and_the_user_declined(monkeypatch):
    seen_args = []

    def fake_execute(name, args, *a, **kw):
        seen_args.append(args)
        return {"companies": [{"id": 1, "name": "Gabinet", "contact_person": "Jan Kowalski"}]}

    monkeypatch.setattr(ai_assistant, "execute_tool", fake_execute)
    model = FakeModel(
        tool_call("list_companies", {"query": "<OSOBA_1:dopełniacz>"}),
        answer("Wyślę <OSOBA_1:celownik> ofertę."),
    )
    result = ai_assistant.run_conversation(
        "Znajdź Jan Kowalski", [], models={}, db=None, finance_helpers=None, masker=make_masker(), call=model
    )

    assert seen_args == [{"query": "Jan Kowalski"}]
    assert result["reply"] == "Wyślę Janowi Kowalskiemu ofertę."
    assert result["error"] is None


def test_masking_failure_sends_nothing():
    def broken(text, mapping):
        raise RuntimeError("polanon crashed")

    model = FakeModel(answer("should not be called"))
    result = ai_assistant.run_conversation(
        "Jan Kowalski",
        [],
        models={},
        db=None,
        finance_helpers=None,
        masker=privacy.Masker(anonymize=broken),
        call=model,
    )
    assert model.requests == []
    assert result["error"] == "masking_unavailable"
    assert "Nic nie zostało wysłane" in result["reply"]


def test_failure_while_masking_a_tool_result_stops_before_next_call(monkeypatch):
    calls = {"n": 0}

    def flaky(text, mapping):
        calls["n"] += 1
        if "WYNIK" in text:
            raise RuntimeError("boom")
        return fake_anonymize(text, mapping)

    monkeypatch.setattr(ai_assistant, "execute_tool", lambda *a, **k: {"note": "WYNIK Jan Kowalski"})
    model = FakeModel(tool_call("search_global", {"query": "x"}), answer("nie powinno dojść"))
    result = ai_assistant.run_conversation(
        "szukaj", [], models={}, db=None, finance_helpers=None, masker=privacy.Masker(anonymize=flaky), call=model
    )
    assert len(model.requests) == 1  # the tool result never went out
    assert result["error"] == "masking_unavailable"


def test_without_masker_behaviour_is_unchanged():
    model = FakeModel(answer("Cześć Jan Kowalski"))
    result = ai_assistant.run_conversation(
        "Jestem Jan Kowalski", [], models={}, db=None, finance_helpers=None, call=model
    )
    assert "Jan Kowalski" in model.sent_text()
    assert "ZAMASKOWANE" not in model.requests[0][0]["content"]
    assert result["reply"] == "Cześć Jan Kowalski"
    assert result["masked"] == 0


def test_max_iterations_message_uses_the_limit(monkeypatch):
    monkeypatch.setattr(ai_assistant, "execute_tool", lambda *a, **k: {"ok": True})
    model = FakeModel(*[tool_call("list_tasks", {}, f"c{i}") for i in range(3)])
    result = ai_assistant.run_conversation(
        "pętla", [], models={}, db=None, finance_helpers=None, call=model, max_iterations=3
    )
    assert result["error"] == "max_iterations"
    assert "3 iteracjach" in result["reply"]


# ── build_masker / settings ─────────────────────────────────────


class _Settings:
    def __init__(self, enabled, ner=False):
        self.pii_masking_enabled = enabled
        self.pii_masking_ner = ner


def test_build_masker_off_returns_none():
    assert ai_assistant.build_masker(_Settings(False)) is None


def test_build_masker_on_without_polanon_fails_closed(monkeypatch):
    def missing(with_ner):
        raise privacy.MaskingUnavailable("pakiet polanon nie jest zainstalowany")

    monkeypatch.setattr(privacy, "_get_anonymizer", missing)
    with pytest.raises(privacy.MaskingUnavailable):
        ai_assistant.build_masker(_Settings(True))


def test_polanon_status_shape():
    status = privacy.polanon_status()
    assert set(status) == {"installed", "version", "ner"}


def test_client_terms_include_legal_name_and_name_without_tag():
    class _C:
        def __init__(self, name, legal=""):
            self.name, self.client_legal_name = name, legal

    terms = privacy.client_terms([_C("[TEST] Pizzeria Bella", "Bella Sp. z o.o."), _C("Kancelaria", None)])
    assert terms == ["[TEST] Pizzeria Bella", "Pizzeria Bella", "Bella Sp. z o.o.", "Kancelaria"]
