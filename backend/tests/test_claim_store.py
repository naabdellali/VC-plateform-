"""
claim_store.py / claim_taxonomy.py are the single choke points the canonical
deal representation depends on - every Number/Claim in the platform must go
through add_number()/add_claim(), and every claim_type must be validated
against the taxonomy before persistence. These tests lock in that discipline.
"""
import pytest

from app.models import Claim, ClaimKind, ClaimVerificationStatus, ClaimRelationship, Number, NumberSemanticCategory
from app.services.claim_store import add_claim, add_number, classify_number
from app.services.claim_taxonomy import validate_claim_type, ALL_CLAIM_TYPES


def test_add_claim_persists_with_kind_and_taxonomy_validated(db_session, sample_company, sample_deck):
    claim = add_claim(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id,
        kind=ClaimKind.company_claim, claim_type="competitive_position",
        text="We are the market leader in France.", slide_reference="4", source="deck",
        required_evidence="Independent market share data.",
        potential_challenge="No named competitor comparison given.",
    )
    db_session.commit()

    fetched = db_session.query(Claim).filter_by(id=claim.id).one()
    assert fetched.kind == ClaimKind.company_claim
    assert fetched.claim_type == "competitive_position"
    assert fetched.verification_status == ClaimVerificationStatus.unverified  # default
    assert fetched.required_evidence == "Independent market share data."


def test_add_claim_rejects_unknown_claim_type(db_session, sample_company):
    with pytest.raises(ValueError):
        add_claim(
            db_session, company_id=sample_company.id,
            kind=ClaimKind.fact, claim_type="not_a_real_claim_type",
            text="Should never be persisted.",
        )
    # nothing should have been added to the session
    assert db_session.query(Claim).count() == 0


def test_add_claim_supports_parent_child_assumption_relationship(db_session, sample_company, sample_deck):
    forecast = add_claim(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id,
        kind=ClaimKind.company_claim, claim_type="traction_projection",
        text="ARR will reach 5M by end of next year.",
    )
    assumption = add_claim(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id,
        kind=ClaimKind.assumption, claim_type="traction_projection",
        text="Assumes successful US market entry within the year.",
        parent_claim_id=forecast.id, relationship_type=ClaimRelationship.assumption_of,
    )
    db_session.commit()

    fetched_forecast = db_session.query(Claim).filter_by(id=forecast.id).one()
    assert len(fetched_forecast.children) == 1
    assert fetched_forecast.children[0].id == assumption.id
    assert assumption.parent_claim.id == forecast.id
    assert assumption.relationship_type == ClaimRelationship.assumption_of


def test_add_number_preserves_raw_evidence_without_forcing_classification(db_session, sample_company, sample_deck):
    number = add_number(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id,
        raw_text="2M€", value=2_000_000.0, unit="EUR", currency="EUR",
        slide_reference="1", context="ARR de 2M€ en decembre 2025.",
    )
    db_session.commit()

    fetched = db_session.query(Number).filter_by(id=number.id).one()
    assert fetched.raw_text == "2M€"
    assert fetched.value == 2_000_000.0
    # Pass A never classifies - semantic_category defaults to unclassified until Pass B runs
    assert fetched.semantic_category == NumberSemanticCategory.unclassified
    assert fetched.claim_id is None


def test_classify_number_never_rewrites_raw_fields(db_session, sample_company, sample_deck):
    number = add_number(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id,
        raw_text="2M€", value=2_000_000.0, unit="EUR", currency="EUR", context="ARR de 2M€.",
    )
    classify_number(
        db_session, number,
        semantic_category=NumberSemanticCategory.arr,
        semantic_confidence="high",
        candidate_categories=["arr", "revenue"],
    )
    db_session.commit()

    fetched = db_session.query(Number).filter_by(id=number.id).one()
    assert fetched.semantic_category == NumberSemanticCategory.arr
    assert fetched.semantic_confidence == "high"
    # raw evidence (Pass A output) must be untouched by the classification pass
    assert fetched.raw_text == "2M€"
    assert fetched.value == 2_000_000.0
    assert fetched.context == "ARR de 2M€."


def test_validate_claim_type_accepts_every_taxonomy_entry():
    for ct in ALL_CLAIM_TYPES:
        assert validate_claim_type(ct) == ct


def test_validate_claim_type_rejects_unknown_type():
    with pytest.raises(ValueError):
        validate_claim_type("totally_made_up_type")
