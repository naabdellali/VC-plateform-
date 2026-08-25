"""
Moat evaluation - now a dedicated step (llm_client.evaluate_moat) run
unconditionally inside competition_module.run_auto, explicitly combining the
Technology module's already-persisted findings with the competitive/sourced
research, rather than being bundled inside build_competitive_landscape's own
output (which meant moat silently went "insufficient" any time the general
landscape matrix did, and never saw Technology's read at all since Technology
used to run after Competition in the pipeline).

Two things this must prove:
1. The Technology module's platform_value (tech_summary/dependencies/
   proprietary/tech_grade) is actually read from the DB and passed into
   evaluate_moat - not just available in principle.
2. Moat can still produce a real grade even when the general competitive
   landscape matrix (build_competitive_landscape) itself returns
   insufficient=true - the two are decoupled.
"""
import json

from app.models import ModuleResult, ModuleStatus
from app.services.llm_client import get_llm_client, LlmResult
from app.services.reasoning import competition_module


def test_moat_reads_technology_module_result_and_survives_thin_landscape(db_session, sample_company, sample_deck, monkeypatch):
    # A technology read is already sitting in the DB, as it would be after
    # upload.py runs Technology before Competition (see upload.py's ordering).
    tech_platform_value = {
        "tech_summary": "Moteur de scoring propriétaire sur données d'assurance agrégées.",
        "proprietary_narrative": "Le moteur combine des signaux propriétaires issus de multiples assureurs partenaires.",
        "proprietary": ["moteur de scoring propriétaire"],
        "dependencies": [{"name": "AWS", "risk_note": "Infrastructure critique.", "critical": True}],
        "tech_grade": "Avancé", "tech_grade_reason": "Données agrégées difficilement réplicables.",
    }
    db_session.add(ModuleResult(
        company_id=sample_company.id, module="technology", status=ModuleStatus.needs_review,
        headline="stub", platform_value=json.dumps(tech_platform_value),
        reasoning_json={"steps": []}, evidence_ids_json=[], llm_mode="live",
    ))
    db_session.flush()

    llm = get_llm_client()
    seen_calls = {}

    def fake_evaluate_moat(company_context, tech_payload, competitors, ocean_type, sources):
        seen_calls["tech_payload"] = tech_payload
        return LlmResult(
            mode="live", text="stub",
            parsed={
                "insufficient": False, "grade": "Narrow Moat",
                "strengths": ["Données propriétaires agrégées sur plusieurs assureurs partenaires."],
                "gaps": ["Pas de confirmation externe indépendante de cette exclusivité de données."],
                "what_would_widen_it": ["Sécuriser des contrats d'exclusivité data à long terme avec les partenaires."],
                "footnotes": [],
            },
        )

    monkeypatch.setattr(llm, "evaluate_moat", fake_evaluate_moat)
    # The general competitive-landscape matrix itself is thin/insufficient - this must NOT
    # prevent Moat from still producing a real grade (the decoupling this test is about).
    monkeypatch.setattr(
        llm, "build_competitive_landscape",
        lambda *a, **k: LlmResult(mode="live", text="stub", parsed={"insufficient": True, "reason": "thin sources"}),
    )

    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    # Technology's own findings actually reached evaluate_moat.
    assert seen_calls["tech_payload"]["tech_grade"] == "Avancé"
    assert seen_calls["tech_payload"]["proprietary_narrative"] == tech_platform_value["proprietary_narrative"]

    moat_result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="moat").one()
    assert moat_result.status == ModuleStatus.needs_review
    assert moat_result.headline == "Narrow Moat"
    moat_payload = json.loads(moat_result.platform_value)
    assert moat_payload["grade"] == "Narrow Moat"
    assert moat_payload["strengths"]
