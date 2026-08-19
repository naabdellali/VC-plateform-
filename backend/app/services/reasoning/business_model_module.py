"""
Business Model tile: deliberately NOT a research/reasoning module. It used
to be folded into the Traction tile ("Traction & Business Model"), but the
business model is just a fixed field the analyst sets on the company
workspace form - there is no independent research to run on it, so
bundling it with Traction's forensic checks was misleading (it implied
both were "analyzed" to the same depth).

Split out on its own so the tray is honest about what this tile is: a
transparent mirror of the workspace field, not a platform conclusion. No
LLM call, no evidence fabricated beyond "this is what the analyst entered."
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import Company, Deck, ModuleStatus, EvidenceOrigin, SourceTier, Confidence
from app.services.evidence_store import add_evidence
from app.services.reasoning.base import ReasoningTrace, upsert_module_result

MODULE = "business_model"

_LABELS = {
    "saas": "SaaS",
    "marketplace": "Marketplace",
    "hardware": "Hardware",
    "consumer": "Consumer",
    "fintech": "Fintech",
    "deeptech": "Deeptech",
    "other": "Other",
}


def run_auto(db: Session, company: Company, deck: Deck | None = None) -> None:
    trace = ReasoningTrace()
    label = _LABELS.get(company.business_model.value, company.business_model.value)

    ev = add_evidence(
        db, company_id=company.id, module=MODULE,
        claim="Business model (as entered on the company workspace)", value=label,
        origin=EvidenceOrigin.company_claim, source_tier=SourceTier.not_applicable,
        confidence=Confidence.medium,
        methodology="Workspace form field, set by the analyst - not independently researched or verified.",
    )
    trace.add("extract", {"business_model": label}, [ev.id])

    upsert_module_result(
        db, company, MODULE, status=ModuleStatus.complete,
        headline=f"Business model : {label}.",
        deck_value=None, platform_value=None, discrepancy_explanation=None,
        trace=trace, llm_mode="n/a",
    )
