"""
Shared scaffolding for the reasoning loop every module follows
(spec section 51):

    extract -> identify_unknowns -> research -> verify -> calculate ->
    benchmark -> reality_check -> contradictions -> assumptions ->
    investment_implication

Not every module populates every step (e.g. "Founders" has no
"calculate" step) - ReasoningTrace just accumulates whichever steps a
module actually performs, each one pointing back at the Evidence rows
that support it, so the API/frontend can render:

    conclusion -> reasoning -> calculation -> evidence -> source
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from sqlalchemy.orm import Session

from app.models import Company, ModuleResult, ModuleStatus


@dataclass
class ReasoningTrace:
    steps: list[dict] = field(default_factory=list)

    def add(self, step: str, content: Any, evidence_ids: list[str] | None = None) -> None:
        self.steps.append({"step": step, "content": content, "evidence_ids": evidence_ids or []})

    def all_evidence_ids(self) -> list[str]:
        ids: list[str] = []
        for s in self.steps:
            ids.extend(s.get("evidence_ids", []))
        return ids

    def to_json(self) -> dict:
        return {"steps": self.steps}


def upsert_module_result(
    db: Session,
    company: Company,
    module: str,
    *,
    status: ModuleStatus,
    headline: str | None,
    deck_value: str | None,
    platform_value: str | None,
    discrepancy_explanation: str | None,
    trace: ReasoningTrace,
    llm_mode: str,
) -> ModuleResult:
    existing = (
        db.query(ModuleResult)
        .filter(ModuleResult.company_id == company.id, ModuleResult.module == module)
        .one_or_none()
    )
    if existing is None:
        existing = ModuleResult(company_id=company.id, module=module)
        db.add(existing)

    existing.status = status
    existing.headline = headline
    existing.deck_value = deck_value
    existing.platform_value = platform_value
    existing.discrepancy_explanation = discrepancy_explanation
    existing.reasoning_json = trace.to_json()
    existing.evidence_ids_json = trace.all_evidence_ids()
    existing.llm_mode = llm_mode
    db.flush()
    return existing
