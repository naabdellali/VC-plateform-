from fastapi import Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Company


def get_company_or_404(company_id: str, db: Session = Depends(get_db)) -> Company:
    company = db.query(Company).filter(Company.id == company_id).one_or_none()
    if company is None:
        raise HTTPException(status_code=404, detail=f"Company {company_id} not found")
    return company
