"""
Market Dynamics module: is this sector growing, stable, or declining, and is
there active consolidation / M&A activity - a standalone question distinct
from TAM/SAM/SOM (size, market_module) and from the Competitive Landscape
(who's in it, competition_module). Previously this lived as one buried
"consolidation" paragraph inside the Competition module's matrix payload;
split out on its own per analyst feedback, with its own tray tile, memo
section, and a small visual (trend badge + keyword tags), grounded only in
sourced web research (plus the deck's own market-context text for
company-claim-origin context) - never invented.
"""
from __future__ import annotations

import json

from sqlalchemy.orm import Session

from app.models import Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence, RedFlagSeverity
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result
from app.services.reasoning.confidence import cap_confidence_by_source_count
from app.services.reasoning.red_flags import add_red_flag

MODULE = "market_dynamics"

TREND_LABEL_FR = {"growing": "Marché en croissance", "stable": "Marché stable", "declining": "Marché en déclin"}


def run_auto(db: Session, company: Company, deck: Deck | None = None) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    if not company.sector:
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Dynamique de marché non évaluée - le secteur n'est pas encore connu.",
            deck_value=None, platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        return

    dynamics_q = (
        f"What is the growth trend of the {company.sector} market (growing, stable, or declining), and is there "
        f"active consolidation or M&A activity among players in this sector?"
    )
    q = llm.generate_search_queries(dynamics_q, {"sector": company.sector, "hq_country": company.hq_country})
    queries = (q.parsed or {}).get("queries", [dynamics_q]) if q.parsed else [dynamics_q]

    sources = []
    for query in queries[:3]:
        resp = search.search(query, max_results=4)
        for r in resp.results:
            sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
    trace.add("research", {"queries": queries, "sources_found": len(sources), "search_mode": search.mode}, [])

    if not sources:
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Aucune source trouvée sur la dynamique de ce marché.",
            deck_value=None, platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        return

    result = llm.identify_market_dynamics(company.sector, company.hq_country, sources, deck_text=deck.raw_text if deck else None)
    payload = result.parsed or {"insufficient": True}

    if payload.get("insufficient") or not (payload.get("trend") or payload.get("consolidation")):
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim="Recherche indépendante sur la dynamique du marché", value="Sources trouvées mais non concluantes.",
            origin=EvidenceOrigin.platform_inference,
            source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
            confidence=Confidence.unverified,
            methodology="LLM synthesis over web-search results restricted to retrieved sources.",
        )
        trace.add("verify", payload, [ev.id])
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Sources trouvées, mais rien de concluant sur la croissance ou la consolidation du secteur.",
            deck_value=None, platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        return

    footnotes = []
    for fn in payload.get("footnotes", []) or []:
        idx = fn.get("source_index")
        src = sources[idx] if isinstance(idx, int) and 0 <= idx < len(sources) else None
        footnotes.append({
            "n": fn.get("n"), "detail": fn.get("detail"),
            "source_url": src["url"] if src else None, "source_name": src["title"] if src else None,
        })

    trend = payload.get("trend") if payload.get("trend") in TREND_LABEL_FR else None
    dynamics_struct = {
        "trend": trend,
        "trend_label": TREND_LABEL_FR.get(trend),
        "trend_reasoning": payload.get("trend_reasoning"),
        "consolidation": payload.get("consolidation"),
        "key_drivers": [d for d in (payload.get("key_drivers") or []) if d],
        "footnotes": footnotes,
    }

    ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Dynamique de marché indépendante (croissance, consolidation)",
        value=json.dumps(dynamics_struct), value_type="market_dynamics_json",
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence=cap_confidence_by_source_count(Confidence.medium, len(sources)),
        methodology="LLM synthesis over web-search results restricted to retrieved sources; a claim is only kept if a source supports it.",
    )
    trace.add("calculate", dynamics_struct, [ev.id])

    if trend == "declining":
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="market_dynamics", severity=RedFlagSeverity.watch,
            explanation="Le marché semble en déclin selon la recherche indépendante : " + (dynamics_struct["trend_reasoning"] or ""),
            evidence_id=ev.id,
            potential_impact="Un marché en déclin réduit la taille de l'opportunité à long terme, indépendamment de l'exécution de l'équipe.",
            resolving_information="Demander à l'équipe comment elle explique la dynamique du marché et pourquoi elle reste pertinente si le marché décline.",
        )

    headline_parts = []
    if dynamics_struct["trend_label"]:
        headline_parts.append(dynamics_struct["trend_label"])
    if dynamics_struct["consolidation"]:
        headline_parts.append("consolidation identifiée" if "aucun" not in dynamics_struct["consolidation"].lower() else "pas de consolidation notable")
    headline = " — ".join(headline_parts) + "." if headline_parts else "Dynamique de marché : éléments limités."

    upsert_module_result(
        db, company, MODULE, status=ModuleStatus.needs_review, headline=headline,
        deck_value=None, platform_value=json.dumps(dynamics_struct), discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
