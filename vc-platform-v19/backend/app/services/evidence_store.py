"""
Single choke point for writing to the `evidence` table. Reasoning modules
must go through `add_evidence` rather than constructing `Evidence` rows
directly - it exists so no code path can accidentally create a record
without an origin/source_tier/confidence, which would silently break the
traceability chain the whole product is built on.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Evidence, EvidenceOrigin, SourceTier, Confidence


def add_evidence(
    db: Session,
    *,
    company_id: str,
    module: str,
    claim: str,
    origin: EvidenceOrigin,
    source_tier: SourceTier,
    confidence: Confidence,
    value: str | None = None,
    value_type: str | None = None,
    source_name: str | None = None,
    source_url: str | None = None,
    source_publication_date: str | None = None,
    methodology: str | None = None,
    supporting_excerpt: str | None = None,
    assumptions: list[str] | None = None,
) -> Evidence:
    ev = Evidence(
        company_id=company_id,
        module=module,
        claim=claim,
        value=str(value) if value is not None else None,
        value_type=value_type,
        origin=origin,
        source_tier=source_tier,
        confidence=confidence,
        source_name=source_name,
        source_url=source_url,
        source_publication_date=source_publication_date,
        methodology=methodology,
        supporting_excerpt=supporting_excerpt,
        assumptions_json=assumptions or [],
    )
    db.add(ev)
    db.flush()  # assign ev.id without committing the whole transaction
    return ev
