from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_company_or_404
from app.models import Company, Deck, Stage, BusinessModel
from app.schemas import AnalyzeResponse, CompanyOut, DeckOut
from app.services.deck_parser import parse_deck
from app.services.llm_client import get_llm_client
from app.rules.saas_rules import evaluate_trigger_rules
from app.services.reasoning import market_module, traction_module, founders_module, competition_module, business_model_module, technology_module, market_dynamics_module, extraction_pipeline

router = APIRouter(prefix="/companies", tags=["upload"])


@router.post("/{company_id}/deck", response_model=AnalyzeResponse)
async def upload_deck(
    company: Company = Depends(get_company_or_404),
    db: Session = Depends(get_db),
    file: UploadFile = File(...),
    stage: str | None = Form(None),
    business_model: str | None = Form(None),
    sector: str | None = Form(None),
    hq_country: str | None = Form(None),
    legal_name: str | None = Form(None),
):
    file_bytes = await file.read()
    try:
        parsed = parse_deck(file.filename, file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Update workspace metadata (spec section 4: company workspace)
    if stage:
        try:
            company.stage = Stage(stage)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid stage '{stage}'")
    if business_model:
        try:
            company.business_model = BusinessModel(business_model)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid business_model '{business_model}'")
    if sector:
        company.sector = sector
    if hq_country:
        company.hq_country = hq_country
    if legal_name:
        company.legal_name = legal_name

    llm = get_llm_client()

    # If nobody typed a sector in the workspace form, read it off the deck itself rather than
    # leaving every downstream research query (market sizing, competitors) guessing blind.
    if not company.sector:
        sector_result = llm.infer_sector(parsed.raw_text)
        inferred_sector = (sector_result.parsed or {}).get("sector")
        if inferred_sector:
            company.sector = inferred_sector

    # Short display tag for the header chip (e.g. "Insuretech") - separate from `sector`, which
    # stays the longer, precise research-query phrase. Runs whether the sector came from the
    # form or was just inferred, since the form field alone is never short enough for a chip.
    if company.sector and not company.industry_tag:
        tag_result = llm.categorize_industry_tag(company.sector)
        tag = (tag_result.parsed or {}).get("tag")
        if tag:
            company.industry_tag = tag

    extraction = llm.extract_claims(parsed.raw_text)
    extracted_claims = extraction.parsed if isinstance(extraction.parsed, list) else []

    deck = Deck(
        company_id=company.id,
        filename=file.filename,
        raw_text=parsed.raw_text,
        slides_json=parsed.to_slides_json(),
        extracted_claims_json=extracted_claims,
    )
    db.add(deck)
    db.flush()

    # Phase 1 - canonical deal representation. Runs ADDITIVELY alongside the
    # legacy extract_claims() above: it populates the new Number/Claim tables
    # (numbers extracted+classified separately from interpretation, structured
    # company/product/market fields, management assertions, and their
    # decomposed assumptions) without touching any existing reasoning module -
    # those still read deck.extracted_claims_json exactly as before. Repointing
    # the reasoning modules onto Claim/Number is deliberately NOT done here -
    # that's reasoning-engine wiring, out of scope for Phase 1.
    extraction_pipeline.run_extraction(db, company_id=company.id, deck_id=deck.id, deck_text=parsed.raw_text)
    db.flush()

    # Rule engine (spec section 38): which modules does this deck's content
    # obligate us to run, beyond the default MVP set.
    fired_rules = evaluate_trigger_rules(extracted_claims)
    modules_triggered = {"market", "market_dynamics", "competition", "traction", "founders", "business_model", "technology"}
    for rule in fired_rules:
        modules_triggered.update(rule["triggers"])

    if "market" in modules_triggered:
        market_module.run_auto(db, company, deck)
    if "market_dynamics" in modules_triggered:
        market_dynamics_module.run_auto(db, company, deck)
    if "competition" in modules_triggered:
        competition_module.run_auto(db, company, deck)
    if "technology" in modules_triggered:
        technology_module.run_auto(db, company, deck)
    if "traction" in modules_triggered:
        traction_module.run_auto(db, company, deck)
    if "founders" in modules_triggered:
        founders_module.run_auto(db, company, deck)
    if "business_model" in modules_triggered:
        business_model_module.run_auto(db, company, deck)

    db.commit()
    db.refresh(company)

    return AnalyzeResponse(company=CompanyOut.model_validate(company), modules_triggered=sorted(modules_triggered))


@router.get("/{company_id}/decks", response_model=list[DeckOut])
def list_decks(company: Company = Depends(get_company_or_404), db: Session = Depends(get_db)):
    return db.query(Deck).filter_by(company_id=company.id).order_by(Deck.uploaded_at.desc()).all()
