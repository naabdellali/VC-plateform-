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

Before sizing anything, the module also identifies the company's precise
target SEGMENT from the deck (identify_target_segment) - not just
`company.sector`, which is often a broad category (whether typed by the
analyst in the upload form or inferred from the deck) shared by every
company in the space. Concretely: "insurance software" is a category;
"parametric underwriting and claims software for agricultural insurers"
is the segment. The segment description drives the PRIMARY TAM search
and anchors SAM's narrowing in estimate_tam_sam_som's prompt; `sector`
is kept as the explicit fallback/adjacent-market anchor, never dropped -
just no longer the first and only thing searched for.

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
    # Deliberately does NOT include company.business_model here: the workspace form defaults it
    # to a fixed value that has nothing to do with market sizing, and letting it leak into this
    # context biased query generation toward the wrong industry entirely (e.g. "SaaS market" for
    # a real-estate services company). Sector - freshly inferred from the deck above if it was
    # blank - is what actually drives what gets searched for.
    context = {
        "sector": company.sector, "hq_country": company.hq_country,
        "stage": company.stage.value if company.stage else None,
    }
    if not company.sector:
        # No sector on record and the deck didn't make it inferable either - don't guess a market.
        trace.add("identify_unknowns", ["Le secteur de l'entreprise n'est pas connu - impossible d'ancrer une recherche TAM/SAM/SOM sur la bonne industrie."])
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Impossible d'estimer la taille du marché pour l'instant - le secteur de l'entreprise n'est pas connu. Renseigne-le sur la fiche de l'entreprise puis réimporte le deck.",
            deck_value=str(deck_value) if deck_value else None, platform_value=None, discrepancy_explanation=None,
            trace=trace, llm_mode=llm.mode,
        )
        return

    # --- 2a. narrow "sector" (often a broad category, whether typed by the analyst in the
    #         upload form or inferred above) down to the precise sub-segment the deck actually
    #         describes - fixes a real quality issue: sizing "the insurance software market" for
    #         a company that specifically builds parametric underwriting tools for agricultural
    #         insurers. Always runs (not conditional on how `sector` was set), so a manually-typed
    #         broad sector doesn't skip this narrowing step. `sector` itself is kept as the
    #         explicit fallback/adjacent-market anchor when the deck doesn't support narrowing
    #         further - it never gets dropped, just no longer the FIRST thing searched for.
    segment_result = llm.identify_target_segment(deck.raw_text, company.sector)
    segment_payload = segment_result.parsed or {}
    segment_description = segment_payload.get("segment_description")
    buyer_persona = segment_payload.get("buyer_persona")
    segment_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Segment de marché précis ciblé par l'entreprise (identifié à partir du deck)",
        value=segment_description or "Non déterminable au-delà de la catégorie large - le deck ne donne pas assez de détail pour préciser davantage.",
        origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
        confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
            segment_payload.get("confidence"), Confidence.unverified
        ),
        source_name=f"Pitch deck ({deck.filename})",
    )
    trace.add("extract", {"segment_description": segment_description, "buyer_persona": buyer_persona}, [segment_ev.id])
    context["segment_description"] = segment_description
    context["buyer_persona"] = buyer_persona

    if segment_description:
        tam_q = (
            f"What is the total addressable market (TAM) size and growth forecast for this specific market "
            f"segment: {segment_description}? This is a narrower segment within the broader "
            f"'{company.sector}' category - search for the segment specifically first. Only if no report "
            f"covers this exact niche, fall back to the closest adjacent or comparable market categories "
            f"(including the broader '{company.sector}' category itself) and their sizes."
        )
        # A dedicated broad-category query alongside the segment one, so the LLM still has
        # adjacent-market sources to fall back on per estimate_tam_sam_som's rule 2 - narrowing
        # the PRIMARY query must not starve the fallback path of sources entirely.
        broad_q = f"What is the total addressable market (TAM) size for the broader {company.sector} category?"
    else:
        tam_q = (
            f"What is the total addressable market (TAM) size and growth forecast for the following industry: "
            f"{company.sector}? If no report covers this exact niche, include the closest adjacent or comparable "
            "market categories and their sizes."
        )
        broad_q = None
    geo_q = (
        f"What percentage share of the {segment_description or company.sector} market is in "
        "North America vs Europe vs rest of world?"
    )
    q1 = llm.generate_search_queries(tam_q, context)
    queries = (q1.parsed or {}).get("queries", [tam_q]) if q1.parsed else [tam_q]
    queries = list(queries[:3]) + ([broad_q] if broad_q else []) + [geo_q]

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
    # Segment info is recorded on platform_value regardless of whether TAM/SAM/SOM itself
    # succeeded - other modules (e.g. competition_module) read it the same way
    # competition_module already reads Technology's platform_value, and identifying the
    # segment doesn't depend on whether market-sizing sources were actually found.
    platform_value = json.dumps({"segment_description": segment_description, "buyer_persona": buyer_persona})

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
            "segment_description": segment_description,
            "buyer_persona": buyer_persona,
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
            f"SOM {_fmt(som.get('estimate_low'), symbol)}–{_fmt(som.get('estimate_high'), symbol)}"
        )
        platform_value = json.dumps(structured)
        status = ModuleStatus.complete

    # --- 4. compare to what the deck claims - LAST, secondary to our own estimate -------------
    discrepancy_note = None
    if structured and deck_value:
        sam_val = (structured.get("sam") or {}).get("estimate")
        if structured["currency"] == "EUR" and sam_val:
            discrepancy_note = f"Le deck annonce {deck_value:,.0f} EUR ; notre estimation SAM indépendante est de {sam_val:,.0f} EUR."
        else:
            discrepancy_note = (
                f"Le deck annonce {deck_value:,.0f} EUR ; notre estimation indépendante ci-dessus est en {structured['currency']} - "
                "à comparer de façon directionnelle plutôt qu'exacte, les devises étant différentes."
            )
    elif structured and not deck_value:
        discrepancy_note = "Le deck ne donne pas sa propre estimation de la taille de marché pour comparaison."
    trace.add("reality_check", {"deck_value_eur": deck_value, "note": discrepancy_note})

    if structured and deck_value and structured["currency"] == "EUR":
        sam_val = (structured.get("sam") or {}).get("estimate")
        if sam_val and deck_value > sam_val * 2:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="market",
                severity=RedFlagSeverity.major,
                explanation=f"La taille de marché du deck ({deck_value:,.0f} EUR) fait plus du double de notre estimation SAM indépendante ({sam_val:,.0f} EUR).",
                evidence_id=None,
                potential_impact="Si le marché adressable est plus petit qu'annoncé, les hypothèses de croissance et la valorisation pourraient devoir être revues.",
                resolving_information="Demander au management leur méthodologie exacte de dimensionnement du marché et leurs sources primaires.",
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

    headline = f"Recalcul analyste : {estimate.value_eur:,.0f} EUR ({methodology.replace('_', '-')})"
    if comparison:
        headline += f". Le deck annonce {deck_value:,.0f} EUR - {comparison['verdict']}"
        if comparison["ratio_platform_over_company"] is not None and comparison["ratio_platform_over_company"] < 0.5:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="market",
                severity=RedFlagSeverity.major,
                explanation=f"Le TAM indépendant confirmé par l'analyste ({estimate.value_eur:,.0f}) fait moins de la moitié de ce qu'annonce le deck ({deck_value:,.0f}).",
                evidence_id=calc_ev.id,
                potential_impact="Le marché pourrait être sensiblement plus petit que ce que suppose le dossier d'investissement.",
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
