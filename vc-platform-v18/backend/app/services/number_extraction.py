"""
Number extraction, Pass A: deterministic, regex-based RECOGNITION of every
number/currency/percentage/date/ratio/multiple candidate in the deck text -
deliberately with NO semantic interpretation attached yet (per-analyst
instruction: "do not interpret a number before preserving the raw
evidence"). This is not an LLM call - it's plain pattern matching, so it is
100% reproducible and runs identically in mock and live mode.

Recall over precision on purpose: a false-positive candidate (e.g. a slide
number caught by the regex) costs nothing downstream - Pass B (semantic
classification, LLM or mock heuristic) will label it "other_kpi"/
"unclassified" with low confidence, or a human reviewing the Number table
sees it and ignores it. A missed candidate, on the other hand, is a real
number from the deck that silently never reaches the platform - exactly
the failure mode this pass exists to prevent.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# The `(?!\d)` after each thousands-group repeat matters: without it, adjacent
# unrelated digit runs separated by whitespace (e.g. "Q1 2025" -> "1" then " 202"
# grabbed off the front of "2025") get fused into a bogus thousands-grouped number
# ("1 202" -> 1202.0) with a stray trailing digit silently dropped. A genuine
# space-grouped number ("1 202 025") is unaffected: each group is still followed by
# either another group-separator or the end of the number, never a bare extra digit.
_NUM = r"\d+(?:[ .,]\d{3}(?!\d))*(?:[.,]\d+)?"
_CUR = r"[€$£]|EUR|USD|GBP"
# English + French magnitude words/abbreviations. "m(?![a-zA-Z])" (not "mm") is the
# single-letter French/English million abbreviation ("2M€", "8m") - must not
# consume into a following word, hence the negative lookahead instead of \b (a
# following digit-less currency symbol like "€" isn't a word char, so \b alone
# would misfire there).
_SUFFIX = r"milliards?|millions?|milliers?|thousand|billion|mds?|md|mm|bn|k|m(?![a-zA-Z])"
_PCTX = r"%|x(?![a-zA-Z])"  # percentage, or an "x" multiple like "3.2x"

_CANDIDATE_RE = re.compile(
    rf"(?P<currency_pre>{_CUR})?\s?(?P<number>{_NUM})\s?(?P<suffix>{_SUFFIX})?\s?(?P<pctx>{_PCTX})?\s?(?P<currency_post>{_CUR})?",
    re.IGNORECASE,
)

# Bare small counts (no currency/%/multiple/magnitude signal) are only worth keeping
# when a unit word right next to them makes clear they're a real metric, not noise
# like a slide number or a stray digit - e.g. "35 clients", "6 mois", "12 employees".
_COUNT_KEYWORD_RE = re.compile(
    r"\b(?P<number>\d{1,6})\s+(?P<unit>clients?|customers?|utilisateurs?|users?|"
    r"employ[ée]s?|salari[ée]s?|contrats?|partenaires?|pays|countries|"
    r"mois|months?|ans?|ann[ée]es?|years?|logos?)\b",
    re.IGNORECASE,
)

_SLIDE_MARKER_RE = re.compile(r"^--- Slide (\d+):", re.MULTILINE)

_MIN_STANDALONE_DIGITS = 3  # bare numbers shorter than this (e.g. "5", "12") need a signal (currency/%/keyword) to count
_CONTEXT_WINDOW = 90        # characters of context on each side of the match


@dataclass
class NumberCandidate:
    raw_text: str
    context: str
    slide_reference: str | None
    span: tuple[int, int]


def _nearest_slide(position: int, slide_positions: list[tuple[int, int]]) -> str | None:
    """slide_positions is a sorted list of (char_offset, slide_number) for every
    '--- Slide N:' marker in the text - returns the slide the given offset
    falls under, or None if the text has no slide markers at all (e.g. a
    bare text fixture in a test)."""
    best = None
    for offset, slide_no in slide_positions:
        if offset <= position:
            best = slide_no
        else:
            break
    return str(best) if best is not None else None


def _slide_bounds(position: int, slide_positions: list[tuple[int, str]]) -> tuple[int, int | None]:
    """(start, end) char offsets of the slide `position` falls under - end is
    exclusive (the next slide marker's start), or None if `position` is on the
    last slide / there are no markers at all."""
    start = 0
    end = None
    for i, (offset, _) in enumerate(slide_positions):
        if offset <= position:
            start = offset
            end = slide_positions[i + 1][0] if i + 1 < len(slide_positions) else None
        else:
            break
    return start, end


def _context_window(deck_text: str, start: int, end: int, clip_start: int = 0, clip_end: int | None = None) -> str:
    start_ctx = max(0, start - _CONTEXT_WINDOW, clip_start)
    end_ctx = min(len(deck_text), end + _CONTEXT_WINDOW, clip_end if clip_end is not None else len(deck_text))
    return deck_text[start_ctx:end_ctx].replace("\n", " ").strip()


def extract_number_candidates(deck_text: str) -> list[NumberCandidate]:
    if not deck_text:
        return []

    slide_positions = [(m.start(), m.group(1)) for m in _SLIDE_MARKER_RE.finditer(deck_text)]
    candidates: list[NumberCandidate] = []
    seen_spans: set[tuple[int, int]] = set()

    for m in _CANDIDATE_RE.finditer(deck_text):
        g = m.groupdict()
        has_signal = bool(g["currency_pre"] or g["suffix"] or g["pctx"] or g["currency_post"])
        digits_only = re.sub(r"[.,\s]", "", g["number"])
        if not digits_only:
            continue
        if not has_signal and len(digits_only) < _MIN_STANDALONE_DIGITS:
            continue
        # A bare 4-digit number in year range with no currency/%/suffix signal is almost
        # always a calendar-year reference (e.g. "en 2025"), not a metric value - drop it
        # here rather than let it masquerade as a KPI number; Pass B never even sees it.
        if not has_signal and len(digits_only) == 4 and digits_only.isdigit() and 1990 <= int(digits_only) <= 2099:
            continue

        span = (m.start(), m.end())
        seen_spans.add(span)
        # Clip the context window to this candidate's own slide - otherwise a number
        # near a slide boundary picks up the NEXT slide's heading/keywords (e.g. "TAM")
        # in its context, which Pass B's classifier (mock or live) would then read as
        # if that keyword applied to this number. Provenance must stay slide-scoped.
        slide_start, slide_end = _slide_bounds(m.start(), slide_positions)
        candidates.append(
            NumberCandidate(
                raw_text=m.group(0).strip(),
                context=_context_window(deck_text, m.start(), m.end(), slide_start, slide_end),
                slide_reference=_nearest_slide(m.start(), slide_positions),
                span=span,
            )
        )

    # Second pass: bare small counts next to a recognizable unit keyword, which the
    # main pattern above deliberately excludes (no currency/%/magnitude signal).
    for m in _COUNT_KEYWORD_RE.finditer(deck_text):
        span = (m.start("number"), m.end("number"))
        if span in seen_spans or any(a <= span[0] < b for a, b in seen_spans):
            continue
        seen_spans.add(span)
        slide_start, slide_end = _slide_bounds(m.start(), slide_positions)
        candidates.append(
            NumberCandidate(
                raw_text=m.group(0).strip(),
                context=_context_window(deck_text, m.start(), m.end(), slide_start, slide_end),
                slide_reference=_nearest_slide(m.start(), slide_positions),
                span=span,
            )
        )

    candidates.sort(key=lambda c: c.span[0])
    return candidates


_MULTIPLIERS = {
    "k": 1_000, "thousand": 1_000, "millier": 1_000, "milliers": 1_000,
    "m": 1_000_000, "mm": 1_000_000, "million": 1_000_000, "millions": 1_000_000,
    "bn": 1_000_000_000, "b": 1_000_000_000, "billion": 1_000_000_000,
    "md": 1_000_000_000, "mds": 1_000_000_000, "milliard": 1_000_000_000, "milliards": 1_000_000_000,
}
_CURRENCY_NORMALIZE = {"€": "EUR", "$": "USD", "£": "GBP", "EUR": "EUR", "USD": "USD", "GBP": "GBP"}
_SPELLED_CURRENCY_RE = re.compile(r"\b(dollars?|euros?|livres?(?:\s+sterling)?)\b", re.IGNORECASE)
_SPELLED_CURRENCY_NORMALIZE = {"dollar": "USD", "euro": "EUR", "livre": "GBP"}


def structure_number_candidate(candidate: NumberCandidate) -> dict:
    """
    Deterministic Pass-A structuring - deliberately NOT an LLM call. Parses
    the exact substring a regex just matched (raw_text), so there is nothing
    here an LLM could get subtly wrong: pull the numeric value, the
    unit/currency/magnitude, and a best-effort period hint from the context
    window. `definition` is intentionally left null in this pass - stating
    HOW the deck defines a metric (e.g. "ARR includes annualized pilot
    contracts") is a genuine language-understanding task, reserved for a
    later, explicitly-LLM pass rather than guessed here.

    Returns a plain dict (not written to the DB directly) so callers can
    still override/reconcile before persisting via claim_store.add_number.
    """
    text = candidate.raw_text
    m = _CANDIDATE_RE.fullmatch(text)
    period = guess_period_hint(candidate.context)

    if m:
        g = m.groupdict()
        number_str = g["number"].replace(" ", "").replace(",", ".") if g["number"].count(",") == 0 else g["number"]
        # Reuse the same EU/US ambiguous-separator handling as calc/parsing.parse_money.
        number_str = g["number"].replace(" ", "")
        if "," in number_str and "." in number_str:
            if number_str.rfind(",") > number_str.rfind("."):
                number_str = number_str.replace(".", "").replace(",", ".")
            else:
                number_str = number_str.replace(",", "")
        elif "," in number_str:
            parts = number_str.split(",")
            number_str = number_str.replace(",", "") if len(parts[-1]) == 3 else number_str.replace(",", ".")

        try:
            value = float(number_str)
        except ValueError:
            value = None

        currency = None
        unit = None
        if g["pctx"] and g["pctx"].lower() == "%":
            unit = "%"
        elif g["pctx"]:  # "x" multiple
            unit = "x"
        else:
            raw_currency = g["currency_pre"] or g["currency_post"]
            if raw_currency:
                currency = _CURRENCY_NORMALIZE.get(raw_currency.upper(), raw_currency.upper())
                unit = currency
            suffix = (g["suffix"] or "").lower()
            multiplier = _MULTIPLIERS.get(suffix, 1)
            if value is not None:
                value *= multiplier
            if unit is None and multiplier > 1:
                # A magnitude suffix with no adjacent currency symbol/code - try a spelled-out
                # currency word nearby ("64 milliards de dollars") before giving up and leaving
                # currency genuinely unknown rather than guessing which one the deck meant.
                spelled = _SPELLED_CURRENCY_RE.search(candidate.context[candidate.context.find(text) if text in candidate.context else 0:])
                if spelled:
                    currency = _SPELLED_CURRENCY_NORMALIZE.get(spelled.group(1).lower().split()[0].rstrip("s"), None)
                unit = currency or "count"

        return {"value": value, "unit": unit, "currency": currency, "period": period, "as_of_date": None, "definition": None}

    ck = _COUNT_KEYWORD_RE.fullmatch(text)
    if ck:
        try:
            value = float(ck.group("number"))
        except ValueError:
            value = None
        return {"value": value, "unit": ck.group("unit").lower(), "currency": None, "period": period, "as_of_date": None, "definition": None}

    return {"value": None, "unit": None, "currency": None, "period": period, "as_of_date": None, "definition": None}


_PERIOD_HINT_RE = re.compile(
    r"\b(Q[1-4]\s?20\d{2}|20\d{2}|FY\s?20\d{2}|H[12]\s?20\d{2}|"
    r"jan(?:vier)?|f[ée]v(?:rier)?|mars|avril|mai|juin|juillet|ao[uû]t|sept(?:embre)?|oct(?:obre)?|nov(?:embre)?|d[ée]c(?:embre)?)\b",
    re.IGNORECASE,
)


def guess_period_hint(context: str) -> str | None:
    """Best-effort, deterministic period hint pulled straight from the context
    window - not a substitute for Pass A's LLM structuring step, just a cheap
    fallback so mock mode can still populate `period` with something real
    instead of leaving it null across the board."""
    m = _PERIOD_HINT_RE.search(context)
    return m.group(0) if m else None
