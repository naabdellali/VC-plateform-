"""
LLM abstraction (spec section 54: "use LLMs for extraction, research
synthesis, qualitative reasoning, classification, contradiction detection,
assumption extraction, hypothesis generation - NOT for arithmetic").

Every public method here returns data, never a persisted Evidence row -
the reasoning modules (services/reasoning/*) are the ones that decide how
to turn an LLM output into an Evidence row with an origin/confidence/tier.

MOCK MODE: if ANTHROPIC_API_KEY is not set, every method returns a
deterministic, clearly-labelled stub instead of raising - the whole
pipeline stays runnable end-to-end (upload -> modules -> memo) without any
key configured, which is what lets this repo be cloned and exercised
immediately. Nothing produced in mock mode is ever framed as verified;
callers must propagate `mode == "mock"` into the resulting Evidence rows.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass

from app.config import get_settings

settings = get_settings()

MOCK_DISCLAIMER = "[MOCK MODE - no ANTHROPIC_API_KEY configured, this is a placeholder, not a verified answer]"


@dataclass
class LlmResult:
    mode: str  # "live" | "mock"
    text: str
    parsed: dict | list | None = None


def _strip_code_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(json)?", "", text).strip()
    text = re.sub(r"```$", "", text).strip()
    return text


def _salvage_json_array(text: str) -> list | None:
    """
    Best-effort recovery for a JSON array response that got cut off mid-object -
    e.g. extract_claims on a very dense deck (revenue by quarter, competitors,
    team, market sizing, traction all in one deck) can produce a long enough
    claims array that even a generous max_tokens cap sometimes isn't enough,
    and the response is truncated mid-object by the model's own output limit.
    A plain json.loads() on that then fails entirely, and previously the
    caller got `parsed=None` -> treated as "zero claims extracted" - which is
    exactly the bug reported ("the platform extracted nothing" from a
    deck with lots of tables/data).

    Instead, walk the text tracking string/brace state and keep every
    top-level `{...}` object that DOES parse cleanly, dropping only the
    final, incomplete one. A deck that had 30 extractable claims and got
    cut off after 27 should yield 27 claims, not 0.

    Only used as a fallback after a normal json.loads() has already failed;
    returns None (not []) if nothing could be salvaged, so callers can still
    tell "genuinely empty" apart from "not an array at all".
    """
    text = text.strip()
    if not text.startswith("["):
        return None
    objects = []
    depth = 0
    start = None
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
            continue
        if ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start : i + 1]
                try:
                    objects.append(json.loads(candidate))
                except json.JSONDecodeError:
                    pass
                start = None
    return objects if objects else None


# ----------------------------------------------------------------------
# Mock-mode fallbacks for the Phase 1 extraction passes - deterministic,
# regex/keyword-based, clearly inferior to the real LLM passes (that's the
# point of labelling them mock), but they exist so the canonical deal
# representation is still meaningfully populated - not just empty - when
# no ANTHROPIC_API_KEY is configured. Mirrors the spirit of
# LlmClient._mock_extract_claims for the older extraction pipeline.
# ----------------------------------------------------------------------

_NUMBER_KEYWORD_CATEGORIES = [
    # (regex over the number's context, semantic_category) - first match wins.
    (re.compile(r"\bmrr\b", re.IGNORECASE), "mrr"),
    (re.compile(r"\barr\b", re.IGNORECASE), "arr"),
    (re.compile(r"\bgmv\b", re.IGNORECASE), "gmv"),
    (re.compile(r"\btam\b", re.IGNORECASE), "market_size_tam"),
    (re.compile(r"\bsam\b", re.IGNORECASE), "market_size_sam"),
    (re.compile(r"\bsom\b", re.IGNORECASE), "market_size_som"),
    (re.compile(r"\bcac\b", re.IGNORECASE), "cac"),
    (re.compile(r"\bltv\b", re.IGNORECASE), "ltv"),
    (re.compile(r"\bacv\b", re.IGNORECASE), "acv"),
    (re.compile(r"churn", re.IGNORECASE), "churn"),
    (re.compile(r"r[ée]tention|retention", re.IGNORECASE), "retention"),
    (re.compile(r"marge|margin", re.IGNORECASE), "gross_margin"),
    (re.compile(r"\bcogs\b", re.IGNORECASE), "cogs"),
    (re.compile(r"\bburn\b", re.IGNORECASE), "burn"),
    (re.compile(r"runway", re.IGNORECASE), "runway"),
    (re.compile(r"pipeline", re.IGNORECASE), "pipeline"),
    (re.compile(r"conversion", re.IGNORECASE), "conversion"),
    (re.compile(r"cycle de vente|sales cycle", re.IGNORECASE), "sales_cycle"),
    (re.compile(r"utilisateurs?\b|\busers?\b", re.IGNORECASE), "users"),
    (re.compile(r"clients?\b|customers?\b", re.IGNORECASE), "customers"),
    (re.compile(r"lev[ée]e|raised|funding|s[ée]rie [a-z]\b|series [a-z]\b|\bseed\b", re.IGNORECASE), "funding_amount"),
    (re.compile(r"valorisation|valuation", re.IGNORECASE), "valuation"),
    (re.compile(r"croissance|growth", re.IGNORECASE), "growth_rate"),
    (re.compile(r"employ[ée]s?|salari[ée]s?|headcount", re.IGNORECASE), "headcount"),
    (re.compile(r"engagement", re.IGNORECASE), "engagement"),
    (re.compile(r"utilisation|utilization", re.IGNORECASE), "utilization"),
    (re.compile(r"commandes?|orders?", re.IGNORECASE), "order_volume"),
    (re.compile(r"unit[ée]s? vendues?|units sold", re.IGNORECASE), "units_sold"),
    (re.compile(r"revenue|revenu|chiffre d'affaires|\bca\b", re.IGNORECASE), "revenue"),
]


def _mock_classify_numbers(numbers: list[dict]) -> list[dict]:
    results = []
    for n in numbers:
        idx = n.get("index")
        context = n.get("context") or ""
        unit = (n.get("unit") or "").lower()
        category = "unclassified"
        if unit in ("clients", "customers"):
            category = "customers"
        elif unit == "users" or unit == "utilisateurs":
            category = "users"
        else:
            for pattern, cat in _NUMBER_KEYWORD_CATEGORIES:
                if pattern.search(context):
                    category = cat
                    break
        results.append({
            "index": idx,
            "semantic_category": category,
            "semantic_confidence": "medium" if category != "unclassified" else "low",
            "candidate_categories": [],
        })
    return results


def _mock_line_scan(deck_text: str, patterns: list[tuple]) -> list[dict]:
    """Shared regex-line-scan helper: for each line of deck_text, test each
    (regex, claim_type, kind) tuple and emit a hit. Deliberately per-line
    (not per-sentence/paragraph) to mirror the deck's own slide-by-slide
    structure and keep `context` short and genuinely relevant."""
    slide = None
    slide_re = re.compile(r"^--- Slide (\d+):")
    out = []
    for line in deck_text.splitlines():
        m = slide_re.match(line)
        if m:
            slide = m.group(1)
            continue
        line_stripped = line.strip()
        if not line_stripped:
            continue
        for pattern, claim_type, kind in patterns:
            if pattern.search(line_stripped):
                out.append({
                    "claim_type": claim_type, "kind": kind,
                    "text": line_stripped[:300], "context": line_stripped[:300], "slide_reference": slide,
                })
                break
    return out


_STRUCTURED_FIELD_PATTERNS = [
    (re.compile(r"\b(CEO|CTO|CFO|COO|CO-?FOUNDER|founder|fondateur|fondatrice)\b", re.IGNORECASE), "team_background", "fact"),
    (re.compile(r"\bSAS\b|\bSARL\b|\bSIREN\b|\bSIRET\b|si[èe]ge social|headquartered|headquarters", re.IGNORECASE), "company_identity", "fact"),
    (re.compile(r"lev[ée]e de fonds|raised \S|\bseed\b|\bseries [a-z]\b|\bs[ée]rie [a-z]\b|investisseurs?|investors?", re.IGNORECASE), "funding_history", "fact"),
    (re.compile(r"tam\b|sam\b|som\b|taille du march[ée]|market size|d[ée]finition du march[ée]", re.IGNORECASE), "market_definition", "fact"),
    (re.compile(r"€\s?\d|\$\s?\d|/mois|/month|par mois|per month|pricing|tarif", re.IGNORECASE), "pricing", "fact"),
    (re.compile(r"api|int[ée]gration|architecture|stack technique|technology stack", re.IGNORECASE), "product_architecture", "fact"),
    (re.compile(r"roadmap|feuille de route", re.IGNORECASE), "product_roadmap", "fact"),
    (re.compile(r"probl[èe]me|solution|use case|cas d'usage", re.IGNORECASE), "product_description", "fact"),
]

_MANAGEMENT_CLAIM_PATTERNS = [
    (re.compile(r"leader (?:du|sur le|de) march[ée]|market leader", re.IGNORECASE), "competitive_position"),
    (re.compile(r"aucun concurrent|pas de concurrence|no (?:significant )?competitors?", re.IGNORECASE), "competitive_position"),
    (re.compile(r"propri[ée]taire|proprietary|brevet[ée]?|patented", re.IGNORECASE), "differentiation"),
    (re.compile(r"unique|seul(?:e)? (?:sur le march[ée]|acteur)|only (?:company|player)", re.IGNORECASE), "differentiation"),
    (re.compile(r"d'ici 20\d\d|by 20\d\d|objectif|target:", re.IGNORECASE), "traction_projection"),
]


def _mock_extract_structured_fields(deck_text: str) -> list[dict]:
    return _mock_line_scan(deck_text, _STRUCTURED_FIELD_PATTERNS)


def _mock_extract_management_claims(deck_text: str) -> list[dict]:
    hits = _mock_line_scan(deck_text, [(p, ct, "company_claim") for p, ct in _MANAGEMENT_CLAIM_PATTERNS])
    for h in hits:
        h["required_evidence"] = "Non déterminé automatiquement en mode mock - nécessite une passe LLM en direct."
        h["potential_challenge"] = "Non déterminé automatiquement en mode mock - nécessite une passe LLM en direct."
        del h["kind"]
    return hits


# decompose_assumptions() pre-dates Phase 1 (Technology's fixed hypothesis already
# used it) and its original mock fallback was a bare empty list - meaning Pass E
# (assumption decomposition, applied here to every traction_projection claim)
# silently produced nothing in mock mode, for ANY deck, regardless of content.
# That is exactly the "pretend the pipeline works" failure mode this whole phase
# exists to eliminate - a keyword heuristic below at least surfaces something
# real and inspectable without a live key, clearly labelled as mock like every
# other fallback here.
_ASSUMPTION_KEYWORD_HINTS = [
    (re.compile(r"march[ée] am[ée]ricain|us market|expansion (?:internationale|aux [ée]tats-unis)|international", re.IGNORECASE),
     "Suppose que l'expansion sur ce nouveau marché se déroule sans retard majeur (recrutement local, conformité, go-to-market)."),
    (re.compile(r"clients?\b|customers?\b", re.IGNORECASE),
     "Suppose que le rythme d'acquisition de nouveaux clients observé jusqu'ici se maintient."),
    (re.compile(r"conversion", re.IGNORECASE),
     "Suppose que le taux de conversion actuel reste stable ou s'améliore."),
    (re.compile(r"r[ée]tention|retention|churn", re.IGNORECASE),
     "Suppose que le taux de rétention/churn actuel ne se dégrade pas."),
    (re.compile(r"prix|pricing|tarif", re.IGNORECASE),
     "Suppose que la structure tarifaire actuelle reste inchangée."),
]


def _mock_decompose_assumptions(claim: str) -> list[dict]:
    assumptions = []
    for pattern, assumption_text in _ASSUMPTION_KEYWORD_HINTS:
        if pattern.search(claim):
            assumptions.append({
                "assumption": assumption_text,
                "plausibility": "aggressive",
                "reason": "Non déterminé automatiquement en mode mock - nécessite une passe LLM en direct pour juger la plausibilité réelle.",
            })
    # Every forecast depends on execution capacity even when no specific keyword
    # matched above - never leave a projection with zero decomposed assumptions.
    assumptions.append({
        "assumption": "Suppose que les moyens commerciaux, techniques et financiers nécessaires seront disponibles pour atteindre cet objectif.",
        "plausibility": "aggressive",
        "reason": "Non déterminé automatiquement en mode mock - nécessite une passe LLM en direct pour juger la plausibilité réelle.",
    })
    return assumptions


class LlmClient:
    def __init__(self):
        self._client = None
        if settings.llm_available:
            import anthropic

            self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)

    @property
    def mode(self) -> str:
        return "live" if self._client else "mock"

    def _call(self, system: str, user: str, max_tokens: int = 2000) -> str:
        if not self._client:
            raise RuntimeError("LLM client called in mock mode - callers must branch on .mode before calling _call")
        resp = self._client.messages.create(
            model=settings.anthropic_model,
            max_tokens=max_tokens,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        return "".join(block.text for block in resp.content if block.type == "text")

    def _call_json(self, system: str, user: str, max_tokens: int = 2000) -> LlmResult:
        if not self._client:
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed=None)
        raw = self._call(system + "\n\nRespond ONLY with valid JSON. No prose, no markdown fences.", user, max_tokens)
        cleaned = _strip_code_fences(raw)
        try:
            parsed = json.loads(cleaned)
        except json.JSONDecodeError:
            # Salvage whatever complete top-level objects we can from a response that
            # got cut off mid-array (see _salvage_json_array) rather than silently
            # discarding the whole batch - a no-op for any non-array-shaped response.
            parsed = _salvage_json_array(cleaned)
        return LlmResult(mode="live", text=raw, parsed=parsed)

    # ------------------------------------------------------------------
    # 1. Extraction: deck text -> typed claims
    # ------------------------------------------------------------------
    def extract_claims(self, deck_text: str) -> LlmResult:
        system = (
            "You are an extraction engine for a VC due-diligence platform. "
            "Read a pitch deck's raw text and extract every material, checkable claim. "
            "Return a JSON array of objects: "
            '{"category": one of ["market_size","competitors","traction_metric","traction_projection",'
            '"team_background","financials","business_model","fundraising_history","other"], '
            '"claim": short human-readable statement, "value": the raw number/text if any, '
            '"slide_reference": best-guess slide number or null}. '
            "Use 'traction_metric' for CURRENT/already-achieved traction (MRR, ARR, customer count, revenue "
            "to date). Use 'traction_projection' for FORWARD-LOOKING statements only - anything phrased as a "
            "forecast, target, projection, or 'by [future date]' (e.g. 'ARR projeté de 500K d'ici fin d'année', "
            "'target: 200 customers by Q4'). Do not infer anything not stated in the text. Do not invent numbers."
        )
        if self.mode == "mock":
            return self._mock_extract_claims(deck_text)
        # Dense decks (tables, revenue by quarter, competitor lists, team, traction,
        # market sizing all present) can produce a long claims array - the default
        # 2000-token cap was silently truncating the JSON mid-array on those decks,
        # which read as "the platform extracted nothing" for whatever category
        # happened to be extracted last. 8000 gives real headroom for a genuinely
        # dense deck (30-50+ claims); _call_json also salvages whatever complete
        # objects it can if even that gets cut off, so a truncation never again
        # silently means zero claims.
        return self._call_json(system, deck_text[:60000], max_tokens=8000)

    def _mock_extract_claims(self, deck_text: str) -> LlmResult:
        # Deterministic, regex-based stand-in so the pipeline is exercisable
        # without an API key. Clearly inferior to the real LLM extraction -
        # that's the point of labelling it mock.
        claims = []
        for m in re.finditer(r"(TAM|SAM|SOM|market)[^\n\d]{0,40}([\€\$]?\s?\d[\d.,]*\s?(bn|billion|m|million|k)?)", deck_text, re.IGNORECASE):
            claims.append({"category": "market_size", "claim": m.group(0).strip(), "value": m.group(2), "slide_reference": None})
        for m in re.finditer(r"(MRR|ARR)[^\n\d]{0,40}([\€\$]?\s?\d[\d.,]*\s?(k|m|million)?)", deck_text, re.IGNORECASE):
            snippet = m.group(0)
            is_projection = bool(re.search(r"projet|prévision|forecast|target|d'ici|by 20\d\d", snippet, re.IGNORECASE))
            claims.append({
                "category": "traction_projection" if is_projection else "traction_metric",
                "claim": snippet.strip(), "value": m.group(2), "slide_reference": None,
            })
        for line in deck_text.splitlines():
            if re.search(r"\bcompetitor", line, re.IGNORECASE):
                claims.append({"category": "competitors", "claim": line.strip()[:200], "value": line.strip()[:200], "slide_reference": None})
            if re.search(r"\b(CEO|CTO|CO-?FOUNDER|founder)\b", line, re.IGNORECASE):
                claims.append({"category": "team_background", "claim": line.strip()[:200], "value": None, "slide_reference": None})
        return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed=claims)

    # ------------------------------------------------------------------
    # 1b. Sector inference - the company workspace form's "Sector" field is
    #     free text and often left blank; every downstream research query
    #     (market sizing, competitors) is only as good as this, so if it's
    #     missing we read it off the deck itself instead of researching
    #     the wrong industry. Deliberately NOT read from a fixed enum -
    #     a specific, real phrase ("cleaning & maintenance services for
    #     residential/commercial real estate") is far more useful for
    #     search than a generic category, and prevents the module from
    #     silently defaulting to whatever the workspace's business_model
    #     field happens to be set to.
    # ------------------------------------------------------------------
    def infer_sector(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and identify, as precisely as possible, the actual "
            "industry/market the company operates in - based only on what the deck describes, never "
            "a generic guess. Prefer a specific descriptive phrase over a broad category "
            "(e.g. 'cleaning and maintenance services for residential and commercial real estate', "
            "not just 'real estate' or 'services'). "
            'Return JSON: {"sector": "..." or null if the deck genuinely does not make this clear, '
            '"confidence": "high"|"medium"|"low"}'
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"sector": None, "confidence": "unverified"})
        return self._call_json(system, deck_text[:60000])

    # ------------------------------------------------------------------
    # 1c. Technology architecture / third-party dependency extraction (VC
    #     Expert Questioning Framework, Technology dimension, section 2.1-2.2).
    #     Deck-text only, like extract_claims/infer_sector - this is a
    #     classification of what the deck itself says, not an independently
    #     verified fact. "critical" is a judgment call about whether the
    #     dependency is core to the product, made from the deck text alone;
    #     downstream code must treat it as company_claim-origin, not as a
    #     verified finding.
    # ------------------------------------------------------------------
    def identify_tech_dependencies(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and identify its technology architecture, for an analyst who will "
            "read this as THREE separate, clearly distinct blocks in this exact order: (1) what the tech IS, "
            "(2) dependencies/risk, (3) a maturity grade. Write everything in French, in short, simple, human "
            "sentences - not academic, not a list of jargon fragments. "
            "(1) Write one or two plain sentences summarizing what their technology actually is and what they "
            "own/built (a normal person should understand it immediately - no jargon-only fragments like 'GPS, "
            "geolocation, critical data'). Separately, list what's proprietary/built in-house as short KEYWORDS "
            "or short phrases (2-4 words each, e.g. 'moteur de scoring propriétaire', 'modèle de pricing "
            "interne') - not full sentences, these render as compact tags. "
            "(2) List every named third-party dependency the deck mentions or clearly implies the product "
            "relies on (APIs, cloud providers, foundation models/LLMs, payment providers, data providers, "
            "hardware suppliers, infrastructure providers). For each, give its name as a short keyword/label, "
            "then ONE short plain sentence stating the concrete risk if that dependency became unavailable or "
            "raised its price - not a description of what it does, the RISK it represents. Judge whether it's "
            "CRITICAL (the product could not function as described without it) based only on how the deck "
            "frames it. Never invent a dependency that isn't stated or clearly implied in the text. "
            "(3) Only if you have enough information to judge (do not guess from a thin deck), grade the "
            "overall technical maturity as 'Avancé' (real technical depth, hard to replicate quickly), "
            "'Intermédiaire' (solid but replicable with effort), or 'Basique' (thin technical layer, mostly "
            "off-the-shelf/no-code) - use null if there isn't enough to judge, don't force a grade. "
            'Return JSON: {"tech_summary": "1-2 simple French sentences on what their tech is/does", '
            '"dependencies": [{"name": "short keyword/label", "risk_note": "one short French sentence on the '
            'concrete risk", "critical": true|false, "evidence_text": "verbatim short snippet from the deck"}], '
            '"proprietary": ["short keyword/phrase", ...], '
            '"tech_grade": "Avancé"|"Intermédiaire"|"Basique"|null, "tech_grade_reason": "1 short sentence" or null}. '
            "If the deck says nothing about technology/architecture, return empty lists, null tech_summary, null tech_grade."
        )
        if self.mode == "mock":
            return LlmResult(
                mode="mock", text=MOCK_DISCLAIMER,
                parsed={"tech_summary": None, "dependencies": [], "proprietary": [], "tech_grade": None, "tech_grade_reason": None},
            )
        return self._call_json(system, deck_text[:60000], max_tokens=1200)

    # ------------------------------------------------------------------
    # 1d. Short industry display tag (e.g. "Insuretech") - a compact label
    #     for the tray/header chip, distinct from `sector` (a longer,
    #     precise phrase used to drive research queries). Pure
    #     categorization of an already-known sector string, not a new
    #     research claim - safe to run even in constrained contexts.
    # ------------------------------------------------------------------
    def categorize_industry_tag(self, sector_text: str) -> LlmResult:
        system = (
            "Given a company's sector/industry description, return the single most standard, "
            "widely-recognized short category label for it (1-2 words, e.g. 'Insuretech', 'Fintech', "
            "'Proptech', 'Cybersecurity', 'HR Tech', 'Climate Tech'). Prefer an existing industry-tag "
            "convention over inventing a new term. "
            'Return JSON: {"tag": "..."}'
        )
        if self.mode == "mock":
            # Honest fallback, no LLM guess: first word of the sector phrase, title-cased.
            first_word = (sector_text or "").split()[0].strip(",.") if sector_text else None
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"tag": first_word.title() if first_word else None})
        return self._call_json(system, sector_text[:500], max_tokens=100)

    # ------------------------------------------------------------------
    # 1e. Plain-language company description for the memo's executive
    #     summary - deliberately separate from market-size/competition so
    #     the exec summary doesn't accidentally lead with a number that
    #     belongs in its own section further down.
    # ------------------------------------------------------------------
    def describe_company(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and write a plain, simple French description of the company: "
            "what it does, what problem it solves, and who the customer is. Write it the way you'd explain it "
            "out loud to a colleague in one breath - short, human sentences, no jargon-stacking, no academic "
            "tone, no markdown, no headers. 2-3 sentences max. Do NOT mention market size, funding amount, or "
            "competitors - those belong elsewhere. Use only what the deck actually says."
            'Return JSON: {"description": "..."}'
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"description": None})
        return self._call_json(system, deck_text[:60000], max_tokens=300)

    # ------------------------------------------------------------------
    # 1f. Business model mechanics - pricing unit + target customer segment,
    #     from the deck text only. The Company.business_model field is just
    #     a fixed workspace-form category ("saas") - far too coarse to be
    #     useful on its own (a SaaS company could be priced per-seat,
    #     per-usage, flat-fee...), so this fills in the concrete mechanics
    #     an analyst actually wants to see at a glance.
    # ------------------------------------------------------------------
    def identify_business_model_details(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and identify how the company actually prices and sells its "
            "product. Write in French, short simple sentences, no jargon-stacking. "
            "Identify the pricing unit/mechanic ONLY if the deck states or clearly implies it (e.g. "
            "'par poste/utilisateur', 'par entreprise (forfait)', 'à l'usage/consommation', "
            "'commission sur transaction', 'abonnement mensuel fixe') - do not guess if unclear. "
            "Identify the target customer segment ONLY if stated or clearly implied (e.g. 'PME', 'TPE', "
            "'grands comptes/Enterprise', 'grand public'). "
            'Return JSON: {"pricing_model": "short French phrase" or null, '
            '"target_segment": "short French phrase" or null}. '
            "Use null for either field rather than guessing if the deck doesn't say."
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"pricing_model": None, "target_segment": None})
        return self._call_json(system, deck_text[:60000], max_tokens=200)

    # ------------------------------------------------------------------
    # 1f-bis. Business model tile "detail on click": an expanded, plain-French
    #     explanation of how the revenue mechanic actually plays out for the
    #     company's own customers. Deliberately GENERALIZED - reasons from the
    #     deck's own pricing unit and segment rather than inventing a named,
    #     hardcoded illustrative customer (the analyst was explicit that a
    #     couple of hardcoded example names read as fabricated, not that she
    #     wanted a template with different names swapped in). If the deck
    #     gives real per-unit numbers, walk through the arithmetic with those
    #     real numbers; otherwise stay qualitative - never invent a number.
    # ------------------------------------------------------------------
    def explain_business_model(self, deck_text: str, pricing_model: str | None, target_segment: str | None) -> LlmResult:
        system = (
            "You are a VC analyst explaining a company's revenue mechanic to a colleague, in French, short "
            "simple sentences, no jargon-stacking, no markdown. You are given the pricing unit and target "
            "segment already extracted from the deck (may be null), plus the deck's raw text. "
            "Write a short explanation (3-5 sentences) of HOW the revenue mechanic actually works in practice "
            "for this company's customers - e.g. what a customer pays for, what drives the price up or down "
            "(seats, usage volume, transaction size...), and why that pricing unit makes sense given the "
            "target segment. Reason in GENERAL terms tied to the deck's own pricing logic - do NOT invent a "
            "named example customer or company ('a company like X would pay...'); describe the mechanic itself. "
            "If, and only if, the deck states real per-unit numbers (a price, a seat count, a take rate...), "
            "you may walk through that real arithmetic explicitly - never invent or round a number that isn't "
            "in the deck. If the deck doesn't give enough to explain the mechanic beyond the pricing "
            "unit/segment already extracted, say so plainly instead of padding. "
            'Return JSON: {"explanation": "..." or null}'
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"explanation": None})
        user = (
            f"Pricing unit extracted: {pricing_model or 'non précisé'}\n"
            f"Target segment extracted: {target_segment or 'non précisé'}\n\n"
            f"Deck text:\n{deck_text[:60000]}"
        )
        return self._call_json(system, user, max_tokens=400)

    # ------------------------------------------------------------------
    # 1g. Founder/officer names + titles as literally stated in the deck.
    #     This is deliberately NOT a background check - just an honest read
    #     of who the deck says is on the team, so the tile can show real
    #     names instead of "en attente de données" while the Pappers.fr /
    #     web-verification pass (which IS the background check) runs
    #     separately in founders_module.py.
    # ------------------------------------------------------------------
    def identify_founders(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and list the founders/executives it names, with their title "
            "(CEO, CTO, CFO, COO, etc.) ONLY if the deck states it. Do not invent a name or title that isn't "
            "in the text, and do not guess a title from context - if the deck names someone but doesn't give "
            "a title, use null for title. "
            'Return JSON: {"founders": [{"name": "...", "title": "..." or null}, ...]}. '
            "Return an empty list if the deck names no one specifically."
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"founders": []})
        return self._call_json(system, deck_text[:60000], max_tokens=400)

    # ------------------------------------------------------------------
    # 1h. Red flags, connected into one flowing paragraph for the memo.
    #     Purely a rephrasing/connecting pass over findings the platform
    #     already produced (market, competition, moat, financial checks) -
    #     no new facts, numbers, or claims may be introduced; this is the
    #     same "smooth the prose, never invent" contract as describe_company.
    # ------------------------------------------------------------------
    def narrate_red_flags(self, flags: list[dict]) -> LlmResult:
        system = (
            "You are given a list of red flags already identified by a VC due-diligence platform, each with "
            "a severity and an explanation. Connect them into ONE flowing, well-written French paragraph, the "
            "way an analyst would write a conclusion - e.g. linking a competitive/market finding to a moat "
            "finding ('le marché est compétitif, ce qui n'est pas contrebalancé par un moat technologique "
            "fort...'). Short, simple, human sentences - not academic. Do NOT invent any new fact, number, or "
            "claim beyond what's in the flags provided - only rephrase and connect what's already there. "
            "If a flag doesn't naturally connect to the others, it can stand as its own sentence. "
            'Return JSON: {"narrative": "..."}.'
        )
        user = json.dumps([{"severity": f.get("severity"), "explanation": f.get("explanation")} for f in flags])
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"narrative": None})
        return self._call_json(system, user, max_tokens=500)

    # ------------------------------------------------------------------
    # 2. Contextual query generation (spec section 40)
    # ------------------------------------------------------------------
    def generate_search_queries(self, question: str, context: dict) -> LlmResult:
        system = (
            "You generate precise, contextual web-search queries for investment research. "
            "Never generate generic queries. Use the company's sector, geography, stage and "
            "business model to make each query as specific as possible. "
            'Return JSON: {"queries": ["...", "..."]} with 2-4 queries.'
        )
        user = f"Question: {question}\nContext: {json.dumps(context)}"
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"queries": [question]})
        return self._call_json(system, user)

    # ------------------------------------------------------------------
    # 3. Research synthesis (spec section 42-43: produces an evidence-ready payload)
    # ------------------------------------------------------------------
    def synthesize_research(self, question: str, sources: list[dict]) -> LlmResult:
        # This "answer" string gets embedded directly into red-flag explanations and
        # evidence claims across several modules (traction, founders, competition) -
        # it was previously left English-default, which is the main source of the
        # French/English mixing the analyst kept flagging. Write it in French, always.
        system = (
            "You synthesize web research results into a sourced answer for a VC investor. "
            "You may ONLY use the provided sources - never your own background knowledge for "
            "factual/numeric claims. If sources conflict, surface the conflict, do not silently pick one. "
            "If the sources do not answer the question, say so explicitly. "
            "Write the 'answer' field in French, in short, simple, human sentences - the way you'd explain "
            "it out loud to a colleague, not an academic paper. Never mix English words into the French "
            "sentence except a proper noun/product name. "
            'Return JSON: {"answer": "...", "confidence": "high"|"medium"|"low"|"unverified", '
            '"citations": [source indices used, 0-based], "conflicting": true|false, '
            '"conflict_note": "..." or null}'
        )
        user = f"Question: {question}\n\nSources:\n" + json.dumps(sources, indent=2)[:12000]
        if self.mode == "mock":
            return LlmResult(
                mode="mock",
                text=MOCK_DISCLAIMER,
                parsed={
                    "answer": "Impossible de vérifier indépendamment - aucun fournisseur de recherche en direct n'est configuré.",
                    "confidence": "unverified",
                    "citations": [],
                    "conflicting": False,
                    "conflict_note": None,
                },
            )
        return self._call_json(system, user)

    # ------------------------------------------------------------------
    # 2b. Top-down TAM/SAM/SOM estimation - produces an analyst-style,
    #     footnoted market-sizing writeup instead of a bare number. Every
    #     TAM/SAM dollar figure must trace to a provided source; only the
    #     SOM capture-rate range is allowed as a labelled methodology
    #     convention rather than a citation (mirrors how a human analyst
    #     actually does top-down sizing when no report covers the exact
    #     niche - aggregate adjacent markets, apply a sourced geography
    #     split, apply a conservative capture-rate range).
    # ------------------------------------------------------------------
    def estimate_tam_sam_som(self, company_context: dict, sources: list[dict]) -> LlmResult:
        system = (
            "You are a VC analyst producing a top-down TAM/SAM/SOM market-sizing writeup, in the style of a "
            "professional investment memo. Rules: "
            "1) Every dollar figure you give for TAM and SAM must be traceable to one of the provided sources - "
            "cite it with a footnote number. Never state a market-size figure that is not grounded in a source. "
            "2) If no source directly covers the company's exact niche, aggregate 2-3 clearly adjacent/comparable "
            "markets found in the sources, and say so explicitly in your reasoning. "
            "3) SAM should apply a geography/segment percentage that itself comes from a source when possible "
            "(e.g. 'North America is 31% of this market, per source [n]'); if you must estimate it without a "
            "direct source, say so explicitly and do not attach a footnote to that specific number. "
            "4) SOM (realistically capturable over 3-5 years) should apply a conservative, clearly-labelled "
            "capture-rate range (a standard analyst convention, e.g. 1-3% for an early/young category) - label "
            "this explicitly as a methodology convention, NOT a cited fact, and do not attach a footnote to it. "
            "5) If the sources are too thin or irrelevant to support any defensible estimate, return "
            '{"insufficient": true, "reason": "..."} instead of guessing. '
            "6) Write the reasoning fields in French, the way you'd explain it out loud to a colleague, not "
            "an academic paper: short simple sentences, plain corporate vocabulary, one idea per sentence, "
            "with inline footnote markers like [1], [2] placed right after the figure they support. Never "
            "mix English words into the French sentences. "
            'Return ONLY JSON: {"insufficient": false, "currency": "USD"|"EUR", '
            '"tam": {"estimate_low": number, "estimate_high": number, "reasoning": "prose with [1][2] markers"}, '
            '"sam": {"estimate": number, "pct_of_tam": number or null, "reasoning": "prose with markers"}, '
            '"som": {"estimate_low": number, "estimate_high": number, "capture_rate_low_pct": number, '
            '"capture_rate_high_pct": number, "reasoning": "prose, methodology convention not a citation"}, '
            '"footnotes": [{"n": 1, "source_index": 0, "detail": "Source name, key figure quoted, short"}]} '
            "Each of the three reasoning fields must be 2-4 short sentences, roughly 40-80 words - not more. "
            "State the number, state where it comes from, move on. No hedging, no filler, no restating the question."
        )
        user = f"Company context: {json.dumps(company_context)}\n\nSources:\n" + json.dumps(sources, indent=2)[:14000]
        if self.mode == "mock":
            return LlmResult(
                mode="mock", text=MOCK_DISCLAIMER,
                parsed={"insufficient": True, "reason": "No live research/LLM provider configured - mock mode."},
            )
        return self._call_json(system, user, max_tokens=3000)

    # ------------------------------------------------------------------
    # 3a2. Competitive landscape as a function x geography matrix - the
    #      format a sharp analyst actually writes (who covers which slice
    #      of the value chain, where), not a flat list of logos. Every
    #      named player must come from a source; empty cells are left
    #      explicitly empty rather than filled with a guess.
    # ------------------------------------------------------------------
    def build_competitive_landscape(self, company_context: dict, sources: list[dict], deck_text: str | None = None) -> LlmResult:
        company_name = company_context.get("company_name") or "l'entreprise"
        system = (
            f"You are a senior VC analyst writing the competitive-landscape section of a memo for another VC, "
            f"using ONLY the provided sources (plus the company's own pitch-deck text, given separately, for "
            f"describing what THEY do). The reader is an investment professional - do not explain basic VC "
            f"concepts, do not write like an encyclopedia entry, get straight to the sharp, specific point a "
            f"sharp analyst would make. Always call the company by its actual name, "
            f"'{company_name}' - never 'the company', 'the startup', or 'l'entreprise'. Write everything in "
            "French, in short, direct, expert-to-expert sentences. Never mix English words into French "
            "sentences except a proper noun/product name/standard VC term (e.g. keep 'moat' as-is). "
            f"First, in one or two sharp sentences, say what market {company_name} operates in and, if it "
            "clearly serves more than one segment/sub-market, name them - written the way one analyst briefs "
            "another, not a Wikipedia summary. "
            "Then break the value chain into 3-5 functions/capabilities relevant to this category (e.g. for "
            "an AI tooling company: governance, observability, guardrails, gateway, usage billing - adapt to "
            "the actual category). For each function, list which named players cover it in each of THREE "
            "separate geography buckets: 'France', 'Europe' (rest of Europe, excluding France), and "
            "'États-Unis'. Do not merge France into the Europe bucket - never write 'France/Europe' as a "
            "single bucket anywhere. Only name a player in a cell if a source explicitly places them there; "
            "if genuinely no player was found for a function in a given geography, write 'Aucun acteur "
            "identifié' rather than leaving it ambiguous. "
            "Then identify the single closest comparable company (same country/region as the target if "
            "possible), state its key facts (funding, notable clients) ONLY if sourced, and write one simple, "
            "clear sentence on the main competitive risk - analytical judgment, but label it as such, not as "
            "sourced fact. "
            "Then classify the competitive intensity as a one-word snapshot label a VC would use in a deck "
            "review: 'blue_ocean' (few/no direct competitors, category still open), 'red_ocean' (many direct "
            "competitors, intense head-to-head competition), or 'blood_red_ocean' (saturated, commoditized, "
            "price-competitive). Base this only on the density/intensity you observe in the sources, and give "
            "2-3 sentences of justification (not just one) - enough for the reasoning to actually stand on its "
            "own, still short simple French sentences, no padding. "
            "Then research whether there has been any recent M&A / acquisition / consolidation activity in "
            "this sector (a competitor acquired, an incumbent buying into the space, notable exits) - only if "
            "a source mentions it; if none is mentioned, say so plainly rather than guessing. "
            "Finally, grade the startup's moat (defensibility / barrier to entry) using ONLY the standard "
            "three-tier convention: 'No Moat', 'Narrow Moat' (some real but erodable advantage), or 'Wide "
            "Moat' (a durable, hard-to-replicate advantage). The question you're really answering: is this "
            f"business model easily copied, and if a large, well-capitalized incumbent in {company_name}'s "
            "sector decided to enter tomorrow, could they sweep the market? Reason across THREE distinct "
            "moat dimensions before writing your points: (1) data/tech moat - does the product generate or "
            "aggregate PROPRIETARY data that compounds over time (e.g. aggregating data across many "
            "counterparties that no single competitor sees), described in the deck text; this is often the "
            "most overlooked real moat, look for it specifically; (2) team moat - is there a specific, hard-"
            "to-replicate expertise or domain knowledge (e.g. know-how that trains/improves their own "
            "product) described in the deck or sources; (3) competitive-replicability moat - could a "
            "competent team rebuild the visible product quickly with today's AI tooling, or has/could a "
            "large incumbent already build this internally. Then, instead of one dense paragraph, give this "
            "as short, distinct bullet-style points a human can scan in seconds: 2-3 short 'strengths' points "
            "(what genuinely helps their defensibility today, drawing on the three dimensions above), 2-3 "
            "short 'gaps' points (what's missing or fragile), and 1-2 short 'what_would_widen_it' points "
            "(concretely what would need to become true for the moat grade to improve). Each point is ONE "
            "short, punchy, qualitative sentence that shows real analytical depth - do NOT restate a precise "
            "number/euro figure inline inside these short points (that reads as copy-pasted, not reasoned); "
            "cite a footnote marker [n] instead when the point rests on a sourced fact. "
            'Return ONLY JSON: {"market_intro": "1-2 sharp French sentences on the market/segments", '
            '"functions": ["..."], "geographies": ["France", "Europe", "États-Unis"], '
            '"matrix": [{"function": "...", "cells": {"France": "names or Aucun acteur identifié", '
            '"Europe": "names or Aucun acteur identifié", "États-Unis": "names or Aucun acteur identifié"}}], '
            '"closest_comparable": {"name": "...", "description": "1-2 simple sentences, sourced facts only", '
            '"source_index": 0 or null}, '
            '"risk": "1 simple sentence, analyst judgment", '
            '"ocean": {"type": "blue_ocean"|"red_ocean"|"blood_red_ocean", "reasoning": "2-3 simple sentences"}, '
            '"consolidation": "1-2 simple sentences on sector M&A/consolidation, or a plain statement that none was found", '
            '"moat": {"grade": "No Moat"|"Narrow Moat"|"Wide Moat", "strengths": ["short sentence", ...], '
            '"gaps": ["short sentence", ...], "what_would_widen_it": ["short sentence", ...]}, '
            '"footnotes": [{"n": 1, "source_index": 0, "detail": "Source name, key figure quoted, short"}]} '
            "If the sources are too thin to build any of this, return "
            '{"insufficient": true, "reason": "..."}.'
        )
        user = (
            f"Company context: {json.dumps(company_context)}\n\n"
            f"Company's own pitch deck text (for describing what they do/own - NOT a competitor source):\n"
            f"{(deck_text or '')[:20000]}\n\n"
            "Web-search sources on the market/competitors:\n" + json.dumps(sources, indent=2)[:14000]
        )
        if self.mode == "mock":
            return LlmResult(
                mode="mock", text=MOCK_DISCLAIMER,
                parsed={"insufficient": True, "reason": "No live research/LLM provider configured - mock mode."},
            )
        return self._call_json(system, user, max_tokens=3500)

    # ------------------------------------------------------------------
    # 3b. Structured competitor identification - used to render an actual
    #     comparison grid in the UI instead of a wall of prose. Strictly
    #     source-restricted: a competitor only appears here if a source
    #     explicitly names it, and "domain" is only filled in when a
    #     source makes it unambiguous - never guessed, so the frontend can
    #     safely use it for a logo lookup without fabricating anything.
    # ------------------------------------------------------------------
    def identify_competitors(self, question: str, sources: list[dict]) -> LlmResult:
        system = (
            "You extract a structured list of named competitors for a startup, using ONLY the "
            "provided web-search sources - never your own background knowledge, and never invent "
            "a competitor that is not explicitly named in the sources. Write descriptions in French, "
            "in plain, simple sentences - the way you'd explain it to a colleague, not an academic paper. "
            "For each competitor include a website domain ONLY if it is stated in or unambiguous "
            "from the source content/URL; otherwise use null - do not guess a domain. "
            "Also classify each competitor as 'direct' (same core offering, same buyer) or 'indirect' "
            "(adjacent/substitute solution) based only on how the sources describe them, and include their "
            "country/HQ and a rough size descriptor (e.g. 'startup', 'scale-up', 'grand groupe') ONLY when a "
            "source states or clearly implies it - otherwise use null for either field, never guess. "
            'Return JSON: {"competitors": [{"name": "...", "description": "one factual sentence in French, '
            'grounded in the sources", "domain": "example.com" or null, "competitor_type": "direct"|"indirect", '
            '"country": "..." or null, "size": "..." or null, "source_index": 0}], '
            '"confidence": "high"|"medium"|"low"|"unverified"}. '
            "Return at most 8 competitors, most relevant first. If none are explicitly named in "
            "the sources, return an empty list rather than guessing."
        )
        user = f"Question: {question}\n\nSources:\n" + json.dumps(sources, indent=2)[:12000]
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"competitors": [], "confidence": "unverified"})
        return self._call_json(system, user)

    # ------------------------------------------------------------------
    # 3b. Market Dynamics: is this sector growing/consolidating, and is there
    #     active M&A activity - a distinct question from TAM/SAM/SOM (size)
    #     and from the Competitive Landscape (who), grounded ONLY in the
    #     provided web-search sources plus the deck's own market-context text.
    #     A standalone module per analyst feedback, not a buried paragraph
    #     inside Competition.
    # ------------------------------------------------------------------
    def identify_market_dynamics(self, sector: str, hq_country: str | None, sources: list[dict], deck_text: str | None = None) -> LlmResult:
        system = (
            "You are a VC analyst assessing sector-level market dynamics, using ONLY the provided "
            "web-search sources (plus the deck's own market-context text, for company-claim-origin "
            "context only) - never your own background knowledge for a factual/numeric claim, and "
            "never invent a statistic, deal, or acquirer name that isn't in a source. Write every "
            "field in French, short simple sentences, no jargon-stacking, no academic tone. "
            'Return JSON: {'
            '"trend": "growing"|"stable"|"declining"|null (only if a source clearly supports it), '
            '"trend_reasoning": "1-2 sentences grounded in the sources" or null, '
            '"consolidation": "1-3 sentences on M&A / consolidation activity in the sector - name real, '
            'sourced deals/acquirers if the sources give them, otherwise say explicitly that no '
            'consolidation activity was found" or null, '
            '"key_drivers": ["short keyword or phrase", ...] (what is driving growth/decline - regulation, '
            'technology shift, funding climate... - empty list if the sources don\'t support any), '
            '"footnotes": [{"n": 1, "detail": "...", "source_index": 0}], '
            '"insufficient": true|false (true if the sources say nothing useful about sector dynamics)'
            '}'
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"insufficient": True})
        user = (
            f"Sector: {sector}\nHQ country: {hq_country or 'non précisé'}\n\n"
            f"Deck market-context text (for context only, not a source to cite):\n{(deck_text or '')[:8000]}\n\n"
            f"Web-search sources:\n" + json.dumps(sources, indent=2)[:12000]
        )
        return self._call_json(system, user, max_tokens=900)

    # ------------------------------------------------------------------
    # 4. Contradiction detection (spec section 46)
    # ------------------------------------------------------------------
    def detect_contradictions(self, evidence_items: list[dict]) -> LlmResult:
        system = (
            "You audit a list of evidence items (claims, calculated values, external facts) "
            "for internal contradictions. Only flag genuine, explainable contradictions - not "
            "differences of methodology already labelled as such. "
            'Return JSON: {"contradictions": [{"description": "...", "evidence_a": idx, '
            '"evidence_b": idx, "severity": "critical"|"major"|"watch"}]}'
        )
        user = json.dumps(evidence_items, indent=2)[:12000]
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"contradictions": []})
        return self._call_json(system, user)

    # ------------------------------------------------------------------
    # 5. Assumption decomposition (spec section 47)
    # ------------------------------------------------------------------
    def decompose_assumptions(self, claim: str, context: dict) -> LlmResult:
        system = (
            "Given a management projection or claim, decompose it into the concrete, checkable "
            "assumptions that would need to be true for it to hold (e.g. number of customers, "
            "ACV, conversion rate, sales capacity, retention). Write each assumption and reason in "
            "French, as one short, simple, human sentence - not academic phrasing, no jargon-stacking. "
            'Return JSON: {"assumptions": [{"assumption": "...", "plausibility": "plausible"|'
            '"aggressive"|"implausible", "reason": "..."}]}'
        )
        user = f"Claim: {claim}\nContext: {json.dumps(context)}"
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"assumptions": _mock_decompose_assumptions(claim)})
        return self._call_json(system, user)

    # ------------------------------------------------------------------
    # Phase 1 - canonical deal representation: Number Pass B (semantic
    # classification only - Pass A's recognition/structuring is entirely
    # deterministic, see services/number_extraction.py, deliberately NOT an
    # LLM call). "€8m" means nothing without the rest of the deck as
    # context - this is the one place that context is actually given.
    # ------------------------------------------------------------------
    def classify_numbers(self, deck_text: str, numbers: list[dict]) -> LlmResult:
        system = (
            "You are given a list of numbers already recognized in a pitch deck (each with its raw text, "
            "parsed value/unit/currency if known, its surrounding context, and its slide), plus the full deck "
            "text for context. For EACH number (by index), classify what it actually measures - e.g. revenue, "
            "ARR, MRR, GMV, users, customers, growth_rate, retention, churn, cac, ltv, acv, gross_margin, cogs, "
            "burn, runway, pipeline, conversion, sales_cycle, order_volume, units_sold, utilization, engagement, "
            "funding_amount, valuation, market_size_tam, market_size_sam, market_size_som, headcount, other_kpi. "
            "Use 'unclassified' ONLY if truly nothing in the deck lets you tell what it measures - do not guess. "
            "If genuinely ambiguous between 2-3 categories (e.g. an amount that could be revenue OR funding "
            "raised), return your best single guess as semantic_category with medium/low confidence AND list the "
            "other real candidates in candidate_categories - never silently pick one and hide the ambiguity. "
            'Return JSON: {"classifications": [{"index": 0, "semantic_category": "...", '
            '"semantic_confidence": "high"|"medium"|"low", "candidate_categories": ["..."]}]}'
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"classifications": _mock_classify_numbers(numbers)})
        user = f"Numbers to classify:\n{json.dumps(numbers, indent=2)[:14000]}\n\nFull deck text:\n{deck_text[:40000]}"
        return self._call_json(system, user, max_tokens=3000)

    # ------------------------------------------------------------------
    # Phase 1 - canonical deal representation: Pass C, structured
    # Company/Product/Market descriptive fields (kind=fact when the field
    # is objectively descriptive, kind=company_claim when it's inherently
    # an assertion e.g. "differentiation"). Deliberately separate from Pass
    # D (management assertions below) - this pass is "what IS stated",
    # not "what is being argued".
    # ------------------------------------------------------------------
    def extract_structured_fields(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and extract every structured Company/Product/Market field it "
            "states - do not summarize, extract each field as its own item, verbatim or near-verbatim from the "
            "text. Only extract a field if the deck actually states it - never infer or guess a value. "
            "claim_type must be one of: company_identity (name, legal name, founding date, HQ, countries of "
            "operation), funding_history (round, amount raised, valuation, investors), ownership, "
            "team_background, product_description, product_architecture, product_roadmap, pricing, "
            "differentiation, distribution, dependency, market_definition (how the deck defines/scopes its "
            "market - methodology, assumptions - NOT the size number itself, that's captured separately). "
            "Set kind='fact' for objectively descriptive fields (company_identity, funding_history, ownership, "
            "team_background, product_description, product_roadmap, distribution) and kind='company_claim' for "
            "fields that are inherently an assertion or interpretation (differentiation, pricing rationale, "
            "product_architecture claims of superiority, market_definition methodology choices). "
            'Return JSON: {"fields": [{"claim_type": "...", "kind": "fact"|"company_claim", "text": "verbatim '
            'or near-verbatim from the deck", "context": "1 surrounding sentence", "slide_reference": "N" or '
            'null}]}. Extract as many as the deck actually supports - do not artificially limit the count, and '
            "do not force something into a field the deck doesn't state."
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"fields": _mock_extract_structured_fields(deck_text)})
        return self._call_json(system, deck_text[:60000], max_tokens=4000)

    # ------------------------------------------------------------------
    # Phase 1 - canonical deal representation: Pass D, management
    # ASSERTIONS specifically - the narrative/evaluative claims a sharp VC
    # would want to challenge ("we are the market leader", "no significant
    # competitors", "our technology is proprietary"), as opposed to Pass
    # C's plain descriptive fields. Each gets required_evidence (what would
    # verify it) and potential_challenge (how an analyst would push back) -
    # this is what makes it usable by a future research/challenge pass,
    # not just a longer list of extracted text.
    # ------------------------------------------------------------------
    def extract_management_claims(self, deck_text: str) -> LlmResult:
        system = (
            "Read this pitch deck's raw text and extract every management ASSERTION - a statement that argues "
            "or evaluates, not just describes. Examples of what counts: 'we are the market leader', 'there are "
            "no significant competitors', 'our technology is proprietary', 'we will reach EUR50M revenue by "
            "2030', 'our retention is best-in-class'. Examples of what does NOT count (that's Pass C, not this "
            "one): 'the company is based in Paris', 'the CEO is Jane Doe' - plain facts, not arguable claims. "
            "For each assertion, write in French: required_evidence (what evidence would actually verify or "
            "refute this - be specific, not 'more data'), and potential_challenge (the sharp, specific way an "
            "experienced VC would push back on this claim - one sentence, no hedging). claim_type must be one "
            "of: competitive_position, differentiation, traction_projection, market_definition, pricing, "
            "product_roadmap, other. "
            'Return JSON: {"claims": [{"claim_type": "...", "text": "verbatim or near-verbatim assertion", '
            '"context": "1 surrounding sentence", "slide_reference": "N" or null, '
            '"required_evidence": "...", "potential_challenge": "..."}]}. '
            "Return an empty list if the deck genuinely contains no such assertions - do not invent one to "
            "avoid an empty result."
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"claims": _mock_extract_management_claims(deck_text)})
        return self._call_json(system, deck_text[:60000], max_tokens=3000)

    # ------------------------------------------------------------------
    # 6. Generic qualitative reasoning step (used for the "investment
    #    implication" step of the reasoning loop, and for memo prose)
    # ------------------------------------------------------------------
    def reason(self, system: str, user: str, max_tokens: int = 1500) -> LlmResult:
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed=None)
        text = self._call(system, user, max_tokens)
        return LlmResult(mode="live", text=text, parsed=None)


_llm_singleton: LlmClient | None = None


def get_llm_client() -> LlmClient:
    global _llm_singleton
    if _llm_singleton is None:
        _llm_singleton = LlmClient()
    return _llm_singleton
