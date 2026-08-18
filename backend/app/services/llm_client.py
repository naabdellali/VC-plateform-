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
            '{"category": one of ["market_size","competitors","traction_metric","team_background",'
            '"financials","business_model","fundraising_history","other"], '
            '"claim": short human-readable statement, "value": the raw number/text if any, '
            '"slide_reference": best-guess slide number or null}. '
            "Do not infer anything not stated in the text. Do not invent numbers."
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
            claims.append({"category": "traction_metric", "claim": m.group(0).strip(), "value": m.group(2), "slide_reference": None})
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
            "6) Write the reasoning fields as a VC analyst would, in French, in plain prose, with inline footnote "
            "markers like [1], [2] placed right after the figure they support. "
            'Return ONLY JSON: {"insufficient": false, "currency": "USD"|"EUR", '
            '"tam": {"estimate_low": number, "estimate_high": number, "reasoning": "prose with [1][2] markers"}, '
            '"sam": {"estimate": number, "pct_of_tam": number or null, "reasoning": "prose with markers"}, '
            '"som": {"estimate_low": number, "estimate_high": number, "capture_rate_low_pct": number, '
            '"capture_rate_high_pct": number, "reasoning": "prose, methodology convention not a citation"}, '
            '"footnotes": [{"n": 1, "source_index": 0, "detail": "Source name, key figure quoted, short"}]} '
            "Style: write like a sharp VC analyst memo, not an AI assistant - terse, declarative, no hedging "
            "filler, no restating the question. Each of the three reasoning fields must be 2-4 sentences, "
            "roughly 40-80 words - not more. State the number, state where it comes from, move on."
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
            "You are a sharp VC analyst mapping the competitive landscape for a startup, using ONLY the "
            "provided sources. Break the value chain into 3-5 functions/capabilities relevant to this "
            "category (e.g. for an AI tooling company: governance, observability, guardrails, gateway, "
            "usage billing - adapt to the actual category). For each function, list which named players "
            "cover it in each of two geography buckets: 'France / Europe' and 'États-Unis'. Only name a "
            "player in a cell if a source explicitly places them there; otherwise write 'Quasi absent' or "
            "'—' rather than guessing. "
            "Then identify the single closest comparable company (same country/region as the target if "
            "possible), state its key facts (funding, notable clients) ONLY if sourced, and write one sharp "
            "sentence on what differentiates the target and one sharp sentence on the main competitive risk "
            "- both may be analytical judgment, but label them as such, not as sourced fact. "
            'Return ONLY JSON: {"functions": ["..."], "geographies": ["France / Europe", "États-Unis"], '
            '"matrix": [{"function": "...", "cells": {"France / Europe": "names or Quasi absent", '
            '"États-Unis": "names or Quasi absent"}}], '
            '"closest_comparable": {"name": "...", "description": "1-2 sentences, sourced facts only", '
            '"source_index": 0 or null}, '
            '"differentiator": "1 sharp sentence, analyst judgment", "risk": "1 sharp sentence, analyst judgment", '
            '"footnotes": [{"n": 1, "source_index": 0, "detail": "Source name, key figure quoted, short"}]} '
            "Style: terse, declarative, like a real analyst memo - no hedging, no filler, no restating the "
            "question. If the sources are too thin to build any of this, return "
            '{"insufficient": true, "reason": "..."}.'
        )
        user = f"Company context: {json.dumps(company_context)}\n\nSources:\n" + json.dumps(sources, indent=2)[:14000]
        if self.mode == "mock":
            return LlmResult(
                mode="mock", text=MOCK_DISCLAIMER,
                parsed={"insufficient": True, "reason": "No live research/LLM provider configured - mock mode."},
            )
        return self._call_json(system, user, max_tokens=2500)

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
            "a competitor that is not explicitly named in the sources. "
            "For each competitor include a website domain ONLY if it is stated in or unambiguous "
            "from the source content/URL; otherwise use null - do not guess a domain. "
            'Return JSON: {"competitors": [{"name": "...", "description": "one factual sentence '
            'grounded in the sources", "domain": "example.com" or null, "source_index": 0}], '
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
            "ACV, conversion rate, sales capacity, retention). "
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
