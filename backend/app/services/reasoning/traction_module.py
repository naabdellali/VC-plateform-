"""
Traction module: SaaS-forensics (spec sections 11-12, 18, 46), directly
implementing the two checks the user asked for by name: MRR-quality
volatility detection, and CAC/LTV internal-consistency checking. Also
runs an external reference check - are the customer logos/case studies
the deck implies actually corroborated by anything public (reviews,
mentions), or do public traces look like pilots/POCs rather than paying
production customers.
"""
from __future__ import annotations

import re

from sqlalchemy.orm import Session

from app.models import (
    Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence, RedFlagSeverity,
)
from app.services.calc.saas_metrics import mrr_quality_check, cac_ltv_consistency_check, rule_of_40
from app.services.calc.parsing import parse_money
from app.services.evidence_store import add_evidence
from app.services.llm_client import get_llm_client
from app.services.search_client import get_search_client
from app.services.reasoning.base import ReasoningTrace, upsert_module_result
from app.services.reasoning.red_flags import add_red_flag

MODULE = "traction"

_PILOT_KEYWORDS = ["pilot", "poc", "proof of concept", "free trial", "trial period", "beta customer"]


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract ----------------------------------------------------
    traction_claims = [c for c in (deck.extracted_claims_json or []) if c.get("category") == "traction_metric"]
    deck_value = None
    evidence_ids = []
    for c in traction_claims:
        parsed = parse_money(c.get("value") or c.get("claim", ""))
        if parsed and deck_value is None:
            deck_value = parsed
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=c.get("claim", "Traction metric claim"), value=c.get("value"),
            origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
            confidence=Confidence.medium, source_name=f"Pitch deck ({deck.filename})",
            supporting_excerpt=c.get("claim"),
        )
        evidence_ids.append(ev.id)
    trace.add("extract", {"claims_found": len(traction_claims), "deck_value_eur": deck_value}, evidence_ids)

    # --- 2. identify_unknowns -------------------------------------------
    unknowns = [
        "Monthly MRR/ARR series not extractable from deck text (charts aren't parsed) - "
        "submit via POST /traction/mrr-series to run the volatility check.",
        "CAC/LTV consistency check requires explicit CAC, LTV, gross margin and ARPA - "
        "submit via POST /traction/cac-ltv-check.",
    ]
    trace.add("identify_unknowns", unknowns)

    # --- 3. research: external corroboration of customer references -----
    question = f"Are there public customer reviews, case studies, or mentions confirming {company.name} has paying production customers (not pilots/POCs)?"
    query_result = llm.generate_search_queries(question, {"company": company.name, "sector": company.sector})
    queries = (query_result.parsed or {}).get("queries", [question]) if query_result.parsed else [question]

    all_sources = []
    for q in queries[:2]:
        resp = search.search(q, max_results=4)
        for r in resp.results:
            all_sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
    trace.add("research", {"queries": queries, "sources_found": len(all_sources), "search_mode": search.mode})

    # --- 4. verify --------------------------------------------------------
    synth = llm.synthesize_research(question, all_sources)
    synth_payload = synth.parsed or {}
    synth_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="External corroboration of customer traction",
        value=synth_payload.get("answer", "Unable to independently verify."),
        origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
            synth_payload.get("confidence"), Confidence.unverified
        ),
        methodology="LLM synthesis over web-search results restricted to retrieved sources.",
    )
    trace.add("verify", synth_payload, [synth_ev.id])

    pilot_signal = any(
        kw in (s["content"] or "").lower() or kw in (s["title"] or "").lower()
        for s in all_sources for kw in _PILOT_KEYWORDS
    )
    if pilot_signal:
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="financial",
            severity=RedFlagSeverity.major,
            explanation="Public sources reference pilots/POCs/trials for customers the deck presents as production traction.",
            evidence_id=synth_ev.id,
            potential_impact="Reported traction may overstate the share of revenue that is truly recurring and committed.",
            resolving_information="Ask management to break down revenue by contract status (signed production vs. pilot/POC).",
        )
        trace.add("contradictions", ["Public sources suggest pilot/POC status for traction presented as production revenue."])

    status = ModuleStatus.needs_review if traction_claims else ModuleStatus.insufficient_evidence
    headline = (
        f"Traction : {deck_value:,.0f} EUR MRR/ARR déclaré (non vérifié)."
        if deck_value else "Traction : en attente de données."
    )
    upsert_module_result(
        db, company, MODULE, status=status, headline=headline,
        deck_value=str(deck_value) if deck_value else None, platform_value=None,
        discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
    )


