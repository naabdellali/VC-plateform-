from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_company_or_404
from app.models import Company, ModuleResult, Evidence, RedFlag
from app.schemas import ModuleResultOut, EvidenceOut, RedFlagOut
from app.services.reasoning import market_module, traction_module

router = APIRouter(prefix="/companies", tags=["modules"])


@router.get("/{company_id}/modules", response_model=list[ModuleResultOut])
def list_modules(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    return db.query(ModuleResult).filter_by(company_id=company.id).all()


@router.get("/{company_id}/modules/{module}", response_model=ModuleResultOut)
def get_module(module: str, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    result = db.query(ModuleResult).filter_by(company_id=company.id, module=module).one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail=f"Module '{module}' has not been analyzed yet for this company")
    return result


@router.get("/{company_id}/evidence", response_model=list[EvidenceOut])
def list_evidence(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db), module: str | None = None):
    q = db.query(Evidence).filter_by(company_id=company.id)
    if module:
        q = q.filter_by(module=module)
    return q.order_by(Evidence.created_at.asc()).all()


@router.get("/{company_id}/evidence/{evidence_id}", response_model=EvidenceOut)
def get_evidence(evidence_id: str, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    ev = db.query(Evidence).filter_by(company_id=company.id, id=evidence_id).one_or_none()
    if ev is None:
        raise HTTPException(status_code=404, detail="Evidence not found")
    return ev


@router.get("/{company_id}/red-flags", response_model=list[RedFlagOut])
def list_red_flags(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    return db.query(RedFlag).filter_by(company_id=company.id).order_by(RedFlag.severity).all()


# --- Human-in-the-loop endpoints (spec section 52) --------------------------

class MarketRecalculateRequest(BaseModel):
    methodology: Literal["bottom_up", "top_down"]
    inputs: dict
    assumptions: list[str] = []


@router.post("/{company_id}/modules/market/recalculate")
def recalculate_market(payload: MarketRecalculateRequest, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    try:
        out = market_module.recalculate(db, company, methodology=payload.methodology, inputs=payload.inputs, assumptions=payload.assumptions)
    except (KeyError, ValueError) as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return out


class MrrSeriesRequest(BaseModel):
    monthly_values_eur: list[float]


@router.post("/{company_id}/modules/traction/mrr-series")
def submit_mrr_series(payload: MrrSeriesRequest, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    if len(payload.monthly_values_eur) < 2:
        raise HTTPException(status_code=400, detail="Need at least 2 monthly values")
    out = traction_module.submit_mrr_series(db, company, payload.monthly_values_eur)
    db.commit()
    return out


class CacLtvRequest(BaseModel):
    cac: float
    reported_ltv: float
    gross_margin: float
    arpa_monthly: float


@router.post("/{company_id}/modules/traction/cac-ltv-check")
def submit_cac_ltv_check(payload: CacLtvRequest, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    try:
        out = traction_module.submit_cac_ltv_check(db, company, **payload.model_dump())
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    db.commit()
    return out


class RuleOf40Request(BaseModel):
    growth_rate_pct: float
    profit_margin_pct: float


@router.post("/{company_id}/modules/traction/rule-of-40")
def submit_rule_of_40(payload: RuleOf40Request, company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    out = traction_module.rule_of_40_check(db, company, **payload.model_dump())
    db.commit()
    return out
