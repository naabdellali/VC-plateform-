"""
Exercises the Technology module's "critical dependency found" path end to
end - the trigger firing, the grounded follow-up research, the cross-module
red flag landing in Moat's territory, and the InvestmentHypothesis
decomposition. Mock mode alone never reaches this path (identify_tech_dependencies
always returns empty with no live LLM - see test_reasoning_pipeline.py's
insufficiency test for that), so the LLM extraction call is monkeypatched
here to return a fixed critical dependency, while every other call stays
in real mock mode (search_client mock mode already returns empty results
deterministically, no network involved).
"""
import json

from app.models import ModuleResult, RedFlag, Evidence
from app.services.llm_client import get_llm_client, LlmResult
from app.services.reasoning import technology_module


def test_critical_dependency_fires_trigger_research_redflag_and_hypothesis(db_session, sample_company, sample_deck, monkeypatch):
    llm = get_llm_client()
    monkeypatch.setattr(
        llm, "identify_tech_dependencies",
        lambda deck_text: LlmResult(
            mode="mock", text="stub",
            parsed={
                "dependencies": [
                    {"name": "OpenAI API", "risk_note": "Dépendance critique à l'API d'OpenAI pour le NLP du produit.", "critical": True, "evidence_text": "We use OpenAI's API to power our assistant."}
                ],
                "proprietary": ["proprietary onboarding flow"],
                "tech_grade": "Intermédiaire",
                "tech_grade_reason": "Le coeur technique repose sur une API tierce, pas de modèle propriétaire identifié.",
            },
        ),
    )

    technology_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="technology").one()
    assert result.status.value == "needs_review"
    assert "OpenAI API" in (result.headline or "")

    platform_value = json.loads(result.platform_value)
    assert platform_value["dependencies"][0]["name"] == "OpenAI API"
    assert platform_value["cross_module_signals"], "critical dependency should have fired at least one trigger activation"
    assert "moat" in platform_value["cross_module_signals"][0]["activates"]
    assert platform_value["hypothesis"]["claim"]

    # Cross-module signal: a red flag lands in Moat's territory without the
    # Technology module silently rewriting Moat's own ModuleResult.
    moat_flags = db_session.query(RedFlag).filter_by(company_id=sample_company.id, category="moat", module="technology").all()
    assert len(moat_flags) == 1
    assert "OpenAI API" in moat_flags[0].explanation

    # The hypothesis is stored as its own inspectable Evidence row, not just buried in reasoning_json.
    hyp_evidence = db_session.query(Evidence).filter_by(company_id=sample_company.id, module="technology", value_type="hypothesis_json").one()
    assert hyp_evidence.value is not None

    # Founder questions (non-researchable judgment calls) surfaced via identify_unknowns,
    # the same mechanism the memo already reads key_questions_json from.
    steps = result.reasoning_json["steps"]
    unknowns_steps = [s for s in steps if s["step"] == "identify_unknowns"]
    assert unknowns_steps and unknowns_steps[0]["content"]
