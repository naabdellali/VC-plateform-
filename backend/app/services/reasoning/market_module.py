"""
Market module: "annonce vs recalcule" (spec section 6).

Automatic pass (`run_auto`):
  extract -> identify_unknowns -> research -> verify -> benchmark(partial)
It deliberately does NOT invent a bottom-up/top-down calculation out of
thin air - percentages like "addressable %" are exactly the kind of
number an LLM will happily hallucinate if asked to guess them. Instead,
the automatic pass flags what's missing and researches external market
data; the actual independent calculation is triggered explicitly via
`recalculate()` once real inputs are available (company-provided,
analyst-provided, or backed by a cited external source) - this is the
human-in-the-loop principle (spec section 52) applied to the single
riskiest number in an early-stage memo.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence,
)
from app.services.calc.market import tam_bottom_up, tam_top_down, compare_estimates
from app.services.calc.parsing import parse_money
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result
from app.services.reasoning.red_flags import add_red_flag
from app.models import RedFlagSeverity

MODULE = "market"


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract -------------------------------------------------
    market_claims = [
        c for c in (deck.extracted_claims_json or []) if c.get("category") == "market_size"
    ]
    deck_value = None
    deck_evidence_ids = []
    for c in market_claims:
        parsed_value = parse_money(c.get("value") or c.get("claim", ""))
        if parsed_value and deck_value is None:
            deck_value = parsed_value
        ev = add_evidence(
            db,
            company_id=company.id,
            module=MODULE,
            claim=c.get("claim", "Market size claim"),
            value=c.get("value"),
            value_type="currency_eur",
            origin=EvidenceOrigin.company_claim,
            source_tier=SourceTier.deck,
            confidence=Confidence.medium,  # explicit in the deck, but self-reported
            source_name=f"Pitch deck ({deck.filename})",
            supporting_excerpt=c.get("claim"),
        )
        deck_evidence_ids.append(ev.id)
    trace.add("extract", {"claims_found": len(market_claims), "deck_value_eur": deck_value}, deck_evidence_ids)

    # --- 2. identify_unknowns ----------------------------------------
    unknowns = []
    if deck_value is None:
        unknowns.append("No parseable market-size figure found in the deck.")
    if not any("methodology" in (c.get("claim", "").lower()) for c in market_claims):
        unknowns.append("Deck does not disclose the methodology behind its market-size claim.")
    unknowns.append("Bottom-up/top-down inputs (customer count, ACV, segment %) not yet confirmed - use POST /recalculate to supply them.")
    trace.add("identify_unknowns", unknowns)

    # --- 3. research (contextual, per spec section 40) ----------------
    question = f"What is the independently reported market size and growth rate for {company.name}'s sector ({company.sector or 'unspecified sector'})?"
    query_result = llm.generate_search_queries(question, {"sector": company.sector, "hq_country": company.hq_country, "business_model": company.business_model.value if company.business_model else None})
    queries = (query_result.parsed or {}).get("queries", [question]) if query_result.parsed else [question]

    all_sources = []
    for q in queries[:3]:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            all_sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
    trace.add("research", {"queries": queries, "sources_found": len(all_sources), "search_mode": search.mode})

    # --- 4. verify / synthesize ---------------------------------------
    synth = llm.synthesize_research(question, all_sources)
    synth_payload = synth.parsed or {}
    synth_evidence_ids = []

    for idx in synth_payload.get("citations", []) if synth_payload else []:
        if idx < len(all_sources):
            s = all_sources[idx]
            ev = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim=f"External market data point for {company.sector or 'sector'}",
                value=None, origin=EvidenceOrigin.external_source,
                source_tier=SourceTier.tier2_secondary, confidence=Confidence.medium,
                source_name=s["title"], source_url=s["url"],
                source_publication_date=s.get("published_date"),
                supporting_excerpt=s["content"][:500],
            )
            synth_evidence_ids.append(ev.id)

    synth_conf = {"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
        synth_payload.get("confidence"), Confidence.unverified
    )
    synth_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Independent research synthesis on market size/growth",
        value=synth_payload.get("answer", "Unable to independently verify."),
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence=synth_conf,
        methodology="LLM synthesis over web-search results, source-restricted (no background knowledge for numbers).",
    )
    synth_evidence_ids.append(synth_ev.id)
    trace.add("verify", synth_payload, synth_evidence_ids)

    if synth_payload.get("conflicting"):
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="market",
            severity=RedFlagSeverity.watch,
            explanation="Independent sources disagree on this market's size/growth - " + (synth_payload.get("conflict_note") or ""),
            evidence_id=synth_ev.id,
            potential_impact="Market-sizing conclusion carries wider uncertainty than usual.",
            resolving_information="Manually review the conflicting sources cited in the evidence trail.",
        )

    # --- 5. benchmark (partial: flag if deck value looks disproportionate to research) ---
    external_value = parse_money(synth_payload.get("answer", "")) if synth_payload else None
    discrepancy_note = None
    if deck_value and external_value:
        cmp = compare_estimates(deck_value, tam_top_down(external_value, 1.0, 1.0))
        discrepancy_note = cmp["verdict"]
        if cmp["ratio_platform_over_company"] is not None and cmp["ratio_platform_over_company"] < 0.5:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="market",
                severity=RedFlagSeverity.major,
                explanation=f"Deck's market size ({deck_value:,.0f}) looks substantially larger than what independent research supports ({external_value:,.0f}).",
                evidence_id=synth_ev.id,
                potential_impact="If the addressable market is smaller than claimed, growth assumptions and valuation may need to be revisited.",
                resolving_information="Ask management for their exact market-sizing methodology and primary sources.",
            )
    trace.add("benchmark", {"deck_value_eur": deck_value, "external_reference_value_eur": external_value, "note": discrepancy_note})

    status = ModuleStatus.needs_review if deck_value or external_value else ModuleStatus.insufficient_evidence
    headline = "Independent recalculation pending analyst input" if deck_value else "No market-size claim found in deck"
    if deck_value:
        headline = f"Deck claims {deck_value:,.0f} EUR. " + (discrepancy_note or "Independent recalculation pending analyst input (see /recalculate).")

    upsert_module_result(
        db, company, MODULE,
        status=status, headline=headline,
        deck_value=str(deck_value) if deck_value else None,
        platform_value=None,
        discrepancy_explanation=discrepancy_note,
        trace=trace, llm_mode=llm.mode,
    )


def recalculate(
    db: Session, company: Company, *,
    methodology: str,  # "bottom_up" | "top_down"
    inputs: dict,
    assumptions: list[str],
) -> dict:
    """
    Human-in-the-loop independent calculation, triggered explicitly with
    real inputs (spec section 52). This is what actually fills
    ModuleResult.platform_value - never the automatic pass alone.
    """
    from app.models import ModuleResult

    if methodology == "bottom_up":
        estimate = tam_bottom_up(
            num_potential_customers=inputs["num_potential_customers"],
            avg_annual_spend_eur=inputs["avg_annual_spend_eur"],
            realistic_penetration=inputs.get("realistic_penetration", 1.0),
            assumptions=assumptions,
        )
    elif methodology == "top_down":
        estimate = tam_top_down(
            industry_size_eur=inputs["industry_size_eur"],
            relevant_segment_pct=inputs["relevant_segment_pct"],
            addressable_pct=inputs["addressable_pct"],
            assumptions=assumptions,
        )
    else:
        raise ValueError("methodology must be 'bottom_up' or 'top_down'")

    calc_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Platform-calculated independent market size estimate",
        value=round(estimate.value_eur, 2), value_type="currency_eur",
        origin=EvidenceOrigin.platform_calculation,
        source_tier=SourceTier.calculation,
        confidence=Confidence.medium,
        methodology=estimate.methodology,
        assumptions=assumptions,
    )

    result = (
        db.query(ModuleResult)
        .filter(ModuleResult.company_id == company.id, ModuleResult.module == MODULE)
        .one_or_none()
    )
    deck_value = float(result.deck_value) if result and result.deck_value else None
    comparison = compare_estimates(deck_value, estimate) if deck_value else None

    trace = ReasoningTrace()
    if result and result.reasoning_json:
        trace.steps = result.reasoning_json.get("steps", [])
    trace.add("calculate", estimate.as_evidence_payload(), [calc_ev.id])
    if comparison:
        trace.add("reality_check", comparison)

    headline = f"Platform estimate: {estimate.value_eur:,.0f} EUR ({methodology.replace('_', '-')})"
    if comparison:
        headline += f". Deck claims {deck_value:,.0f} EUR - {comparison['verdict']}"
        if comparison["ratio_platform_over_company"] is not None and comparison["ratio_platform_over_company"] < 0.5:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="market",
                severity=RedFlagSeverity.major,
                explanation=f"Analyst-confirmed independent TAM ({estimate.value_eur:,.0f}) is less than half the deck's claim ({deck_value:,.0f}).",
                evidence_id=calc_ev.id,
                potential_impact="Market may be materially smaller than the investment case assumes.",
            )

    upsert_module_result(
        db, company, MODULE,
        status=ModuleStatus.complete,
        headline=headline,
        deck_value=result.deck_value if result else None,
        platform_value=str(round(estimate.value_eur, 2)),
        discrepancy_explanation=comparison["verdict"] if comparison else None,
        trace=trace, llm_mode=get_llm_client().mode,
    )

    return {"estimate": estimate.as_evidence_payload(), "comparison": comparison}
