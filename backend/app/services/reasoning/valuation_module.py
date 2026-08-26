"""
Valuation & Scenarios module (roadmap: "Valuation & Return/Exit
scenarios", first slice). Two things this module produces, both keyed off
whatever revenue figure the Traction module already found in the deck:

1. A comps-based implied valuation range: research a defensible
   revenue-multiple range for the company's sector/stage (grounded in
   cited sources, never invented), then apply it to the revenue figure -
   pure arithmetic (see calc/valuation.py).
2. Three revenue/valuation scenarios (Downside/Base/Upside) projected
   PROJECTION_YEARS out, using the stage-typical growth-rate benchmarks
   in rules/valuation_rules.py (explicitly labelled as a sector
   assumption, never as a prediction about this specific company) and
   the SAME comps multiple computed in step 1.

Deliberately NOT in this first slice (see rules/valuation_rules.py and
the product decision behind it): a deal-specific pre/post-money and
dilution calculation from the round's ask amount, and any cap-table
modeling. This module only reasons about the company's standalone
value, not about what a specific investor's stake in it would be worth.

Runs AFTER Traction in upload.py (same cross-module dependency pattern
competition_module uses for Technology's ModuleResult - see that
module's docstring) since it reads Traction's already-persisted
deck_value rather than re-parsing the deck itself. If Traction hasn't
run yet, or found no usable revenue figure, this module reports
insufficient_evidence rather than fabricating a base to multiply from.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import Company, Deck, ModuleResult, ModuleStatus, EvidenceOrigin, SourceTier, Confidence
from app.rules.valuation_rules import get_scenario_growth_rates, PROJECTION_YEARS
from app.services.calc.valuation import implied_valuation_range, project_scenario_value
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result

MODULE = "valuation"

_STAGE_LABEL_FR = {
    "pre_seed": "pre-seed",
    "seed": "seed",
    "series_a": "Series A",
    "series_b_plus": "Series B+",
    "unknown": "stade inconnu",
}

_SCENARIO_LABEL_FR = {"downside": "Downside", "base": "Base", "upside": "Upside"}


def _fmt_eur(n: float) -> str:
    if abs(n) >= 1e9:
        return f"{n / 1e9:.1f}Md€"
    if abs(n) >= 1e6:
        return f"{n / 1e6:.1f}M€"
    if abs(n) >= 1e3:
        return f"{n / 1e3:.0f}K€"
    return f"{n:,.0f}€"


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract: read Traction's already-persisted revenue read, don't
    #        re-parse the deck ourselves - same cross-module pattern
    #        competition_module uses for Technology's ModuleResult. ---
    traction_mr = db.query(ModuleResult).filter_by(company_id=company.id, module="traction").first()
    revenue = None
    if traction_mr and traction_mr.deck_value:
        try:
            revenue = float(traction_mr.deck_value)
        except (TypeError, ValueError):
            revenue = None
    trace.add("extract", {"revenue_source": "traction module deck_value (déclaré, non vérifié)", "revenue_eur": revenue})

    if revenue is None or revenue <= 0:
        trace.add("identify_unknowns", [
            "Aucun chiffre de traction (MRR/ARR) exploitable n'a été trouvé par le module Traction - "
            "impossible d'ancrer une valorisation ou des scénarios sans base de revenu.",
        ])
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Valorisation : en attente d'un chiffre de traction (MRR/ARR) exploitable.",
            deck_value=None, platform_value=None, discrepancy_explanation=None,
            trace=trace, llm_mode=llm.mode,
        )
        return

    # --- 2. identify_unknowns -------------------------------------------
    trace.add("identify_unknowns", [
        "Le chiffre de revenu utilisé ici est celui déclaré par l'entreprise dans le deck (module "
        "Traction), non vérifié indépendamment - toute valorisation en aval hérite de cette réserve.",
        "Le multiple de comparables est une fourchette sectorielle, pas une expertise spécifique à "
        "cette société.",
    ])

    # --- 3. research: comps multiples for this sector/stage --------------
    stage_value = company.stage.value if company.stage else "unknown"
    stage_label = _STAGE_LABEL_FR.get(stage_value, stage_value)
    context = {"sector": company.sector, "hq_country": company.hq_country, "stage": stage_value}

    if not company.sector:
        trace.add("research", {"queries": [], "sources_found": 0, "search_mode": search.mode,
                                "skipped_reason": "Secteur inconnu - impossible de cibler une recherche de comparables."})
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Valorisation : secteur de l'entreprise inconnu, impossible de rechercher des comparables.",
            deck_value=str(revenue), platform_value=None, discrepancy_explanation=None,
            trace=trace, llm_mode=llm.mode,
        )
        return

    comps_q = (
        f"What are typical revenue valuation multiples for recent funding rounds or M&A in the "
        f"{company.sector} sector, at {stage_label} stage, in {company.hq_country or 'Europe'}?"
    )
    query_result = llm.generate_search_queries(comps_q, context)
    queries = (query_result.parsed or {}).get("queries", [comps_q]) if query_result.parsed else [comps_q]
    queries = list(queries[:2])

    sources = []
    for q in queries:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
    trace.add("research", {"queries": queries, "sources_found": len(sources), "search_mode": search.mode})

    # --- 4. calculate: comps multiple (LLM-synthesized, source-grounded) ---
    multiples_result = llm.estimate_valuation_multiples(context, sources)
    multiples_payload = multiples_result.parsed or {"insufficient": True, "reason": "Could not parse the model's output."}
    if not sources:
        multiples_payload = {"insufficient": True, "reason": "No web-search results were available to ground a multiple range."}

    if multiples_payload.get("insufficient"):
        trace.add("calculate", {"insufficient": True, "reason": multiples_payload.get("reason")})
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline=(
                f"Valorisation : traction de {_fmt_eur(revenue)} déclarée, mais aucun comparable "
                f"sourcé trouvé pour établir un multiple ({multiples_payload.get('reason', 'sources insuffisantes')})."
            ),
            deck_value=str(revenue), platform_value=None, discrepancy_explanation=None,
            trace=trace, llm_mode=llm.mode,
        )
        return

    low_multiple = float(multiples_payload.get("low_multiple") or 0)
    high_multiple = float(multiples_payload.get("high_multiple") or 0)
    multiple_basis = multiples_payload.get("multiple_basis") or "ARR"

    footnotes = []
    for fn in multiples_payload.get("footnotes", []) or []:
        idx = fn.get("source_index")
        src = sources[idx] if isinstance(idx, int) and 0 <= idx < len(sources) else None
        footnotes.append({
            "n": fn.get("n"), "detail": fn.get("detail"),
            "source_url": src["url"] if src else None, "source_name": src["title"] if src else None,
        })

    multiple_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim=f"Fourchette de multiple de valorisation comparable ({multiple_basis})",
        value=json.dumps({"low": low_multiple, "high": high_multiple, "basis": multiple_basis}),
        value_type="multiple_range_json",
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence=Confidence.medium if llm.mode == "live" else Confidence.unverified,
        methodology="Synthèse LLM à partir de sources de recherche web restreintes aux résultats obtenus (rounds/M&A comparables).",
        supporting_excerpt=multiples_payload.get("reasoning"),
    )
    trace.add("calculate", {"multiples": multiples_payload, "footnotes": footnotes}, [multiple_ev.id])

    # --- 5. implied valuation range (deterministic) ----------------------
    implied = implied_valuation_range(revenue, low_multiple, high_multiple)
    implied_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Valorisation implicite (comparables x traction déclarée)",
        value=json.dumps(implied), value_type="valuation_range_json",
        origin=EvidenceOrigin.platform_calculation, source_tier=SourceTier.calculation,
        confidence=Confidence.medium if llm.mode == "live" else Confidence.unverified,
        methodology=(
            f"{_fmt_eur(revenue)} ({multiple_basis} déclaré, non vérifié) x multiple comparable "
            f"{low_multiple:g}-{high_multiple:g}x."
        ),
    )
    trace.add("calculate", {"implied_valuation": implied}, [implied_ev.id])

    # --- 6. scenarios: Downside/Base/Upside, same comps multiple, ---------
    #        stage-typical growth-rate benchmark (explicitly labelled). ---
    growth_rates = get_scenario_growth_rates(company.stage)
    mid_multiple = (low_multiple + high_multiple) / 2
    scenarios = {}
    scenario_evidence_ids = []
    for key in ("downside", "base", "upside"):
        rate = growth_rates[key]
        projection = project_scenario_value(revenue, rate, PROJECTION_YEARS, mid_multiple)
        scenarios[key] = {**projection, "growth_rate": rate}
        sc_ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=f"Scénario {_SCENARIO_LABEL_FR[key]} à {PROJECTION_YEARS} ans",
            value=json.dumps(scenarios[key]), value_type="scenario_json",
            origin=EvidenceOrigin.platform_calculation, source_tier=SourceTier.calculation,
            confidence=Confidence.unverified,
            methodology=(
                f"{_fmt_eur(revenue)} composé à +{rate * 100:.0f}%/an sur {PROJECTION_YEARS} ans "
                f"(hypothèse sectorielle {stage_label}, pas une prévision propre à cette société) "
                f"x multiple comparable médian {mid_multiple:.1f}x."
            ),
        )
        scenario_evidence_ids.append(sc_ev.id)
    trace.add("calculate", {"scenarios": scenarios, "growth_rate_source": f"benchmark sectoriel {stage_label}"}, scenario_evidence_ids)

    headline = (
        f"Comparables : {low_multiple:g}-{high_multiple:g}x {multiple_basis}. "
        f"Valorisation implicite : {_fmt_eur(implied['low'])}-{_fmt_eur(implied['high'])}. "
        f"Scénario à {PROJECTION_YEARS} ans - Downside : {_fmt_eur(scenarios['downside']['projected_value'])} / "
        f"Base : {_fmt_eur(scenarios['base']['projected_value'])} / "
        f"Upside : {_fmt_eur(scenarios['upside']['projected_value'])}."
    )
    platform_value = json.dumps({
        "revenue_eur": revenue,
        "multiple_basis": multiple_basis,
        "multiple_low": low_multiple,
        "multiple_high": high_multiple,
        "implied_valuation": implied,
        "scenarios": scenarios,
        "projection_years": PROJECTION_YEARS,
        "footnotes": footnotes,
    })
    upsert_module_result(
        db, company, MODULE, status=ModuleStatus.needs_review, headline=headline,
        deck_value=str(revenue), platform_value=platform_value, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
