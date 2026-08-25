from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_company_or_404
from app.models import Company, Memo
from app.schemas import MemoOut
from app.services.reasoning.memo_module import generate_memo

router = APIRouter(prefix="/companies", tags=["memo"])


@router.post("/{company_id}/memo/generate", response_model=MemoOut)
def generate_company_memo(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    memo = generate_memo(db, company)
    db.commit()
    db.refresh(memo)
    return memo


@router.get("/{company_id}/memo", response_model=MemoOut)
def get_latest_memo(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    memo = (
        db.query(Memo)
        .filter_by(company_id=company.id)
        .order_by(Memo.generated_at.desc())
        .first()
    )
    if memo is None:
        raise HTTPException(status_code=404, detail="No memo generated yet - POST /memo/generate first")
    return memo
