from __future__ import annotations

from sqlalchemy.orm import Session

from app.models import RedFlag, RedFlagSeverity


def add_red_flag(
    db: Session,
    *,
    company_id: str,
    module: str | None,
    category: str,
    severity: RedFlagSeverity,
    explanation: str,
    evidence_id: str | None = None,
    potential_impact: str | None = None,
    resolving_information: str | None = None,
) -> RedFlag:
    flag = RedFlag(
        company_id=company_id,
        module=module,
        category=category,
        severity=severity,
        explanation=explanation,
        evidence_id=evidence_id,
        potential_impact=potential_impact,
        resolving_information=resolving_information,
    )
    db.add(flag)
    db.flush()
    return flag
