"""Optional PII masking for the AI assistant, powered by polanon (in ``requirements.txt``).

Before anything is sent to OpenRouter, personal data in the conversation (names, e-mails, phone
numbers, NIP/PESEL, IBANs, company names...) is replaced with tokens such as ``<OSOBA_1>`` or
``<EMAIL_1>``. The model only ever sees the tokens. The mapping token -> real value lives in memory
for the duration of one request and is used to:

* restore real values in the arguments of tool calls before a tool touches the database
  (the model may call ``get_company(name="<FIRMA_1>")``),
* restore real values in the final answer shown to the user.

The masking itself is polanon's :class:`~polanon.MaskedTurn`, one per request: it keeps the mapping,
masks client names the CRM knows (``known=``) and restores. polanon 0.4 masks a person named again
in another case as ``<OSOBA_1:celownik>``, and the model writes such a token back as it got it. In
the answer the name comes back declined ("Janowi Kowalskiemu"); in tool arguments, which go to the
database, it comes back as it was masked (``restore_data(..., as_held=True)``).

Rules (the same as in PolCV, https://github.com/boromat/polcv):

* without polanon installed and with masking switched off, the assistant works exactly as before,
* when masking is switched ON but polanon is missing or fails, NOTHING is sent to the model
  (:class:`MaskingUnavailable` is raised) - better an error than personal data sent in clear text.

This module imports nothing from Flask or the database, so it can be unit tested in isolation.
"""

from __future__ import annotations

import importlib.util
import re
from typing import TYPE_CHECKING, Any, Callable

if TYPE_CHECKING:  # polanon is imported lazily, see polanon_masker
    from polanon import MaskedTurn

import i18n
from i18n import _

#: Shape of a polanon token: ``<OSOBA_1>``, ``<EMAIL_12>``, ``<FIRMA_3>``..., and a person's token with
#: the grammatical case polanon 0.4 adds after a colon, ``<OSOBA_1:celownik>`` (as its
#: ``CASED_TOKEN_PATTERN``). No capturing group, so ``findall`` returns whole tokens.
TOKEN_RE = re.compile(r"<[A-Z][A-Z_]*_\d+(?::[^\W\d_]+)?>")


def _defused(text: str) -> str:
    """Write token-shaped text as ``[OSOBA_2]`` (``[OSOBA_3:celownik]``), so no turn reads it as a token.

    Numbering starts again in every request, while the history, a note in the database or what the
    user types may hold a token from an earlier one, or one the model made up. polanon keeps such a
    token as standing for itself only when it comes before the turn hands the same token out; after
    that it reads it as masked text and restores it as whoever got that token this time.
    """
    return TOKEN_RE.sub(lambda m: "[" + m.group(0)[1:-1] + "]", text)


