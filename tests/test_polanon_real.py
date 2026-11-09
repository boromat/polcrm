"""The same contract with the real polanon (skipped when it is not installed).

CI installs polanon, so these run on every push.
"""

import json

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
    monkeypatch.setattr(ai_assistant, "execute_tool",
                        lambda name, args, *a, **k: seen.append(args) or {"contact": "jan.kowalski@example.com"})
    requests = []

    def model(messages):
        requests.append(json.dumps(messages, ensure_ascii=False))
        if len(requests) == 1:
            token = privacy.TOKEN_RE.findall(messages[-1]["content"])[0]
            return {"choices": [{"message": {"content": "", "tool_calls": [{
                "id": "c1", "type": "function",
                "function": {"name": "search_global", "arguments": json.dumps({"query": token})}}]}}]}
        token = privacy.TOKEN_RE.findall(messages[-1]["content"])[0]
        return {"choices": [{"message": {"content": f"Mail: {token}"}}]}

    result = ai_assistant.run_conversation(
        "Znajdź Jan Kowalski", [], models={}, db=None, finance_helpers=None,
        masker=privacy.polanon_masker(), call=model)

    assert all("Jan Kowalski" not in r and "jan.kowalski@example.com" not in r for r in requests)
    assert "Kowalski" in seen[0]["query"]
    assert result["reply"] == "Mail: jan.kowalski@example.com"


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
