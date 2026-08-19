"""
Competition module: independent competitive landscape + "collision"
simulation (spec sections 8-9) - directly implements the user's example:
"a large incumbent already tried/abandoned/blocks this, and the deck
doesn't mention it."
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import (
    Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence, RedFlagSeverity,
)
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result
from app.services.reasoning.red_flags import add_red_flag

MODULE = "competition"
MOAT_MODULE = "moat"

OCEAN_LABEL = {
    "blue_ocean": "Blue Ocean",
    "red_ocean": "Red Ocean",
    "blood_red_ocean": "Blood Red Ocean",
}


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract: competitors the deck itself names -------------------
    deck_competitor_claims = [c for c in (deck.extracted_claims_json or []) if c.get("category") == "competitors"]
    deck_named = {c.get("value") or c.get("claim") for c in deck_competitor_claims}
    claim_evidence_ids = []
    for c in deck_competitor_claims:
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=c.get("claim", "Competitor mentioned in deck"), value=c.get("value"),
            origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
            confidence=Confidence.medium, source_name=f"Pitch deck ({deck.filename})",
        )
        claim_evidence_ids.append(ev.id)
    trace.add("extract", {"deck_named_competitors": list(deck_named)}, claim_evidence_ids)

    # --- 2. research: independent competitor discovery --------------------
    # Sector-driven, not business_model-driven - see market_module for why business_model
    # (a fixed workspace-form value, unrelated to the actual product) must not leak into
    # research queries and bias them toward the wrong category.
    if not company.sector:
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Impossible de cartographier la concurrence pour l'instant - le secteur n'est pas connu.",
            deck_value=", ".join(list(deck_named)[:5]) if deck_named else None,
            platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        upsert_module_result(
            db, company, MOAT_MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Défendabilité non évaluée - secteur inconnu.",
            deck_value=None, platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        return
    landscape_q = f"Who are the direct and indirect competitors in {company.sector}, including incumbents and adjacent solutions, by function and by region (France/Europe vs United States)?"
    q1 = llm.generate_search_queries(landscape_q, {"sector": company.sector, "hq_country": company.hq_country})
    queries = (q1.parsed or {}).get("queries", [landscape_q]) if q1.parsed else [landscape_q]

    landscape_sources = []
    for q in queries[:3]:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            landscape_sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})

    landscape_synth = llm.synthesize_research(landscape_q, landscape_sources)
    landscape_payload = landscape_synth.parsed or {}
    landscape_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Independently researched competitive landscape",
        value=landscape_payload.get("answer", "Unable to independently verify."),
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
            landscape_payload.get("confidence"), Confidence.unverified
        ),
        methodology="LLM synthesis over web-search results restricted to retrieved sources.",
    )
    trace.add("research", {"queries": queries, "sources_found": len(landscape_sources), "search_mode": search.mode}, [landscape_ev.id])

    # --- 2b. structured competitor list, for a real comparison grid in the UI ---
    competitor_ids = []
    competitors_struct = []
    if landscape_sources:
        comp_result = llm.identify_competitors(landscape_q, landscape_sources)
        comp_payload = comp_result.parsed or {"competitors": [], "confidence": "unverified"}
        for c in comp_payload.get("competitors", [])[:8]:
            idx = c.get("source_index")
            src = landscape_sources[idx] if isinstance(idx, int) and 0 <= idx < len(landscape_sources) else None
            name = (c.get("name") or "").strip()
            if not name:
                continue
            competitors_struct.append({
                "name": name,
                "description": c.get("description") or "",
                "domain": c.get("domain"),
                "competitor_type": c.get("competitor_type") if c.get("competitor_type") in ("direct", "indirect") else None,
                "country": c.get("country"),
                "size": c.get("size"),
                "source_url": src["url"] if src else None,
                "source_name": src["title"] if src else None,
                "in_deck": any(name.lower() in (dn or "").lower() or (dn or "").lower() in name.lower() for dn in deck_named),
            })
        if competitors_struct:
            comp_conf = {"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
                comp_payload.get("confidence"), Confidence.unverified
            )
            comp_ev = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim="Independently identified named competitors",
                value=json.dumps(competitors_struct), value_type="competitor_list_json",
                origin=EvidenceOrigin.external_source, source_tier=SourceTier.tier2_secondary,
                confidence=comp_conf,
                methodology="LLM-extracted from web-search results; a competitor is only listed if a source explicitly names it.",
            )
            competitor_ids.append(comp_ev.id)
    trace.add("verify", {"structured_competitors_found": len(competitors_struct)}, competitor_ids)

    # --- 2c. function x geography landscape matrix - the analyst-memo format ------------------
    # Also carries the "ocean" snapshot (blue/red/blood-red - competitive intensity at a glance)
    # and the "moat" grade (No/Narrow/Wide) - split out into their own tray tile + memo section
    # below, since they're a distinct judgment from the raw landscape mapping.
    landscape_struct = None
    moat_struct = None
    platform_value = None
    moat_platform_value = None
    if landscape_sources:
        matrix_result = llm.build_competitive_landscape({"sector": company.sector, "hq_country": company.hq_country}, landscape_sources)
        matrix_payload = matrix_result.parsed or {"insufficient": True}
        if not matrix_payload.get("insufficient"):
            footnotes = []
            for fn in matrix_payload.get("footnotes", []) or []:
                idx = fn.get("source_index")
                src = landscape_sources[idx] if isinstance(idx, int) and 0 <= idx < len(landscape_sources) else None
                footnotes.append({
                    "n": fn.get("n"), "detail": fn.get("detail"),
                    "source_url": src["url"] if src else None, "source_name": src["title"] if src else None,
                })
            comparable = matrix_payload.get("closest_comparable") or {}
            comp_idx = comparable.get("source_index")
            comp_src = landscape_sources[comp_idx] if isinstance(comp_idx, int) and 0 <= comp_idx < len(landscape_sources) else None
            ocean_payload = matrix_payload.get("ocean") or {}
            ocean_type = ocean_payload.get("type") if ocean_payload.get("type") in OCEAN_LABEL else None
            ocean_struct = (
                {"type": ocean_type, "label": OCEAN_LABEL[ocean_type], "reasoning": ocean_payload.get("reasoning")}
                if ocean_type else None
            )
            landscape_struct = {
                "market_intro": matrix_payload.get("market_intro"),
                "functions": matrix_payload.get("functions") or [],
                "geographies": matrix_payload.get("geographies") or ["France", "Europe", "États-Unis"],
                "matrix": matrix_payload.get("matrix") or [],
                "competitors": competitors_struct,
                "closest_comparable": {
                    "name": comparable.get("name"), "description": comparable.get("description"),
                    "source_url": comp_src["url"] if comp_src else None, "source_name": comp_src["title"] if comp_src else None,
                } if comparable.get("name") else None,
                "differentiator": matrix_payload.get("differentiator"),
                "risk": matrix_payload.get("risk"),
                "ocean": ocean_struct,
                "consolidation": matrix_payload.get("consolidation"),
                "footnotes": footnotes,
            }
            landscape_ev2 = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim="Independent competitive landscape matrix (function x geography)",
                value=json.dumps(landscape_struct), value_type="competitive_landscape_json",
                origin=EvidenceOrigin.platform_inference,
                source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
                confidence=Confidence.medium,
                methodology="LLM-mapped value-chain function x geography grid; a player is only placed in a cell if a source names them there.",
            )
            platform_value = json.dumps(landscape_struct)
            trace.add("calculate", landscape_struct, [landscape_ev2.id])

            moat_payload = matrix_payload.get("moat") or {}
            if moat_payload.get("grade"):
                moat_struct = {
                    "grade": moat_payload.get("grade"),
                    "strengths": moat_payload.get("strengths") or [],
                    "gaps": moat_payload.get("gaps") or [],
                    "what_would_widen_it": moat_payload.get("what_would_widen_it") or [],
                    "footnotes": footnotes,
                }
                moat_ev = add_evidence(
                    db, company_id=company.id, module=MOAT_MODULE,
                    claim="Independent moat / defensibility grade",
                    value=json.dumps(moat_struct), value_type="moat_json",
                    origin=EvidenceOrigin.platform_inference,
                    source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
                    confidence=Confidence.medium,
                    methodology="LLM-graded on the standard No Moat / Narrow Moat / Wide Moat convention, from the same sourced competitive research.",
                )
                moat_platform_value = json.dumps(moat_struct)
                trace.add("calculate", moat_struct, [moat_ev.id])

    # --- 3. collision simulation: incumbent threat (spec section 9) -------
    collision_q = f"Has any large, well-capitalized incumbent already launched, tested, or explicitly abandoned a product similar to a {company.sector or ''} startup's offering? Why did they stop, if they did?"
    q2 = llm.generate_search_queries(collision_q, {"sector": company.sector})
    collision_queries = (q2.parsed or {}).get("queries", [collision_q]) if q2.parsed else [collision_q]
    collision_sources = []
    for q in collision_queries[:2]:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            collision_sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})

    collision_synth = llm.synthesize_research(collision_q, collision_sources)
    collision_payload = collision_synth.parsed or {}
    collision_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Incumbent collision / abandonment check", value=collision_payload.get("answer"),
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
            collision_payload.get("confidence"), Confidence.unverified
        ),
        methodology="LLM synthesis over web-search results restricted to retrieved sources.",
    )
    trace.add("verify", collision_payload, [collision_ev.id])

    collision_signal = collision_payload.get("confidence") in ("high", "medium") and collision_payload.get("answer")
    if collision_signal and "unable to independently verify" not in (collision_payload.get("answer") or "").lower():
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="competition",
            severity=RedFlagSeverity.major,
            explanation="Un acteur déjà bien financé semble s'être positionné sur ce marché : " + collision_payload["answer"][:300],
            evidence_id=collision_ev.id,
            potential_impact="Remet en question la défendabilité du moat si un acteur mieux capitalisé revient sur ce marché.",
            resolving_information="Demander à l'équipe pourquoi cette tentative antérieure (si confirmée) ne s'applique pas à cette startup.",
        )

    # --- 4. contradiction: deck's competitor list vs independent findings -
    if landscape_payload.get("answer") and deck_named:
        contradiction_note = (
            f"Le deck cite {len(deck_named)} concurrent(s) : {', '.join(list(deck_named)[:5])}. "
            "La recherche indépendante peut faire apparaître d'autres acteurs non mentionnés dans le deck - voir le détail dans les preuves."
        )
        trace.add("contradictions", [contradiction_note])
    elif landscape_payload.get("answer") and not deck_named:
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="competition",
            severity=RedFlagSeverity.watch,
            explanation="Le deck ne cite aucun concurrent, alors que la recherche indépendante en a trouvé sur ce marché.",
            evidence_id=landscape_ev.id,
            potential_impact="Omettre les concurrents peut indiquer une présentation incomplète ou trop favorable du paysage concurrentiel.",
        )

    status = ModuleStatus.needs_review if (landscape_struct or competitors_struct or deck_named) else ModuleStatus.insufficient_evidence
    not_in_deck = sum(1 for c in competitors_struct if not c["in_deck"])
    if landscape_struct and landscape_struct.get("ocean"):
        headline = f"{landscape_struct['ocean']['label']}"
        if landscape_struct.get("closest_comparable"):
            headline += f" — comparable le plus proche : {landscape_struct['closest_comparable']['name']}."
        elif not_in_deck:
            headline += f" — {not_in_deck} acteur(s) non mentionné(s) dans le deck."
        else:
            headline += "."
    elif landscape_struct and landscape_struct.get("closest_comparable"):
        headline = f"Comparable le plus proche : {landscape_struct['closest_comparable']['name']}."
        if not_in_deck:
            headline += f" {not_in_deck} acteur(s) non mentionné(s) dans le deck."
    elif competitors_struct:
        headline = f"{len(competitors_struct)} concurrent(s) identifié(s) indépendamment"
        headline += f", {not_in_deck} absent(s) du deck." if not_in_deck else "."
    elif deck_named:
        headline = f"Le deck cite {len(deck_named)} concurrent(s) ; la recherche indépendante n'a rien confirmé de plus."
    else:
        headline = "Aucun concurrent cité dans le deck, et la recherche indépendante n'a rien trouvé de concluant."

    upsert_module_result(
        db, company, MODULE, status=status, headline=headline,
        deck_value=", ".join(list(deck_named)[:5]) if deck_named else None,
        platform_value=platform_value, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )

    moat_status = ModuleStatus.needs_review if moat_struct else ModuleStatus.insufficient_evidence
    moat_headline = moat_struct["grade"] if moat_struct else "Pas assez de sources pour évaluer la défendabilité (moat)."
    upsert_module_result(
        db, company, MOAT_MODULE, status=moat_status, headline=moat_headline,
        deck_value=None, platform_value=moat_platform_value, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