def _defused_data(value: Any) -> Any:
    """:func:`_defused` on every string inside a JSON-like value, keys and numbers as they are.

    Anything else becomes its ``str`` first (a date, a ``Decimal``), as ``json.dumps(default=str)``
    would send it, so it is masked too and not sent as text after the masking.
    """
    if isinstance(value, str):
        return _defused(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    if isinstance(value, dict):
        return {k: _defused_data(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_defused_data(v) for v in value]
    return _defused(str(value))


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
        importlib.util.find_spec("spacy") is not None and importlib.util.find_spec("pl_core_news_md") is not None
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
            raise MaskingUnavailable(_("pakiet polanon nie jest zainstalowany (pip install polanon)")) from exc
        try:
            guards = default_guards(with_ner=with_ner)
        except ModuleNotFoundError as exc:  # spaCy or the Polish model missing
            raise MaskingUnavailable(str(exc)) from exc
        _ANONYMIZERS[with_ner] = Anonymizer(guards, allowlist=Allowlist(WELL_KNOWN_NAMES))
    return _ANONYMIZERS[with_ner]


def _fail_closed(mask: Callable[[Any], Any], value: Any) -> Any:
    """Run one of polanon's masks; any failure becomes :class:`MaskingUnavailable` (fail closed).

    polanon's own ``MaskingUnavailableError`` names the failure and never quotes the text.
    """
    try:
        return mask(value)
    except Exception as exc:
        raise MaskingUnavailable(_("blad polanon: %(error)s", error=exc)) from exc


class Masker:
    """Masks one assistant request with polanon's :class:`~polanon.MaskedTurn`.

    The turn keeps one mapping for the whole request, so a value gets one token in the history, the
    question and every tool result. Around it PolCRM adds what the turn leaves to the caller:
    token-shaped text in the input is defused first (:func:`_defused`), any failure is
    :class:`MaskingUnavailable` with a message in the interface language, a text that is empty or
    not a string passes as it is, and tool arguments come back as the records hold them.
    """

    def __init__(self, turn: MaskedTurn) -> None:
        self.turn = turn

    @property
    def mapping(self) -> dict[str, str]:
        """A copy of the request's token -> real value mapping."""
        return self.turn.mapping

    # ── outgoing: real -> tokens ───────────────────────────────

    def mask(self, text: str) -> str:
        """Mask one text, a token already in it defused first."""
        if not text or not isinstance(text, str):
            return text
        return _fail_closed(self.turn.mask, _defused(text))

    def mask_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Mask chat messages (``role``, ``content``) together, a token already in them defused first.

        A value polanon recognises in a later message is masked in the earlier ones too: the history
        says "Testowski dzwonił", a surname no rule reads alone, and the question names "Jan Testowski".
        """
        return _fail_closed(self.turn.mask_messages, [_defused_data(m) for m in messages])

    def mask_data(self, value: Any) -> Any:
        """Mask every string inside a JSON-like value (tool results). Keys and numbers stay as they are.

        A value polanon recognises in one string is masked in the others too, also in one before it.
        """
        return _fail_closed(self.turn.mask_data, _defused_data(value))

    # ── incoming: tokens -> real ───────────────────────────────

    def restore(self, text: str) -> str:
        """Replace known tokens in the answer with real values; unknown ones stay.

        A token with a case gives the name declined, ``<OSOBA_1:celownik>`` "Janowi Kowalskiemu";
        a name polanon cannot decline for sure comes back as written.
        """
        if not text or not isinstance(text, str):
            return text
        return self.turn.restore(text)

    def restore_data(self, value: Any) -> Any:
        """Restore tokens inside a JSON-like value (tool call arguments).

        A tool searches the database, which holds the original spelling, so a token with a case
        gives the value as it was masked, ``<OSOBA_1:dopełniacz>`` "Jan Kowalski", not declined.
        """
        return self.turn.restore_data(value, as_held=True)

    def unknown_tokens(self, text: str) -> list[str]:
        """Tokens in a model answer the request never handed out, each without its case, sorted."""
        return self.turn.unknown_tokens(text or "")


def ensure_available(with_ner: bool = False) -> None:
    """Raise :class:`MaskingUnavailable` when polanon (or spaCy for NER) cannot run."""
    _get_anonymizer(with_ner)


def polanon_masker(with_ner: bool = False, terms=()) -> Masker:
    """A :class:`Masker` on a turn of polanon's anonymizer. Raises :class:`MaskingUnavailable` when it cannot run.

    ``terms`` are values the CRM already knows are sensitive (client company names). polanon's
    rules find names with a legal form ("sp. z o.o.") or a first name, but not "Auto Serwis Nowak".
    The turn masks known terms always, as ``<FIRMA_n>``: also without the legal form a term is
    listed with, when two words or more are left, and also when polanon's allowlist of public names
    holds them, since a client of the agency is never "just public". The turn reuses the cached
    guards, so the spaCy model is not loaded again.
    """
    anonymizer = _get_anonymizer(with_ner)
    known = [t for t in dict.fromkeys(t.strip() for t in terms if t) if len(t) >= 3]
    return Masker(_fail_closed(lambda values: anonymizer.turn(known=values), known))
