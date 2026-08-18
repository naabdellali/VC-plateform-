"""
Market module: independent top-down TAM/SAM/SOM (spec section 6, refined
per analyst feedback on the live product).

Automatic pass (`run_auto`) now ALWAYS produces the platform's own
top-down TAM/SAM/SOM estimate - this is what the tray tile and the module
hero lead with, before the user ever compares it to what the deck claims.
It is not a blind guess: every TAM/SAM dollar figure must be traceable to
a real source found via web research (aggregating adjacent/comparable
markets when no report covers the exact niche, exactly like a human
analyst would), with numbered footnotes. Only the SOM capture-rate range
is allowed as an explicitly-labelled analyst convention rather than a
citation. If the research doesn't support a defensible estimate, the
module says so plainly instead of fabricating one.

The deck's own market-size claim (if any) is still extracted, but it is
now used only for the "compare to what the deck claims" section, shown
LAST rather than leading the page.

`recalculate()` remains available as a human-in-the-loop override, for
when an analyst wants to substitute their own bottom-up/top-down inputs
for the platform's automatic estimate.
"""
from __future__ import annotations

import json

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


def _fmt(n, symbol: str) -> str:
    if n is None:
        return "?"
    try:
        n = float(n)
    except (TypeError, ValueError):
        return "?"
    if abs(n) >= 1e9:
        return f"{symbol}{n / 1e9:.1f}B"
    if abs(n) >= 1e6:
        return f"{symbol}{n / 1e6:.0f}M"
    if abs(n) >= 1e3:
        return f"{symbol}{n / 1e3:.0f}K"
    return f"{symbol}{n:,.0f}"


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract: deck's own market-size claim, kept for the comparison shown at the end ---
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
            db, company_id=company.id, module=MODULE,
            claim=c.get("claim", "Market size claim"), value=c.get("value"), value_type="currency_eur",
            origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
            confidence=Confidence.medium, source_name=f"Pitch deck ({deck.filename})",
            supporting_excerpt=c.get("claim"),
        )
        deck_evidence_ids.append(ev.id)
    trace.add("extract", {"claims_found": len(market_claims), "deck_value_eur": deck_value}, deck_evidence_ids)

    # --- 2. research: TAM/adjacent-market sources + a geography/segment split ------------------
    context = {
        "sector": company.sector, "hq_country": company.hq_country,
        "business_model": company.business_model.value if company.business_model else None,
        "stage": company.stage.value if company.stage else None,
    }
    tam_q = (
        f"What is the total addressable market (TAM) size and growth forecast for "
        f"{company.sector or 'this company'}'s sector? If no report covers this exact niche, include the "
        "closest adjacent or comparable market categories and their sizes."
    )
    geo_q = f"What percentage share of the {company.sector or 'this'} market is in North America vs Europe vs rest of world?"
    q1 = llm.generate_search_queries(tam_q, context)
    queries = (q1.parsed or {}).get("queries", [tam_q]) if q1.parsed else [tam_q]
    queries = list(queries[:3]) + [geo_q]

    sources = []
    for q in queries:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
    trace.add("research", {"queries": queries, "sources_found": len(sources), "search_mode": search.mode})

    # --- 3. calculate: the platform's own top-down TAM/SAM/SOM, always attempted --------------
    tam_result = llm.estimate_tam_sam_som(context, sources)
    payload = tam_result.parsed or {"insufficient": True, "reason": "Could not parse the model's output."}

    if not sources:
        payload = {"insufficient": True, "reason": "No web-search results were available to ground a TAM/SAM/SOM estimate."}

    structured = None
    platform_value = None

    if payload.get("insufficient"):
        status = ModuleStatus.insufficient_evidence
        headline = f"We could not establish an independent TAM/SAM/SOM yet - {payload.get('reason', 'insufficient sourced data')}."
        trace.add("calculate", {"insufficient": True, "reason": payload.get("reason")})
    else:
        currency = payload.get("currency") or "USD"
        symbol = "$" if currency == "USD" else "€"

        footnotes = []
        for fn in payload.get("footnotes", []) or []:
            idx = fn.get("source_index")
            src = sources[idx] if isinstance(idx, int) and 0 <= idx < len(sources) else None
            footnotes.append({
                "n": fn.get("n"),
                "detail": fn.get("detail"),
                "source_url": src["url"] if src else None,
                "source_name": src["title"] if src else None,
            })

        structured = {
            "currency": currency,
            "tam": payload.get("tam") or {},
            "sam": payload.get("sam") or {},
            "som": payload.get("som") or {},
            "footnotes": footnotes,
        }

        calc_ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim="Independent top-down TAM/SAM/SOM estimate", value=json.dumps(structured),
            value_type="tam_sam_som_json",
            origin=EvidenceOrigin.platform_calculation,
            source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
            confidence=Confidence.medium,
            methodology=(
                "Top-down aggregation of adjacent/comparable market sources with a sourced geography split for "
                "SAM; SOM applies a standard early-market capture-rate convention, not a cited figure."
            ),
        )
        trace.add("calculate", structured, [calc_ev.id])

        tam, sam, som = structured["tam"], structured["sam"], structured["som"]
        headline = (
            f"TAM {_fmt(tam.get('estimate_low'), symbol)}–{_fmt(tam.get('estimate_high'), symbol)} · "
            f"SAM {_fmt(sam.get('estimate'), symbol)} · "
            f"SOM {_fmt(som.get('estimate_low'), symbol)}–{_fmt(som.get('estimate_high'), symbol)} (top-down)"
        )
        platform_value = json.dumps(structured)
        status = ModuleStatus.complete

    # --- 4. compare to what the deck claims - LAST, secondary to our own estimate -------------
    discrepancy_note = None
    if structured and deck_value:
        sam_val = (structured.get("sam") or {}).get("estimate")
        if structured["currency"] == "EUR" and sam_val:
            discrepancy_note = f"Deck claims {deck_value:,.0f} EUR; our independent SAM estimate is €{sam_val:,.0f}."
        else:
            discrepancy_note = (
                f"Deck claims {deck_value:,.0f} EUR; our independent estimate above is in {structured['currency']} - "
                "compare directionally rather than exactly, since the currencies differ."
            )
    elif structured and not deck_value:
        discrepancy_note = "The deck did not provide its own market-size figure to compare against."
    trace.add("reality_check", {"deck_value_eur": deck_value, "note": discrepancy_note})

    if structured and deck_value and structured["currency"] == "EUR":
        sam_val = (structured.get("sam") or {}).get("estimate")
        if sam_val and deck_value > sam_val * 2:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="market",
                severity=RedFlagSeverity.major,
                explanation=f"Deck's market size ({deck_value:,.0f} EUR) is more than double our independent SAM estimate (€{sam_val:,.0f}).",
                evidence_id=None,
                potential_impact="If the addressable market is smaller than claimed, growth assumptions and valuation may need to be revisited.",
                resolving_information="Ask management for their exact market-sizing methodology and primary sources.",
            )

    upsert_module_result(
        db, company, MODULE,
        status=status, headline=headline,
        deck_value=str(deck_value) if deck_value else None,
        platform_value=platform_value,
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
    Human-in-the-loop override: substitute the analyst's own bottom-up/
    top-down inputs for the platform's automatic top-down estimate above.
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
        claim="Analyst-overridden independent market size estimate",
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

    headline = f"Analyst override: {estimate.value_eur:,.0f} EUR ({methodology.replace('_', '-')})"
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
