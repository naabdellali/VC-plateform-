from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_company_or_404
from app.models import Company, ModuleResult, RedFlag
from app.schemas import CompanyCreate, CompanyOut, CompanyDetailOut, TrayTile
from app.rules.stage_rules import get_stage_priorities

router = APIRouter(prefix="/companies", tags=["companies"])

TRAY_MODULES = [
    ("market", "Market Analysis"),
    ("competition", "Competition & Moat"),
    ("traction", "Traction & Business Model"),
    ("founders", "Team & Background"),
]


@router.post("", response_model=CompanyOut)
def create_company(payload: CompanyCreate, db: Session = Depends(get_db)):
    company = Company(name=payload.name)
    db.add(company)
    db.commit()
    db.refresh(company)
    return company


@router.get("", response_model=list[CompanyOut])
def list_companies(db: Session = Depends(get_db)):
    return db.query(Company).order_by(Company.created_at.desc()).all()


@router.get("/{company_id}", response_model=CompanyDetailOut)
def get_company(company: Company = Depends(get_company_or_404)):
    return company


@router.get("/{company_id}/tray", response_model=list[TrayTile])
def get_tray(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    results = {m.module: m for m in db.query(ModuleResult).filter_by(company_id=company.id).all()}
    flag_counts: dict[str, int] = {}
    for f in db.query(RedFlag).filter_by(company_id=company.id).all():
        if f.module:
            flag_counts[f.module] = flag_counts.get(f.module, 0) + 1

    tiles = []
    for key, label in TRAY_MODULES:
        mr = results.get(key)
        tiles.append(
            TrayTile(
                module=key,
                label=label,
                status=mr.status.value if mr else "pending",
                headline=mr.headline if mr else None,
                red_flag_count=flag_counts.get(key, 0),
            )
        )
    return tiles


@router.get("/{company_id}/stage-priorities")
def get_company_stage_priorities(company: Company = Depends(get_company_or_404)):
    return get_stage_priorities(company.stage)
