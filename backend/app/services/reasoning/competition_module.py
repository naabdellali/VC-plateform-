"""
Competition module: independent competitive landscape + "collision"
simulation (spec sections 8-9) - directly implements the user's example:
"a large incumbent already tried/abandoned/blocks this, and the deck
doesn't mention it."
"""
from __future__ import annotations

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
    landscape_q = f"Who are the direct and indirect competitors of a {company.business_model.value if company.business_model else ''} company in {company.sector or 'this sector'}, including incumbents and adjacent solutions?"
    q1 = llm.generate_search_queries(landscape_q, {"sector": company.sector, "business_model": company.business_model.value if company.business_model else None})
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
            explanation="Independent research suggests an incumbent has already engaged with this space: " + collision_payload["answer"][:300],
            evidence_id=collision_ev.id,
            potential_impact="Question whether the startup's moat is defensible if/when a better-capitalized player re-enters.",
            resolving_information="Ask management directly why the incumbent's prior attempt (if confirmed) does not apply to this startup.",
        )

    # --- 4. contradiction: deck's competitor list vs independent findings -
    if landscape_payload.get("answer") and deck_named:
        contradiction_note = (
            f"Deck names {len(deck_named)} competitor(s): {', '.join(list(deck_named)[:5])}. "
            "Independent research may surface additional players not mentioned in the deck - review the full research answer in the evidence trail."
        )
        trace.add("contradictions", [contradiction_note])
    elif landscape_payload.get("answer") and not deck_named:
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="competition",
            severity=RedFlagSeverity.watch,
            explanation="Deck does not name any competitors, but independent research found relevant players in the space.",
            evidence_id=landscape_ev.id,
            potential_impact="Omitting competitors may indicate an incomplete or overly favorable framing of the competitive landscape.",
        )

    status = ModuleStatus.needs_review if (deck_named or landscape_payload.get("answer")) else ModuleStatus.insufficient_evidence
    headline = f"Deck names {len(deck_named)} competitor(s). Independent research {'found additional signal' if landscape_payload.get('answer') else 'inconclusive'} - see evidence trail."

    upsert_module_result(
        db, company, MODULE, status=status, headline=headline,
        deck_value=", ".join(list(deck_named)[:5]) if deck_named else None,
        platform_value=None, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
