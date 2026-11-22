"""The same contract with the real polanon (skipped when it is not installed).

CI installs polanon, so these run on every push.
"""

import json
import re

import pytest

pytest.importorskip("polanon")

import ai_assistant  # noqa: E402
import privacy  # noqa: E402

TEXT = (
    "Klient Jan Kowalski (jan.kowalski@example.com, tel. 501 234 567) prosi o fakturę "
    "na konto PL61 1090 1014 0000 0712 1981 2874."
)
REAL_VALUES = ["Jan Kowalski", "jan.kowalski@example.com", "501 234 567", "1090 1014 0000 0712 1981 2874"]


def test_polanon_masks_polish_pii_and_restores_it():
    m = privacy.polanon_masker()
    masked = m.mask(TEXT)
    for value in REAL_VALUES:
        assert value not in masked
    assert privacy.TOKEN_RE.search(masked)
    assert m.restore(masked) == TEXT


def test_polanon_keeps_tokens_consistent_within_a_request():
    m = privacy.polanon_masker()
    first = m.mask("Spotkanie: Jan Kowalski, piątek.")
    second = m.mask("Jan Kowalski potwierdził spotkanie.")
    tokens_first = set(privacy.TOKEN_RE.findall(first))
    tokens_second = set(privacy.TOKEN_RE.findall(second))
    assert tokens_first and tokens_second
    assert tokens_first & tokens_second, "the same person should get the same token"


def test_full_loop_with_polanon(monkeypatch):
    seen = []
    monkeypatch.setattr(
        ai_assistant,
        "execute_tool",
        lambda name, args, *a, **k: seen.append(args) or {"contact": "jan.kowalski@example.com"},
    )
    requests = []

    def model(messages):
        requests.append(json.dumps(messages, ensure_ascii=False))
        if len(requests) == 1:
            token = privacy.TOKEN_RE.findall(messages[-1]["content"])[0]
            return {
                "choices": [
                    {
                        "message": {
                            "content": "",
                            "tool_calls": [
                                {
                                    "id": "c1",
                                    "type": "function",
                                    "function": {"name": "search_global", "arguments": json.dumps({"query": token})},
                                }
                            ],
                        }
                    }
                ]
            }
        token = privacy.TOKEN_RE.findall(messages[-1]["content"])[0]
        return {"choices": [{"message": {"content": f"Mail: {token}"}}]}

    result = ai_assistant.run_conversation(
        "Znajdź Jan Kowalski", [], models={}, db=None, finance_helpers=None, masker=privacy.polanon_masker(), call=model
    )

    assert all("Jan Kowalski" not in r and "jan.kowalski@example.com" not in r for r in requests)
    assert "Kowalski" in seen[0]["query"]
    assert result["reply"] == "Mail: jan.kowalski@example.com"


def test_a_surname_the_question_names_is_masked_in_the_history_too():
    """The history went out message by message, so "Testowski" alone in an earlier one, which no
    rule reads as a person, reached the model before the question named "Jan Testowski"."""
    requests = []

    def model(messages):
        requests.append(json.dumps(messages, ensure_ascii=False))
        return {"choices": [{"message": {"content": "Gotowe."}}]}

    history = [{"role": "user", "content": "Testowski dzwonił wczoraj w sprawie audytu."}]
    result = ai_assistant.run_conversation(
        "Co z Jan Testowski?",
        history,
        models={},
        db=None,
        finance_helpers=None,
        masker=privacy.polanon_masker(),
        call=model,
    )

    assert result["error"] is None
    assert "Testowski" not in requests[0]


