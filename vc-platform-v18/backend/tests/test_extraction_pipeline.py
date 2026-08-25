"""
End-to-end test of Phase 1's canonical deal representation, run against a
dense synthetic deck (revenue by quarter, ~35 paying customers, TAM/SAM/SOM,
competitive claim, team, funding history, and a forward-looking ARR forecast
with an implicit US-expansion assumption) - deliberately built to mirror the
density of deck the analyst described, and to exercise exactly the two old
extract_claims() categories ("financials", "other") that used to disappear
end-to-end with zero downstream consumer.

Mock mode only (no ANTHROPIC_API_KEY in this sandbox) - assertions are
therefore scoped to what the deterministic Pass A regex engine and the
regex/keyword mock fallbacks for Pass B/C/D can actually produce. This is
the honest ceiling of what can be demonstrated without a live LLM call; see
the delivered report to the analyst for the explicit caveat that live-mode
recall will be materially higher.
"""
from app.models import Claim, Number, ClaimKind, NumberSemanticCategory
from app.services.reasoning import extraction_pipeline

DENSE_DECK_TEXT = """--- Slide 1: Company ---
Acme SaaS SAS, siege social a Paris. Jean Dupont, CEO et co-fondateur, ex-Google.
Marie Curie, CTO et co-fondatrice, ex-Stripe.

--- Slide 2: Problem & Solution ---
Le probleme: la gestion des notes de frais est manuelle et lente pour les PME.
Notre solution: une plateforme SaaS d'automatisation des notes de frais.

--- Slide 3: Traction ---
MRR actuel: 90K EUR en decembre 2025, en hausse de 120% sur un an.
35 clients payants a ce jour. ARR de 2M€.

--- Slide 4: Revenue by quarter ---
Q1 2025: 400K EUR de revenue. Q2 2025: 600K EUR de revenue.
Q3 2025: 850K EUR de revenue. Q4 2025: 1.1M EUR de revenue.

--- Slide 5: Market ---
TAM estime a 64 milliards de dollars pour ce secteur.
SAM: 7.4bn. SOM: 740M.

--- Slide 6: Competition ---
Nous sommes leader du marche en France, aucun concurrent direct de taille comparable.
Technologie proprietaire de rapprochement automatique des recus.

--- Slide 7: Funding ---
Levee de fonds: 3.5M EUR en seed, menee par Example Ventures.
Valorisation post-money: 15M EUR.

--- Slide 8: Forecast ---
Objectif: ARR de 8M EUR d'ici fin 2027, porte par l'expansion sur le marche americain.

--- Slide 9: Pricing ---
Pricing: 49 EUR par mois par utilisateur.
"""


def test_extraction_pipeline_runs_end_to_end_in_mock_mode(db_session, sample_company, sample_deck):
    report = extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()

    assert report.llm_mode == "mock"
    # Every pass should have produced something demonstrable, not an empty pipeline.
    assert len(report.numbers) > 0
    assert len(report.structured_fields) > 0
    assert len(report.management_claims) > 0


def test_pass_a_and_b_capture_traction_and_financial_numbers_that_previously_disappeared(db_session, sample_company, sample_deck):
    # Under the OLD extract_claims() pipeline, quarterly revenue figures and
    # other numeric detail fell into the "financials"/"other" categories that
    # zero reasoning modules ever read - i.e. they were extracted once, then
    # silently lost. Here they must persist as inspectable Number rows.
    extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()

    numbers = db_session.query(Number).filter_by(company_id=sample_company.id).all()
    raw_texts = {n.raw_text for n in numbers}

    # MRR/ARR/customer-count (traction) - previously in "traction_metric" but only
    # ever read by the traction module for the FIRST claim found, not preserved as
    # a structured, inspectable, multi-valued record.
    assert "90K" in raw_texts or any("90" in r for r in raw_texts)
    assert "35 clients" in raw_texts
    assert "2M€" in raw_texts

    # Quarterly revenue - this is exactly the "financials" category that used to
    # vanish end-to-end (zero modules consumed it). Now persisted as Number rows,
    # inspectable regardless of whether a module reads them yet.
    assert "400K EUR" in raw_texts or any("400" in r for r in raw_texts)
    assert "600K EUR" in raw_texts or any("600" in r for r in raw_texts)

    # Every Number preserves its provenance back to the exact slide it came from.
    mrr_number = next(n for n in numbers if "90" in n.raw_text)
    assert mrr_number.slide_reference == "3"
    assert mrr_number.context  # non-empty - the surrounding text is preserved, not discarded


def test_pass_b_classifies_at_least_some_numbers_via_mock_heuristic(db_session, sample_company, sample_deck):
    extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()

    numbers = db_session.query(Number).filter_by(company_id=sample_company.id).all()
    classified = [n for n in numbers if n.semantic_category != NumberSemanticCategory.unclassified]
    # The mock keyword classifier should label at least the MRR/customers/TAM numbers
    assert len(classified) > 0
    categories = {n.semantic_category for n in classified}
    assert NumberSemanticCategory.customers in categories or NumberSemanticCategory.mrr in categories


def test_pass_c_and_d_produce_claims_with_correct_epistemic_kind(db_session, sample_company, sample_deck):
    extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()

    claims = db_session.query(Claim).filter_by(company_id=sample_company.id).all()
    assert len(claims) > 0

    # Team background (Pass C) should be a `fact`, not a `company_claim` - it's
    # descriptive, not an assertion management is making about itself.
    team_claims = [c for c in claims if c.claim_type == "team_background"]
    assert len(team_claims) > 0
    assert all(c.kind == ClaimKind.fact for c in team_claims)

    # "Leader du marche, aucun concurrent" (Pass D) must be a company_claim, not a
    # fact - the whole point of the epistemic-status separation the analyst asked
    # for is that an unverified self-assertion is never treated as established fact.
    competitive_claims = [c for c in claims if c.claim_type == "competitive_position"]
    assert len(competitive_claims) > 0
    assert all(c.kind == ClaimKind.company_claim for c in competitive_claims)
    assert all(c.required_evidence for c in competitive_claims)
    assert all(c.potential_challenge for c in competitive_claims)


def test_pass_e_decomposes_assumptions_for_the_forward_looking_forecast(db_session, sample_company, sample_deck):
    extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()

    claims = db_session.query(Claim).filter_by(company_id=sample_company.id).all()
    forecast_claims = [c for c in claims if c.claim_type == "traction_projection"]
    assert len(forecast_claims) > 0

    assumptions = [c for c in claims if c.kind == ClaimKind.assumption]
    assert len(assumptions) > 0
    # Every assumption must be traceable back to the forecast it underpins -
    # provenance is the whole point (per-analyst instruction).
    forecast_ids = {c.id for c in forecast_claims}
    assert all(a.parent_claim_id in forecast_ids for a in assumptions)


def test_extraction_pipeline_does_not_touch_legacy_extracted_claims_json(db_session, sample_company, sample_deck):
    # Phase 1 must run purely additively - the legacy field existing reasoning
    # modules still read must be completely untouched by the new pipeline.
    before = list(sample_deck.extracted_claims_json)
    extraction_pipeline.run_extraction(
        db_session, company_id=sample_company.id, deck_id=sample_deck.id, deck_text=DENSE_DECK_TEXT,
    )
    db_session.commit()
    assert sample_deck.extracted_claims_json == before
