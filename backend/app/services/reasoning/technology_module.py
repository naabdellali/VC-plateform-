"""
Technology module (VC Expert Questioning Framework, Technology dimension -
sections 2.1/2.2/2.6). Pilot for two shared primitives the framework calls
for explicitly: the trigger/signal engine (triggers.py) and the
InvestmentHypothesis pattern (a claim decomposed into testable
sub-conditions, reusing llm_client.decompose_assumptions).

Scoped for this first pass to what the framework's own worked example
covers: identify the company's technology architecture and third-party
dependencies from the deck (company-claim origin, not independently
verified), then let the trigger registry decide what that implies for
Moat/Competition and what to actually go research - rather than
hardcoding that reasoning inline here. Product/Timing/Geography/Macro
follow the same shape once this is validated.
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
from app.services.reasoning.triggers import Signal, evaluate

MODULE = "technology"

HYPOTHESIS_CLAIM = (
    "La différenciation technologique de l'entreprise constitue un avantage défendable, "
    "difficilement réplicable par les concurrents ou par le fournisseur tiers lui-même."
)


def run_auto(db: Session, company: Company, deck: Deck) -> None:
    llm = get_llm_client()
    search = get_search_client()
    trace = ReasoningTrace()

    # --- 1. extract: architecture + third-party dependencies, from the deck only ---
    tech_result = llm.identify_tech_dependencies(deck.raw_text or "")
    tech_payload = tech_result.parsed or {"dependencies": [], "proprietary": []}
    dependencies = [d for d in (tech_payload.get("dependencies") or []) if d.get("name")]
    proprietary = [p for p in (tech_payload.get("proprietary") or []) if p]

    dep_evidence_ids = []
    for d in dependencies:
        ev = add_evidence(
            db, company_id=company.id, module=MODULE,
            claim=f"Technology dependency: {d.get('name')}", value=d.get("role"),
            origin=EvidenceOrigin.company_claim, source_tier=SourceTier.deck,
            confidence=Confidence.medium, source_name=f"Pitch deck ({deck.filename})",
            supporting_excerpt=d.get("evidence_text"),
        )
        dep_evidence_ids.append(ev.id)
    trace.add("extract", {"dependencies": dependencies, "proprietary": proprietary}, dep_evidence_ids)

    if not dependencies and not proprietary:
        upsert_module_result(
            db, company, MODULE, status=ModuleStatus.insufficient_evidence,
            headline="Technologie : architecture non identifiable depuis le deck.",
            deck_value=None, platform_value=None, discrepancy_explanation=None, trace=trace, llm_mode=llm.mode,
        )
        return

    # --- 2. trigger engine: what does each critical dependency imply elsewhere? ---
    signals = [
        Signal(name="third_party_tech_dependency", value=True, detail=d["name"], source_module=MODULE)
        for d in dependencies if d.get("critical")
    ]
    activations = evaluate(signals)
    trace.add("cross_module_signals", activations)

    # --- 3. research: one grounded, sourced question per activation (bounded - cost control) ---
    research_findings = []
    founder_questions: list[str] = []
    research_ev_ids = []
    for act in activations:
        founder_questions.extend(act["founder_questions"])
        for q in act["research_questions"][:1]:
            sources = []
            for r in search.search(q, max_results=4).results:
                sources.append({"title": r.title, "url": r.url, "content": r.content[:1500], "published_date": r.published_date})
            synth = llm.synthesize_research(q, sources)
            payload = synth.parsed or {}
            ev = add_evidence(
                db, company_id=company.id, module=MODULE,
                claim=q, value=payload.get("answer", "Unable to independently verify."),
                origin=EvidenceOrigin.platform_inference,
                source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
                confidence={"high": Confidence.high, "medium": Confidence.medium, "low": Confidence.low}.get(
                    payload.get("confidence"), Confidence.unverified
                ),
                methodology="LLM synthesis over web-search results restricted to retrieved sources - triggered by a detected third-party dependency, not run generically.",
            )
            research_ev_ids.append(ev.id)
            research_findings.append({"question": q, "answer": payload.get("answer"), "dependency": act["detail"]})
    trace.add("research", research_findings, research_ev_ids)

    if founder_questions:
        trace.add("identify_unknowns", founder_questions)

    # --- 4. cross-module red flags: surfaced in Moat/Competition's territory without silently
    #        rewriting their own independently-computed conclusion ---
    for act in activations:
        if "moat" in act["activates"]:
            add_red_flag(
                db, company_id=company.id, module=MODULE, category="moat", severity=RedFlagSeverity.watch,
                explanation=f"Dépendance technologique tierce détectée : {act['detail']}. {act['rationale']}",
                evidence_id=None,
                potential_impact="Peut affaiblir la défendabilité technologique et exposer la marge brute au pricing du fournisseur.",
                resolving_information="; ".join(act["founder_questions"]),
            )

    # --- 5. InvestmentHypothesis: is the tech differentiation actually defensible? ---
    # The claim is decomposed into testable sub-conditions (llm_client.decompose_assumptions,
    # already existing) rather than asserted outright - each sub-condition is rated
    # plausible/aggressive/implausible, none of it independently verified yet at this stage.
    decomp = llm.decompose_assumptions(HYPOTHESIS_CLAIM, {
        "dependencies": [d["name"] for d in dependencies], "proprietary": proprietary, "sector": company.sector,
    })
    decomp_payload = decomp.parsed or {"assumptions": []}
    hypothesis_struct = {"claim": HYPOTHESIS_CLAIM, "sub_conditions": decomp_payload.get("assumptions", [])}
    hyp_ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Investment hypothesis: technology defensibility", value=json.dumps(hypothesis_struct),
        value_type="hypothesis_json", origin=EvidenceOrigin.platform_inference,
        source_tier=SourceTier.llm_inference if llm.mode == "live" else SourceTier.not_applicable,
        confidence=Confidence.medium,
        methodology="Claim decomposed into testable sub-conditions, each rated by the LLM - not independently verified, a starting hypothesis for further research.",
    )
    trace.add("assumptions", hypothesis_struct, [hyp_ev.id])

    # --- 6. transparent headline + status ---
    n_critical = sum(1 for d in dependencies if d.get("critical"))
    if n_critical:
        crit_names = ", ".join(d["name"] for d in dependencies if d.get("critical"))
        headline = f"⚠ {n_critical} dépendance(s) technique(s) critique(s) : {crit_names}."
    elif dependencies:
        headline = f"{len(dependencies)} dépendance(s) technique(s) identifiée(s), aucune jugée critique."
    else:
        headline = "Technologie majoritairement propriétaire déclarée, pas de dépendance tierce critique."

    platform_value = json.dumps({
        "dependencies": dependencies,
        "proprietary": proprietary,
        "cross_module_signals": activations,
        "hypothesis": hypothesis_struct,
    })

    upsert_module_result(
        db, company, MODULE, status=ModuleStatus.needs_review, headline=headline,
        deck_value=None, platform_value=platform_value, discrepancy_explanation=None,
        trace=trace, llm_mode=llm.mode,
    )
