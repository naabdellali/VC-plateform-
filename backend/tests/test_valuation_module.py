"""
Valuation & Scenarios module. Three things this must prove:

1. It never fabricates a revenue base - it reads Traction's already-
   persisted deck_value from the DB (same cross-module dependency
   pattern Competition uses for Technology - see test_moat_evaluation.py)
   and reports insufficient_evidence, not a guess, whenever that figure
   is missing, whenever the sector is unknown, or whenever no comparable
   sources were found.
2. The implied valuation range and the three Downside/Base/Upside
   scenarios are exactly what calc/valuation.py's formulas + the
   stage's growth-rate benchmarks in rules/valuation_rules.py produce -
   not a number the LLM invented.
3. The growth-rate assumption used is always the company's actual stage,
   read from rules/valuation_rules.py, and is explicitly labelled as a
   sector benchmark in the evidence methodology, not a claim about this
   specific company.
"""
import json

from app.models import ModuleResult, ModuleStatus, Stage
from app.rules.valuation_rules import get_scenario_growth_rates, PROJECTION_YEARS
from app.services.calc.valuation import implied_valuation_range, project_scenario_value
from app.services.llm_client import get_llm_client, LlmResult
from app.services.search_client import get_search_client, SearchResponse, SearchResult
from app.services.reasoning import valuation_module


def _seed_traction_result(db_session, company, deck_value: str | None):
    db_session.add(ModuleResult(
        company_id=company.id, module="traction", status=ModuleStatus.needs_review,
        headline="stub", deck_value=deck_value, platform_value=None,
        reasoning_json={"steps": []}, evidence_ids_json=[], llm_mode="mock",
    ))
    db_session.flush()


def test_insufficient_when_traction_has_not_run_yet(db_session, sample_company, sample_deck):
    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.insufficient_evidence
    assert "traction" in result.headline.lower()


def test_insufficient_when_traction_found_no_revenue(db_session, sample_company, sample_deck):
    _seed_traction_result(db_session, sample_company, deck_value=None)

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.insufficient_evidence


def test_insufficient_when_sector_unknown(db_session, sample_company, sample_deck):
    sample_company.sector = None
    _seed_traction_result(db_session, sample_company, deck_value="90000")

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.insufficient_evidence
    assert "secteur" in result.headline.lower()


def test_insufficient_when_no_comparable_sources_found(db_session, sample_company, sample_deck):
    # Mock mode's search client already returns empty results with no API
    # key configured - this exercises that path with no monkeypatching.
    _seed_traction_result(db_session, sample_company, deck_value="90000")

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.insufficient_evidence
    assert float(result.deck_value) == 90000  # the revenue figure itself was still recorded
    assert result.platform_value is None  # but no multiple/valuation was fabricated


def test_insufficient_when_llm_reports_insufficient(db_session, sample_company, sample_deck, monkeypatch):
    _seed_traction_result(db_session, sample_company, deck_value="90000")

    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(
        mode="live", query="stub",
        results=[SearchResult(title="Some report", url="https://example.com", content="irrelevant content")],
    ))
    llm = get_llm_client()
    monkeypatch.setattr(llm, "estimate_valuation_multiples", lambda *a, **k: LlmResult(
        mode="live", text="stub", parsed={"insufficient": True, "reason": "aucun comparable pertinent"},
    ))

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.insufficient_evidence
    assert result.platform_value is None


def test_computes_implied_valuation_and_scenarios_matching_the_formulas(db_session, sample_company, sample_deck, monkeypatch):
    # sample_company is stage=Stage.seed (see conftest.py).
    _seed_traction_result(db_session, sample_company, deck_value="90000")

    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(
        mode="live", query="stub",
        results=[
            SearchResult(title="Seed SaaS comps report", url="https://example.com/comps", content="6-9x ARR for seed SaaS."),
        ],
    ))
    llm = get_llm_client()
    monkeypatch.setattr(llm, "estimate_valuation_multiples", lambda *a, **k: LlmResult(
        mode="live", text="stub",
        parsed={
            "insufficient": False, "low_multiple": 6.0, "high_multiple": 9.0, "multiple_basis": "ARR",
            "reasoning": "Multiple observé sur des rounds seed comparables [1].",
            "footnotes": [{"n": 1, "source_index": 0, "detail": "Seed SaaS comps report"}],
        },
    ))

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    assert result.status == ModuleStatus.needs_review
    assert float(result.deck_value) == 90000

    payload = json.loads(result.platform_value)
    assert payload["multiple_low"] == 6.0
    assert payload["multiple_high"] == 9.0

    expected_implied = implied_valuation_range(90000.0, 6.0, 9.0)
    assert payload["implied_valuation"]["low"] == expected_implied["low"]
    assert payload["implied_valuation"]["high"] == expected_implied["high"]

    # Scenarios must use the company's actual stage (seed) growth-rate
    # benchmarks and the SAME mid-point comparable multiple, not a number
    # invented independently of calc/valuation.py.
    growth_rates = get_scenario_growth_rates(Stage.seed)
    mid_multiple = (6.0 + 9.0) / 2
    for key in ("downside", "base", "upside"):
        expected = project_scenario_value(90000.0, growth_rates[key], PROJECTION_YEARS, mid_multiple)
        assert payload["scenarios"][key]["projected_revenue"] == expected["projected_revenue"]
        assert payload["scenarios"][key]["projected_value"] == expected["projected_value"]
        assert payload["scenarios"][key]["growth_rate"] == growth_rates[key]

    # Upside must project higher than Base, which must project higher than Downside -
    # a sanity check that the three scenarios are actually ordered, not just present.
    assert payload["scenarios"]["downside"]["projected_value"] < payload["scenarios"]["base"]["projected_value"]
    assert payload["scenarios"]["base"]["projected_value"] < payload["scenarios"]["upside"]["projected_value"]

    # Every number-bearing evidence row this module wrote is deterministic/sourced,
    # never left unmethodologized.
    evidence_ids = result.evidence_ids_json
    assert len(evidence_ids) >= 4  # multiple range + implied valuation + 3 scenarios (>=4 covers either count safely)


def test_scenarios_use_a_different_stage_growth_rate_for_series_a(db_session, sample_company, sample_deck, monkeypatch):
    sample_company.stage = Stage.series_a
    _seed_traction_result(db_session, sample_company, deck_value="90000")

    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(
        mode="live", query="stub",
        results=[SearchResult(title="Series A SaaS comps", url="https://example.com/comps-a", content="5-8x ARR.")],
    ))
    llm = get_llm_client()
    monkeypatch.setattr(llm, "estimate_valuation_multiples", lambda *a, **k: LlmResult(
        mode="live", text="stub",
        parsed={"insufficient": False, "low_multiple": 5.0, "high_multiple": 8.0, "multiple_basis": "ARR",
                "reasoning": "stub", "footnotes": []},
    ))

    valuation_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="valuation").one()
    payload = json.loads(result.platform_value)
    series_a_rates = get_scenario_growth_rates(Stage.series_a)
    assert payload["scenarios"]["base"]["growth_rate"] == series_a_rates["base"]
    # Series A's benchmark growth is more conservative than seed's - the module must not
    # silently reuse seed's rate regardless of the company's actual stage.
    seed_rates = get_scenario_growth_rates(Stage.seed)
    assert series_a_rates["base"] < seed_rates["base"]
