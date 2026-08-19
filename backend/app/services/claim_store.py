"""
Single choke points for writing to the `claims` and `numbers` tables -
mirrors evidence_store.py's `add_evidence()` pattern deliberately: no code
path should be able to create a Claim without a `kind` (fact / company_claim
/ assumption / inference) or a Number without at least its raw_text/context
preserved, which is exactly the discipline the canonical deal
representation depends on.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Claim, ClaimKind, ClaimVerificationStatus, ClaimRelationship, Number, NumberSemanticCategory
from app.services.claim_taxonomy import validate_claim_type


def add_claim(
    db: Session,
    *,
    company_id: str,
    kind: ClaimKind,
    claim_type: str,
    text: str,
    deck_id: str | None = None,
    context: str | None = None,
    slide_reference: str | None = None,
    source: str | None = None,
    verification_status: ClaimVerificationStatus = ClaimVerificationStatus.unverified,
    required_evidence: str | None = None,
    potential_challenge: str | None = None,
    related_modules: list[str] | None = None,
    parent_claim_id: str | None = None,
    relationship_type: ClaimRelationship | None = None,
) -> Claim:
    validate_claim_type(claim_type)
    claim = Claim(
        company_id=company_id,
        deck_id=deck_id,
        kind=kind,
        claim_type=claim_type,
        text=text,
        context=context,
        slide_reference=slide_reference,
        source=source,
        verification_status=verification_status,
        required_evidence=required_evidence,
        potential_challenge=potential_challenge,
        related_modules=related_modules or [],
        parent_claim_id=parent_claim_id,
        relationship_type=relationship_type,
    )
    db.add(claim)
    db.flush()
    return claim


def add_number(
    db: Session,
    *,
    company_id: str,
    deck_id: str,
    raw_text: str,
    value: float | None = None,
    unit: str | None = None,
    currency: str | None = None,
    period: str | None = None,
    as_of_date: str | None = None,
    definition: str | None = None,
    slide_reference: str | None = None,
    context: str | None = None,
    semantic_category: NumberSemanticCategory = NumberSemanticCategory.unclassified,
    semantic_confidence: str | None = None,
    candidate_categories: list[str] | None = None,
    claim_id: str | None = None,
) -> Number:
    number = Number(
        company_id=company_id,
        deck_id=deck_id,
        raw_text=raw_text,
        value=value,
        unit=unit,
        currency=currency,
        period=period,
        as_of_date=as_of_date,
        definition=definition,
        slide_reference=slide_reference,
        context=context,
        semantic_category=semantic_category,
        semantic_confidence=semantic_confidence,
        candidate_categories=candidate_categories or [],
        claim_id=claim_id,
    )
    db.add(number)
    db.flush()
    return number


def classify_number(db: Session, number: Number, *, semantic_category: NumberSemanticCategory, semantic_confidence: str, candidate_categories: list[str] | None = None) -> Number:
    """Pass B - annotates a Number already created by Pass A. Never rewrites
    raw_text/value/unit/context: the raw recognition is immutable, only the
    semantic label is updated, so a bad classification never destroys the
    underlying evidence."""
    number.semantic_category = semantic_category
    number.semantic_confidence = semantic_confidence
    if candidate_categories:
        number.candidate_categories = candidate_categories
    db.flush()
    return number
