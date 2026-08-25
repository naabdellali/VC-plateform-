import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import Company, Deck, Stage, BusinessModel


@pytest.fixture()
def db_session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    session = Session()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def sample_company(db_session):
    company = Company(
        name="Acme SaaS",
        legal_name="Acme SaaS SAS",
        stage=Stage.seed,
        business_model=BusinessModel.saas,
        sector="B2B expense management software",
        hq_country="France",
    )
    db_session.add(company)
    db_session.flush()
    return company


@pytest.fixture()
def sample_deck(db_session, sample_company):
    deck = Deck(
        company_id=sample_company.id,
        filename="acme_pitch.pptx",
        raw_text="--- Slide 1: Market ---\nTAM: EUR 8bn\n\n--- Slide 2: Traction ---\nCurrent MRR: EUR 90k",
        slides_json=[{"slide": 1, "title": "Market", "text": "TAM: EUR 8bn", "notes": ""}],
        extracted_claims_json=[
            {"category": "market_size", "claim": "TAM: EUR 8bn", "value": "EUR 8bn", "slide_reference": 1},
            {"category": "traction_metric", "claim": "Current MRR: EUR 90k", "value": "EUR 90k", "slide_reference": 2},
            {"category": "team_background", "claim": "CEO is ex-Google, 10 years experience", "value": None, "slide_reference": 3},
            {"category": "competitors", "claim": "Main competitor: LegacyCorp", "value": "LegacyCorp", "slide_reference": 4},
        ],
    )
    db_session.add(deck)
    db_session.flush()
    return deck