def submit_mrr_series(db: Session, company: Company, monthly_values_eur: list[float]) -> dict:
    """Human-in-the-loop: analyst reads the MRR chart off the deck (or gets
    it from the data room) and submits the actual monthly series."""
    from app.models import ModuleResult

    report = mrr_quality_check(monthly_values_eur)
    calc_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="MRR quality / volatility check", value=report.as_evidence_payload(),
        value_type="json", origin=EvidenceOrigin.platform_calculation,
        source_tier=SourceTier.calculation, confidence=Confidence.high,
        methodology="Coefficient of variation + month-over-month decline ratio on analyst-submitted MRR series.",
    )
    severity = None
    if report.coefficient_of_variation > 0.15:
        severity = RedFlagSeverity.major
    if severity:
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="financial", severity=severity,
            explanation=report.flags[0], evidence_id=calc_ev.id,
            potential_impact="Reported MRR may include non-recurring services/project revenue, inflating perceived recurring traction.",
            resolving_information="Request a revenue breakdown by recurring vs. one-off/services line items.",
        )

    result = db.query(ModuleResult).filter(ModuleResult.company_id == company.id, ModuleResult.module == MODULE).one_or_none()
    trace = ReasoningTrace()
    if result and result.reasoning_json:
        trace.steps = result.reasoning_json.get("steps", [])
    trace.add("calculate", report.as_evidence_payload(), [calc_ev.id])

    # Transparent, single-glance trend signal for the tray tile - the full CV/volatility
    # detail still lives in discrepancy_explanation and the reasoning trace below it.
    first, last = monthly_values_eur[0], monthly_values_eur[-1]
    if last > first * 1.05:
        trend = "↑ Traction en hausse"
    elif last < first * 0.95:
        trend = "↓ Traction en baisse"
    else:
        trend = "→ Traction stable"
    headline = f"{trend} (CV={report.coefficient_of_variation:.2f})."

    upsert_module_result(
        db, company, MODULE, status=ModuleStatus.complete,
        headline=headline,
        deck_value=result.deck_value if result else None,
        platform_value=str(round(monthly_values_eur[-1], 2)),
        discrepancy_explanation=report.flags[0], trace=trace, llm_mode=get_llm_client().mode,
    )
    return report.as_evidence_payload()


def submit_cac_ltv_check(db: Session, company: Company, *, cac: float, reported_ltv: float, gross_margin: float, arpa_monthly: float) -> dict:
    result_payload = cac_ltv_consistency_check(cac=cac, reported_ltv=reported_ltv, gross_margin=gross_margin, arpa_monthly=arpa_monthly)
    calc_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="CAC/LTV internal consistency check", value=result_payload,
        value_type="json", origin=EvidenceOrigin.platform_calculation,
        source_tier=SourceTier.calculation, confidence=Confidence.high,
        methodology="Reverse-solve implied monthly churn required for reported LTV given ARPA and gross margin.",
    )
    if not result_payload["plausible"]:
        add_red_flag(
            db, company_id=company.id, module=MODULE, category="financial", severity=RedFlagSeverity.major,
            explanation=result_payload["explanation"], evidence_id=calc_ev.id,
            potential_impact="Reported LTV (and therefore LTV:CAC) may be materially overstated.",
            resolving_information="Ask for the actual churn cohort data underlying the reported LTV.",
        )
    return result_payload


def rule_of_40_check(db: Session, company: Company, *, growth_rate_pct: float, profit_margin_pct: float) -> dict:
    result = rule_of_40(growth_rate_pct, profit_margin_pct)
    add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Rule of 40 check", value=result, value_type="json",
        origin=EvidenceOrigin.platform_calculation, source_tier=SourceTier.calculation,
        confidence=Confidence.high, methodology="growth_rate_pct + profit_margin_pct >= 40",
    )
    return result
