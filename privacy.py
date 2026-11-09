"""Optional PII masking for the AI assistant, powered by polanon (``pip install polanon``).

Before anything is sent to OpenRouter, personal data in the conversation (names, e-mails, phone
numbers, NIP/PESEL, IBANs, company names...) is replaced with tokens such as ``<OSOBA_1>`` or
``<EMAIL_1>``. The model only ever sees the tokens. The mapping token -> real value lives in memory
for the duration of one request and is used to:

* restore real values in the arguments of tool calls before a tool touches the database
  (the model may call ``get_company(name="<FIRMA_1>")``),
* restore real values in the final answer shown to the user.

Rules (the same as in PolCV, https://github.com/boromat/polcv):

* without polanon installed and with masking switched off, the assistant works exactly as before,
* when masking is switched ON but polanon is missing or fails, NOTHING is sent to the model
  (:class:`MaskingUnavailable` is raised) - better an error than personal data sent in clear text.

This module imports nothing from Flask or the database, so it can be unit tested in isolation.
"""

from __future__ import annotations

import importlib.util
import re
from dataclasses import dataclass, field
from typing import Any, Callable

import i18n
from i18n import _

#: Shape of a polanon token: ``<OSOBA_1>``, ``<EMAIL_12>``, ``<FIRMA_3>``...
TOKEN_RE = re.compile(r"<[A-Z][A-Z_]*_\d+>")

#: Appended to the system prompt when masking is on, so the model treats tokens as real values.
TOKENS_NOTE = (
    "\n\nDANE OSOBOWE SA ZAMASKOWANE: imiona i nazwiska, e-maile, telefony, NIP, numery kont i nazwy "
    "firm w rozmowie i w wynikach narzedzi sa zastapione tokenami w nawiasach ostrych, np. <OSOBA_1>, "
    "<EMAIL_1>, <FIRMA_1>. Traktuj token jak prawdziwa wartosc. Gdy przekazujesz ja do narzedzia "
    "albo cytujesz w odpowiedzi, przepisz token dokladnie tak, jak jest zapisany - bez odmiany, bez "
    "zmiany liter i bez spacji w srodku. Nie tworz nowych tokenow."
)
#: The same note for the English system prompt (see :func:`tokens_note`).
TOKENS_NOTE_EN = (
    "\n\nPERSONAL DATA IS MASKED: first and last names, e-mails, phone numbers, tax IDs (NIP), account "
    "numbers and company names in the conversation and in tool results are replaced with tokens in angle "
    "brackets, e.g. <OSOBA_1>, <EMAIL_1>, <FIRMA_1>. Treat a token as the real value. When you pass it to a "
    "tool or quote it in your answer, copy the token exactly as it is written - do not change its letters "
    "and do not add spaces inside. Do not create new tokens."
)


def tokens_note(lang: str | None = None) -> str:
    """TOKENS_NOTE in the language of the current request (the assistant answers in that language)."""
    return TOKENS_NOTE_EN if (lang or i18n.current_language()) == "en" else TOKENS_NOTE


class MaskingUnavailable(RuntimeError):
    """Masking is switched on but cannot run. The caller must not contact the model."""


def client_terms(companies) -> list[str]:
    """Known client names to mask always: trade name, legal name and the name without a "[TAG] " prefix."""
    out: list[str] = []
    for c in companies:
        for value in (getattr(c, "name", ""), getattr(c, "client_legal_name", "")):
            value = (value or "").strip()
            if not value:
                continue
            out.append(value)
            if value.startswith("[") and "] " in value:
                out.append(value.split("] ", 1)[1])
    return out


def polanon_status() -> dict[str, Any]:
    """What the settings page shows: is polanon installed, which version, is spaCy NER available."""
    info: dict[str, Any] = {"installed": False, "version": None, "ner": False}
    if importlib.util.find_spec("polanon") is None:
        return info
    try:
        import polanon  # noqa: PLC0415 - optional dependency, imported lazily on purpose

        info["installed"] = True
        info["version"] = getattr(polanon, "__version__", None)
    except Exception:  # broken install - report as missing rather than crash the settings page
        return info
    info["ner"] = (
        importlib.util.find_spec("spacy") is not None
        and importlib.util.find_spec("pl_core_news_md") is not None
    )
    return info


# One anonymizer per (with_ner) flag for the whole process: building the guards (and loading the
# spaCy model) is the expensive part, and polanon's Anonymizer keeps no per-call state.
_ANONYMIZERS: dict[bool, Any] = {}


