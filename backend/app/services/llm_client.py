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
            parsed = None
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
        return self._call_json(system, deck_text[:15000])

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
        return self._call_json(system, deck_text[:8000])

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
            "Read this pitch deck's raw text and identify its technology architecture. Write everything in "
            "French, in short, simple, human sentences - not academic, not a list of jargon fragments. "
            "First, write one or two plain sentences summarizing what their technology actually is and what "
            "they own/built (a normal person should understand it immediately, no jargon-only fragments like "
            "'GPS, geolocation, critical data'). "
            "Then list every named third-party dependency the deck mentions or clearly implies the product "
            "relies on (APIs, cloud providers, foundation models/LLMs, payment providers, data providers, "
            "hardware suppliers, infrastructure providers). For each, write a short PLAIN SENTENCE (not a "
            "fragment) explaining what it's used for, and judge whether it appears CRITICAL - i.e. the "
            "product could not function as described without it - based only on how the deck frames it. "
            "Separately, list short plain sentences describing what the deck claims is proprietary/built "
            "in-house. Never invent a dependency that isn't stated or clearly implied in the text. "
            'Return JSON: {"tech_summary": "1-2 simple French sentences on what their tech is/does", '
            '"dependencies": [{"name": "...", "role": "a full simple French sentence - what it powers and why", '
            '"critical": true|false, "evidence_text": "verbatim short snippet from the deck"}], '
            '"proprietary": ["short simple French sentence", ...]}. '
            "If the deck says nothing about technology/architecture, return empty lists and null tech_summary."
        )
        if self.mode == "mock":
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"tech_summary": None, "dependencies": [], "proprietary": []})
        return self._call_json(system, deck_text[:12000])

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
        return self._call_json(system, deck_text[:10000], max_tokens=300)

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
        return self._call_json(system, deck_text[:10000], max_tokens=200)

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
        return self._call_json(system, deck_text[:10000], max_tokens=400)

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
        system = (
            "You synthesize web research results into a sourced answer for a VC investor. "
            "You may ONLY use the provided sources - never your own background knowledge for "
            "factual/numeric claims. If sources conflict, surface the conflict, do not silently pick one. "
            "If the sources do not answer the question, say so explicitly. "
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
                    "answer": "Unable to independently verify - no live research provider configured.",
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
    def build_competitive_landscape(self, company_context: dict, sources: list[dict]) -> LlmResult:
        system = (
            "You are a VC analyst mapping the competitive landscape for a startup, using ONLY the provided "
            "sources. Write everything in French. Write the way you'd explain it out loud to a colleague, "
            "not an academic paper: short sentences, plain corporate vocabulary, one idea per sentence. Never "
            "mix English words into French sentences except a proper noun/product name. "
            "First, in one or two simple sentences, say what market the company operates in and, if it "
            "clearly serves more than one segment/sub-market, name them. "
            "Then break the value chain into 3-5 functions/capabilities relevant to this category (e.g. for "
            "an AI tooling company: governance, observability, guardrails, gateway, usage billing - adapt to "
            "the actual category). For each function, list which named players cover it in each of THREE "
            "separate geography buckets: 'France', 'Europe' (rest of Europe, excluding France), and "
            "'États-Unis'. Do not merge France into the Europe bucket. Only name a player in a cell if a "
            "source explicitly places them there; otherwise write 'Quasi absent' or '—' rather than guessing. "
            "Then identify the single closest comparable company (same country/region as the target if "
            "possible), state its key facts (funding, notable clients) ONLY if sourced, and write one simple, "
            "clear sentence on what differentiates the target and one on the main competitive risk - both may "
            "be analytical judgment, but label them as such, not as sourced fact. "
            "Then classify the competitive intensity as a one-word snapshot label a VC would use in a deck "
            "review: 'blue_ocean' (few/no direct competitors, category still open), 'red_ocean' (many direct "
            "competitors, intense head-to-head competition), or 'blood_red_ocean' (saturated, commoditized, "
            "price-competitive). Base this only on the density/intensity you observe in the sources, and give "
            "one short, plain-French justification sentence. "
            "Then research whether there has been any recent M&A / acquisition / consolidation activity in "
            "this sector (a competitor acquired, an incumbent buying into the space, notable exits) - only if "
            "a source mentions it; if none is mentioned, say so plainly rather than guessing. "
            "Finally, grade the startup's moat (defensibility / barrier to entry) using ONLY the standard "
            "three-tier convention: 'No Moat', 'Narrow Moat' (some real but erodable advantage), or 'Wide "
            "Moat' (a durable, hard-to-replicate advantage). Then, instead of one dense paragraph, give this "
            "as short, distinct bullet-style points a human can scan in seconds: 2-3 short 'strengths' points "
            "(what genuinely helps their defensibility today), 2-3 short 'gaps' points (what's missing or "
            "fragile), and 1-2 short 'what_would_widen_it' points (concretely what would need to become true "
            "for the moat grade to improve). Each point is ONE short simple sentence, citing a footnote marker "
            "[n] where it rests on a sourced fact, otherwise labelled as analyst judgment implicitly by not "
            "having a footnote. "
            'Return ONLY JSON: {"market_intro": "1-2 simple French sentences on the market/segments", '
            '"functions": ["..."], "geographies": ["France", "Europe", "États-Unis"], '
            '"matrix": [{"function": "...", "cells": {"France": "names or Quasi absent", '
            '"Europe": "names or Quasi absent", "États-Unis": "names or Quasi absent"}}], '
            '"closest_comparable": {"name": "...", "description": "1-2 simple sentences, sourced facts only", '
            '"source_index": 0 or null}, '
            '"differentiator": "1 simple sentence, analyst judgment", "risk": "1 simple sentence, analyst judgment", '
            '"ocean": {"type": "blue_ocean"|"red_ocean"|"blood_red_ocean", "reasoning": "1 simple sentence"}, '
            '"consolidation": "1-2 simple sentences on sector M&A/consolidation, or a plain statement that none was found", '
            '"moat": {"grade": "No Moat"|"Narrow Moat"|"Wide Moat", "strengths": ["short sentence", ...], '
            '"gaps": ["short sentence", ...], "what_would_widen_it": ["short sentence", ...]}, '
            '"footnotes": [{"n": 1, "source_index": 0, "detail": "Source name, key figure quoted, short"}]} '
            "If the sources are too thin to build any of this, return "
            '{"insufficient": true, "reason": "..."}.'
        )
        user = f"Company context: {json.dumps(company_context)}\n\nSources:\n" + json.dumps(sources, indent=2)[:14000]
        if self.mode == "mock":
            return LlmResult(
                mode="mock", text=MOCK_DISCLAIMER,
                parsed={"insufficient": True, "reason": "No live research/LLM provider configured - mock mode."},
            )
        return self._call_json(system, user, max_tokens=3000)

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
            return LlmResult(mode="mock", text=MOCK_DISCLAIMER, parsed={"assumptions": []})
        return self._call_json(system, user)

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
