"""
Founders & background-check module (spec section 17).

Pappers.fr is the Tier-1 primary source for French legal/company data
(officers, incorporation date, insolvency proceedings). Claimed
professional background (e.g. "ex-Google, 10 years experience") is
cross-checked against open web research and explicitly classified as
Verified / Reported-but-unverified / Contradicted - never silently
upgraded to "verified" just because the deck says so.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import (
    Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence, RedFlagSeverity,
)
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.pappers_client import get_pappers_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result
from app.services.reasoning.red_flags import add_red_flag

MODULE = "founders"


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    pappers = get_pappers_client()
    trace = ReasoningTrace()

    # --- 1. extract ------------------------------------------------------
    team_claims = [c for c in (deck.extracted_claims_json or []) if c.get("category") == "team_background"]
    claim_evidence_ids = []
    for c in team_claims:
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=c.get("claim", "Founder background claim"), value=c.get("value"),
            origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
            confidence=Confidence.medium, source_name=f"Pitch deck ({deck.filename})",
            supporting_excerpt=c.get("claim"),
        )
        claim_evidence_ids.append(ev.id)
    trace.add("extract", {"claims_found": len(team_claims)}, claim_evidence_ids)

    # --- 2. Pappers.fr legal/registry check (Tier 1 for French entities) --
    record = pappers.search_company(company.legal_name or company.name)
    pappers_evidence_ids = []
    if record.mode == "mock":
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim="Legal/registry background check", value=None,
            origin=EvidenceOrigin.unknown if False else EvidenceOrigin.external_source,
            source_tier=SourceTier.not_applicable, confidence=Confidence.unverified,
            source_name="Pappers.fr", methodology="Unable to independently verify - PAPPERS_API_KEY not configured.",
        )
        pappers_evidence_ids.append(ev.id)
    elif not record.found:
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim="Legal/registry background check", value="Not found in Pappers.fr registry",
            origin=EvidenceOrigin.external_source, source_tier=SourceTier.tier1_primary,
            confidence=Confidence.medium, source_name="Pappers.fr",
            methodology="No matching French legal entity found - company may be foreign, pre-incorporation, or under a different legal name.",
        )
        pappers_evidence_ids.append(ev.id)
    else:
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=f"Legal entity: {record.denomination} (SIREN {record.siren})",
            value=record.date_creation, origin=EvidenceOrigin.external_source,
            source_tier=SourceTier.tier1_primary, confidence=Confidence.high,
            source_name="Pappers.fr", source_url=f"https://www.pappers.fr/entreprise/{record.siren}",
            methodology="French company registry (RNE/INPI data via Pappers.fr API).",
        )
        pappers_evidence_ids.append(ev.id)

        for d in record.dirigeants:
            dev = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim=f"Officer of record: {d.prenom or ''} {d.nom} ({d.qualite or 'role unspecified'})",
                value=f"{len(d.autres_mandats)} other mandate(s) on record",
                origin=EvidenceOrigin.external_source, source_tier=SourceTier.tier1_primary,
                confidence=Confidence.high, source_name="Pappers.fr",
                source_url=f"https://www.pappers.fr/entreprise/{record.siren}",
            )
            pappers_evidence_ids.append(dev.id)

        if record.procedures_collectives:
            fev = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim="Insolvency/collective proceedings on record", value=str(len(record.procedures_collectives)),
                origin=EvidenceOrigin.external_source, source_tier=SourceTier.tier1_primary,
                confidence=Confidence.high, source_name="Pappers.fr",
            )
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="team",
                severity=RedFlagSeverity.critical,
                explanation=f"{len(record.procedures_collectives)} insolvency/collective proceeding(s) found on the legal entity's record.",
                evidence_id=fev.id,
                potential_impact="May indicate prior financial distress relevant to founder track record or the entity itself.",
                resolving_information="Review the specific proceedings and ask management directly about context and resolution.",
            )
    trace.add("research", {"pappers_mode": record.mode, "found": record.found}, pappers_evidence_ids)

    # --- 3. Web verification of claimed background ------------------------
    verification_evidence_ids = []
    classifications = []
    for c in team_claims[:5]:  # cap to keep the automatic pass bounded
        question = f"Verify this claim about a startup founder: '{c.get('claim')}'. Is there public evidence supporting or contradicting it?"
        q_result = llm.generate_search_queries(question, {"company": company.name})
        queries = (q_result.parsed or {}).get("queries", [question]) if q_result.parsed else [question]
        sources = []
        for q in queries[:2]:
            resp = search.search(q, max_results=3)
            for r in resp.results:
                sources.append({"title": r.title, "url": r.url, "content": r.content[:1200], "published_date": r.published_date})

        synth = llm.synthesize_research(question, sources)
        payload = synth.parsed or {}
        confidence_str = payload.get("confidence", "unverified")
        classification = "reported_unverified"
        if confidence_str == "high":
            classification = "verified"
        elif payload.get("conflicting"):
            classification = "contradicted"

        vev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=f"Verification of: {c.get('claim')}", value=payload.get("answer"),
            origin=EvidenceOrigin.platform_inference,
            source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
            confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(confidence_str, Confidence.unverified),
            methodology="LLM synthesis over web-search results restricted to retrieved sources.",
        )
        verification_evidence_ids.append(vev.id)
        classifications.append({"claim": c.get("claim"), "classification": classification, "evidence_id": vev.id})

        if classification == "contradicted":
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="team",
                severity=RedFlagSeverity.major,
                explanation=f"Public sources appear to contradict the claim: '{c.get('claim')}'.",
                evidence_id=vev.id,
                potential_impact="Founder credibility / founder-market fit claims may be overstated.",
                resolving_information="Ask the founder directly to clarify and provide documentation.",
            )
    trace.add("verify", classifications, verification_evidence_ids)

    status = ModuleStatus.needs_review if team_claims or record.found else ModuleStatus.insufficient_evidence
    n_contradicted = sum(1 for c in classifications if c["classification"] == "contradicted")
    headline = f"{len(record.dirigeants) if record.found else 0} officer(s) on record via Pappers.fr. {n_contradicted} claim(s) contradicted by public sources." if record.found or classifications else "Insufficient data to run founder verification."

    upsert_module_result(
        db, company, MODULE, status=status, headline=headline,
        deck_value=None, platform_value=None, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
