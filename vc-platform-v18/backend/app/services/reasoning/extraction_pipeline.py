"""
Phase 1 - the canonical deal representation's extraction pipeline.

Deck -> raw extraction -> normalized facts/numbers -> claims -> assumptions
                                                                     |
                                                    (modules/evidence/reasoning consume from here on)

Replaces the single `extract_claims()` call (still available, kept as a
lower-fidelity fallback/legacy path - see upload.py) with five explicit,
separately-inspectable passes:

  Pass A - Number recognition (deterministic, regex - see number_extraction.py).
           No LLM call, no interpretation yet: just "here is a number, here
           is its raw text/unit/currency/period/slide/context."
  Pass B - Number semantic classification (LLM, full deck as context).
           Turns "raw number" into "this is ARR" / "this is funding raised" /
           etc, keeping multiple candidates when genuinely ambiguous instead
           of silently picking one.
  Pass C - Structured Company/Product/Market fields (LLM). What the deck
           states, not what it argues - company identity, funding history,
           product description/architecture/roadmap, pricing, distribution,
           dependencies, market definition.
  Pass D - Management claims/assertions (LLM). What the deck argues, not
           just states - "we are the market leader", "proprietary tech" -
           each with required_evidence/potential_challenge so a future
           research pass has something concrete to act on.
  Pass E - Assumption identification (LLM, decompose_assumptions - already
           existed, previously only ever applied to Technology's fixed
           hypothesis). Applied here to every extracted claim of type
           traction_projection: what would need to be true for this
           forecast to hold.

Every Number and Claim produced is persisted via claim_store's single
choke points - nothing extracted here is later silently dropped, even if
no reasoning module reads a given claim_type yet (see claim_taxonomy.py's
CLAIM_TYPE_TO_MODULES for what's actually wired up vs. just persisted and
waiting).
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.models import Claim, ClaimKind, ClaimRelationship, NumberSemanticCategory
from app.services.claim_store import add_claim, add_number, classify_number
from app.services.llm_client import get_llm_client
from app.services.number_extraction import extract_number_candidates, structure_number_candidate

# Only claims of these types are run through Pass E (assumption decomposition) -
# a forecast/projection is exactly the shape of claim that HAS decomposable
# assumptions; a plain descriptive fact (e.g. "HQ in Paris") does not.
_ASSUMPTION_ELIGIBLE_CLAIM_TYPES = {"traction_projection"}


@dataclass
class ExtractionReport:
    """What Pass A-E actually produced, for a single deck - this is the
    object a caller (upload.py, or a standalone test/demo script) uses to
    both persist and to show exactly what was extracted, per-pass, without
    re-querying the DB."""
    numbers: list[dict] = field(default_factory=list)
    structured_fields: list[dict] = field(default_factory=list)
    management_claims: list[dict] = field(default_factory=list)
    assumptions: list[dict] = field(default_factory=list)
    llm_mode: str = "mock"


def run_extraction(db: Session, *, company_id: str, deck_id: str, deck_text: str) -> ExtractionReport:
    llm = get_llm_client()
    report = ExtractionReport(llm_mode=llm.mode)

    # --- Pass A: deterministic number recognition + structuring -----------
    candidates = extract_number_candidates(deck_text)
    number_rows = []
    for i, cand in enumerate(candidates):
        structured = structure_number_candidate(cand)
        number_rows.append(add_number(
            db, company_id=company_id, deck_id=deck_id,
            raw_text=cand.raw_text, value=structured["value"], unit=structured["unit"],
            currency=structured["currency"], period=structured["period"],
            as_of_date=structured["as_of_date"], definition=structured["definition"],
            slide_reference=cand.slide_reference, context=cand.context,
        ))

    # --- Pass B: semantic classification, LLM (or its mock heuristic) -----
    if number_rows:
        classify_input = [
            {"index": i, "raw_text": n.raw_text, "value": n.value, "unit": n.unit,
             "currency": n.currency, "period": n.period, "context": n.context}
            for i, n in enumerate(number_rows)
        ]
        classify_result = llm.classify_numbers(deck_text, classify_input)
        classifications = (classify_result.parsed or {}).get("classifications", [])
        for c in classifications:
            idx = c.get("index")
            if not isinstance(idx, int) or not (0 <= idx < len(number_rows)):
                continue
            category_str = c.get("semantic_category") or "unclassified"
            try:
                category = NumberSemanticCategory(category_str)
            except ValueError:
                category = NumberSemanticCategory.unclassified
            classify_number(
                db, number_rows[idx],
                semantic_category=category,
                semantic_confidence=c.get("semantic_confidence") or "low",
                candidate_categories=c.get("candidate_categories") or [],
            )
    report.numbers = [n.to_dict() for n in number_rows]

    # --- Pass C: structured Company/Product/Market fields ------------------
    fields_result = llm.extract_structured_fields(deck_text)
    fields = (fields_result.parsed or {}).get("fields", [])
    structured_field_claims = []
    for f in fields:
        claim_type = f.get("claim_type")
        text = f.get("text")
        if not claim_type or not text:
            continue
        kind_str = f.get("kind") or "fact"
        kind = ClaimKind.company_claim if kind_str == "company_claim" else ClaimKind.fact
        try:
            claim = add_claim(
                db, company_id=company_id, deck_id=deck_id, kind=kind, claim_type=claim_type,
                text=text, context=f.get("context"), slide_reference=f.get("slide_reference"),
                source="deck",
            )
            structured_field_claims.append(claim)
        except ValueError:
            continue  # unknown claim_type from a live LLM response - skip rather than crash the pipeline
    report.structured_fields = [c.to_dict() for c in structured_field_claims]

    # --- Pass D: management claims/assertions -------------------------------
    claims_result = llm.extract_management_claims(deck_text)
    mgmt_claims = (claims_result.parsed or {}).get("claims", [])
    management_claim_rows = []
    for c in mgmt_claims:
        claim_type = c.get("claim_type")
        text = c.get("text")
        if not claim_type or not text:
            continue
        try:
            claim = add_claim(
                db, company_id=company_id, deck_id=deck_id, kind=ClaimKind.company_claim, claim_type=claim_type,
                text=text, context=c.get("context"), slide_reference=c.get("slide_reference"), source="deck",
                required_evidence=c.get("required_evidence"), potential_challenge=c.get("potential_challenge"),
            )
            management_claim_rows.append(claim)
        except ValueError:
            continue
    report.management_claims = [c.to_dict() for c in management_claim_rows]

    # --- Pass E: assumption decomposition, for forecast-shaped claims only -
    assumptions = []
    for claim in management_claim_rows:
        if claim.claim_type not in _ASSUMPTION_ELIGIBLE_CLAIM_TYPES:
            continue
        decomp = llm.decompose_assumptions(claim.text, {"claim_type": claim.claim_type})
        for a in (decomp.parsed or {}).get("assumptions", []):
            assumption_text = a.get("assumption")
            if not assumption_text:
                continue
            arow = add_claim(
                db, company_id=company_id, deck_id=deck_id, kind=ClaimKind.assumption,
                claim_type=claim.claim_type, text=assumption_text,
                context=a.get("reason"), source="platform_reasoning",
                parent_claim_id=claim.id, relationship_type=ClaimRelationship.assumption_of,
                required_evidence=a.get("reason"),
            )
            assumptions.append(arow)
    report.assumptions = [a.to_dict() for a in assumptions]

    return report