def test_known_client_names_are_always_masked():
    """A tool result field holds just the company name, with no context. polanon's rules cannot
    tell "Auto Serwis Nowak" is sensitive there, so the CRM passes its client names as known terms."""

    class _Company:
        name = "[TEST] Auto Serwis Nowak"
        client_legal_name = "AUTO-NOWAK Piotr Nowak"

    terms = privacy.client_terms([_Company()])
    assert "Auto Serwis Nowak" in terms  # also without the [TEST] prefix

    m = privacy.polanon_masker(terms=terms)
    data = m.mask_data({"company_name": "[TEST] Auto Serwis Nowak", "title": "Abonament"})
    assert "Nowak" not in json.dumps(data, ensure_ascii=False)
    assert m.restore_data(data)["company_name"] == "[TEST] Auto Serwis Nowak"
    assert "Auto Serwis" not in m.mask("Czy Auto Serwis Nowak zapłacił?")


def test_client_named_like_a_public_brand_is_still_masked():
    """polanon leaves well-known names (e.g. Facebook) unmasked; a client of the agency must not be."""
    m = privacy.polanon_masker(terms=["Facebook Studio"])
    assert "Facebook" not in m.mask("Zaległa faktura: Facebook Studio, termin piątek.")


def test_client_whose_whole_name_is_on_the_allowlist_is_still_masked():
    """Every word of "Gemini" is a well-known name, so polanon's allowlist would let it through;
    PolCRM took the words of client names out of the allowlist for it. polanon 0.4.2 never lets the
    allowlist drop what its denylist, fed with MaskedTurn(known=...), found."""
    m = privacy.polanon_masker(terms=["Gemini"])
    assert "Gemini" not in m.mask("Zaległa faktura: Gemini, termin piątek.")
    assert "Gemini" in privacy.polanon_masker().mask("Zapytaj Gemini o termin.")


def test_client_name_without_its_legal_form_is_masked():
    """polanon 0.4.2: a known company is found without the legal form the CRM lists it with."""
    m = privacy.polanon_masker(terms=["Kwiaciarnia Testowa Sp. z o.o."])
    masked = m.mask("Zaległa faktura: Kwiaciarnia Testowa, termin piątek.")
    assert "Kwiaciarnia" not in masked and "Testowa" not in masked


def test_a_token_from_an_earlier_request_is_defused_also_after_this_one_handed_it_out():
    """polanon keeps a token the caller wrote as standing for itself only when it comes before the
    turn hands the same token out. A note saved with a token from an earlier request arrives in a
    tool result after that, and polanon would read it as this request's person."""
    m = privacy.polanon_masker()
    assert m.mask("Co z Jan Kowalski?") == "Co z <OSOBA_1>?"
    sent = m.mask_data({"note": "Oddzwonić do <OSOBA_1>"})
    assert sent == {"note": "Oddzwonić do [OSOBA_1]"}
    assert m.restore(sent["note"]) == "Oddzwonić do [OSOBA_1]"


def test_a_person_named_again_in_another_case_comes_back_declined():
    """polanon 0.4 masks the second mention as <OSOBA_1:celownik>; the answer shows the name."""
    m = privacy.polanon_masker()
    assert m.mask("Jan Testowski zamówił audyt strony.") == "<OSOBA_1> zamówił audyt strony."
    masked = m.mask("Wyślij Janowi Testowskiemu ofertę.")
    assert masked == "Wyślij <OSOBA_1:celownik> ofertę."
    assert m.restore(masked) == "Wyślij Janowi Testowskiemu ofertę."
    assert m.restore_data({"query": "<OSOBA_1:celownik>"}) == {"query": "Jan Testowski"}
    assert m.unknown_tokens(masked) == []


def test_the_token_shape_is_polanons():
    """privacy.TOKEN_RE mirrors polanon's CASED_TOKEN_PATTERN without importing polanon on load."""
    from polanon.policy import CASED_TOKEN_PATTERN

    samples = ["<OSOBA_1>", "<OSOBA_1:celownik>", "<KOD_POCZTOWY_12>", "<OSOBA_3:wołacz>", "<OSOBA_1:>", "<OSOBA_1: x>"]
    for sample in samples:
        assert bool(privacy.TOKEN_RE.fullmatch(sample)) == bool(re.fullmatch(CASED_TOKEN_PATTERN, sample)), sample