def _get_anonymizer(with_ner: bool):
    if with_ner not in _ANONYMIZERS:
        try:
            from polanon import WELL_KNOWN_NAMES, Allowlist, Anonymizer, default_guards  # noqa: PLC0415
        except ImportError as exc:
            raise MaskingUnavailable(
                _("pakiet polanon nie jest zainstalowany (pip install polanon)")
            ) from exc
        try:
            guards = default_guards(with_ner=with_ner)
        except ModuleNotFoundError as exc:  # spaCy or the Polish model missing
            raise MaskingUnavailable(str(exc)) from exc
        _ANONYMIZERS[with_ner] = Anonymizer(guards, allowlist=Allowlist(WELL_KNOWN_NAMES))
    return _ANONYMIZERS[with_ner]


@dataclass
class Masker:
    """Masks one assistant request. Tokens stay consistent across every text masked with it.

    ``anonymize`` is injectable for tests: ``(text, mapping) -> (masked_text, full_mapping)``.
    """

    anonymize: Callable[[str, dict[str, str]], tuple[str, dict[str, str]]]
    mapping: dict[str, str] = field(default_factory=dict)

    # ── outgoing: real -> tokens ───────────────────────────────

    def mask(self, text: str) -> str:
        if not text or not isinstance(text, str):
            return text
        try:
            masked, self.mapping = self.anonymize(text, self.mapping)
        except MaskingUnavailable:
            raise
        except Exception as exc:  # any polanon failure must stop the request (fail closed)
            raise MaskingUnavailable(_("blad polanon: %(error)s", error=exc)) from exc
        return masked

    def mask_data(self, value: Any) -> Any:
        """Mask every string inside a JSON-like value (tool results). Keys and numbers stay as they are."""
        if isinstance(value, str):
            return self.mask(value)
        if isinstance(value, dict):
            return {k: self.mask_data(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.mask_data(v) for v in value]
        return value

    # ── incoming: tokens -> real ───────────────────────────────

    def restore(self, text: str) -> str:
        if not text or not isinstance(text, str) or not self.mapping:
            return text
        return TOKEN_RE.sub(lambda m: self.mapping.get(m.group(0), m.group(0)), text)

    def restore_data(self, value: Any) -> Any:
        """Restore tokens inside a JSON-like value (tool call arguments)."""
        if isinstance(value, str):
            return self.restore(value)
        if isinstance(value, dict):
            return {k: self.restore_data(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self.restore_data(v) for v in value]
        return value

    def unknown_tokens(self, text: str) -> list[str]:
        """Tokens in a model answer that are not in the mapping (the model invented or mangled them)."""
        return [t for t in TOKEN_RE.findall(text or "") if t not in self.mapping]


def ensure_available(with_ner: bool = False) -> None:
    """Raise :class:`MaskingUnavailable` when polanon (or spaCy for NER) cannot run."""
    _get_anonymizer(with_ner)


def polanon_masker(with_ner: bool = False, terms=()) -> Masker:
    """A :class:`Masker` backed by polanon. Raises :class:`MaskingUnavailable` when it cannot run.

    ``terms`` are values the CRM already knows are sensitive (client company names). polanon's
    rules find names with a legal form ("sp. z o.o.") or a first name, but not "Auto Serwis Nowak";
    known terms are masked always, through polanon's DenylistGuard (token ``<FIRMA_n>``).
    """
    anonymizer = _get_anonymizer(with_ner)
    terms = [t for t in dict.fromkeys(t.strip() for t in terms if t) if len(t) >= 3]
    if terms:
        from polanon import WELL_KNOWN_NAMES, Allowlist, Anonymizer, DenylistGuard  # noqa: PLC0415

        # polanon leaves allowlisted public names (big brands, cities) unmasked - also when a
        # DenylistGuard found them. A client of the agency is never "just public", so its words
        # are taken out of the allowlist for this request.
        client_words = {w.lower() for t in terms for w in t.split()}
        allowlist = Allowlist([n for n in WELL_KNOWN_NAMES
                               if not ({w.lower() for w in n.split()} & client_words)])
        # Same guard instances (the spaCy model stays loaded), plus this request's known terms.
        anonymizer = Anonymizer([*anonymizer.guards, DenylistGuard(terms)], allowlist=allowlist)

    def _anonymize(text: str, mapping: dict[str, str]) -> tuple[str, dict[str, str]]:
        result = anonymizer.anonymize_sync(text, mapping)
        return result.anonymized, dict(result.mapping)

    return Masker(anonymize=_anonymize)
