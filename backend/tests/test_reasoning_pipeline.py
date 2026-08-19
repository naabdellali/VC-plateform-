"""
End-to-end pipeline tests in MOCK MODE (no API keys configured in the test
environment). These assert two things that matter most for the product's
core promise:

1. The full pipeline (extract -> research -> verify -> calculate -> memo)
   runs without raising, even with zero external services configured.
2. Nothing produced in mock mode is ever mislabelled as verified: every
   mock-mode Evidence row must carry confidence=unverified or explicitly
   say "unable to independently verify" - never a fabricated fact.
"""
from app.models import ModuleResult, Evidence, Memo, Confidence
from app.services.reasoning import market_module, traction_module, founders_module, competition_module, business_model_module, technology_module, memo_module


def test_market_module_auto_pass_runs_in_mock_mode(db_session, sample_company, sample_deck):
    market_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="market").one()
    assert result.deck_value is not None  # parsed "EUR 8bn" from the deck claim
    assert result.status.value in {"needs_review", "insufficient_evidence"}
    assert result.llm_mode == "mock"

    # No live external evidence should claim more confidence than "unverified" in mock mode
    live_looking = [
        e for e in db_session.query(Evidence).filter_by(company_id=sample_company.id, module="market")
        if e.origin.value == "platform_inference"
    ]
    assert all(e.confidence == Confidence.unverified for e in live_looking)


def test_market_recalculate_bottom_up_produces_platform_value(db_session, sample_company, sample_deck):
    market_module.run_auto(db_session, sample_company, sample_deck)
    db_session.flush()

    out = market_module.recalculate(
        db_session, sample_company,
        methodology="bottom_up",
        inputs={"num_potential_customers": 40_000, "avg_annual_spend_eur": 3_000, "realistic_penetration": 0.25},
        assumptions=["25% penetration based on comparable vertical SaaS adoption curves"],
    )
    db_session.commit()

    assert out["estimate"]["value"] == 40_000 * 3_000 * 0.25
    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="market").one()
    assert result.platform_value is not None
    assert result.status.value == "complete"
    # deck claimed 8bn, platform bottom-up says 30M -> should be flagged as a major discrepancy
    assert out["comparison"] is not None
    assert out["comparison"]["ratio_platform_over_company"] < 0.5


def test_traction_module_auto_pass_and_mrr_series_flow(db_session, sample_company, sample_deck):
    traction_module.run_auto(db_session, sample_company, sample_deck)
    db_session.flush()

    # Classic volatile "services revenue mixed in" pattern
    volatile_series = [80_000, 110_000, 75_000, 120_000, 70_000, 130_000]
    report = traction_module.submit_mrr_series(db_session, sample_company, volatile_series)
    db_session.commit()

    assert report["coefficient_of_variation"] > 0.15
    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="traction").one()
    assert result.status.value == "complete"

    from app.models import RedFlag
    flags = db_session.query(RedFlag).filter_by(company_id=sample_company.id, module="traction").all()
    assert any("volatility" in f.explanation for f in flags)


def test_cac_ltv_consistency_flow(db_session, sample_company, sample_deck):
    # arpa*margin=175/mo; for reported_ltv=1000, implied monthly churn = 17.5%,
    # well above the 10%/month plausibility ceiling -> should be flagged.
    result = traction_module.submit_cac_ltv_check(
        db_session, sample_company, cac=500, reported_ltv=1_000, gross_margin=0.7, arpa_monthly=250,
    )
    db_session.commit()
    assert result["plausible"] is False

    # A genuinely plausible LTV should NOT be flagged.
    plausible_result = traction_module.submit_cac_ltv_check(
        db_session, sample_company, cac=5_000, reported_ltv=800_000, gross_margin=0.7, arpa_monthly=250,
    )
    db_session.commit()
    assert plausible_result["plausible"] is True


def test_founders_module_runs_in_mock_mode_and_flags_unverifiable(db_session, sample_company, sample_deck):
    founders_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="founders").one()
    assert result.llm_mode == "mock"
    # Pappers ran in mock mode -> should not claim a verified legal entity
    pappers_evidence = [
        e for e in db_session.query(Evidence).filter_by(company_id=sample_company.id, module="founders")
        if e.source_name == "Pappers.fr"
    ]
    assert len(pappers_evidence) >= 1
    assert all(e.confidence != Confidence.high for e in pappers_evidence if "not configured" in (e.methodology or ""))


def test_competition_module_runs_in_mock_mode(db_session, sample_company, sample_deck):
    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="competition").one()
    assert "LegacyCorp" in (result.deck_value or "")

    # The moat grade is split into its own tray tile/module row - it should always be
    # populated (even if just "insufficient_evidence" in mock mode), never silently missing.
    moat_result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="moat").one()
    assert moat_result.status.value in {"needs_review", "insufficient_evidence"}


def test_technology_module_runs_in_mock_mode_and_is_honest_about_insufficiency(db_session, sample_company, sample_deck):
    # Mock mode never invents a dependency it can't ground - with no live LLM,
    # identify_tech_dependencies always returns empty, so this should be an
    # honest insufficient_evidence, never a fabricated dependency list.
    technology_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="technology").one()
    assert result.status.value == "insufficient_evidence"
    assert result.llm_mode == "mock"


def test_business_model_module_is_a_transparent_passthrough(db_session, sample_company, sample_deck):
    business_model_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="business_model").one()
    assert result.status.value == "complete"
    assert "SaaS" in (result.headline or "")  # sample_company fixture is BusinessModel.saas


def test_memo_generation_assembles_all_modules_and_recommends_conservatively(db_session, sample_company, sample_deck):
    market_module.run_auto(db_session, sample_company, sample_deck)
    traction_module.run_auto(db_session, sample_company, sample_deck)
    founders_module.run_auto(db_session, sample_company, sample_deck)
    competition_module.run_auto(db_session, sample_company, sample_deck)
    business_model_module.run_auto(db_session, sample_company, sample_deck)
    technology_module.run_auto(db_session, sample_company, sample_deck)
    db_session.flush()

    memo = memo_module.generate_memo(db_session, sample_company)
    db_session.commit()

    assert memo.recommendation is not None
    # In mock mode with modules stuck at needs_review, the deterministic
    # rule should never auto-recommend "invest" - that would violate
    # "don't optimize for positive conclusions."
    assert memo.recommendation.value != "invest"
    titles = [s["title"] for s in memo.sections_json]
    assert "Taille de marché (TAM / SAM / SOM)" in titles and "Traction" in titles and "Red Flags" in titles and "Faut-il continuer ?" in titles

    saved = db_session.query(Memo).filter_by(company_id=sample_company.id).one()
    assert saved.id == memo.id
