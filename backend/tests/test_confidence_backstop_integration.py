"""
Integration proof that the confidence backstop (services/reasoning/
confidence.py) is actually wired into modules, not just unit-tested in
isolation. A model claiming "high" confidence off a single thin source
must not reach the Evidence table as Confidence.high.
"""
from app.models import Confidence, Evidence
from app.services.llm_client import get_llm_client, LlmResult
from app.services.search_client import get_search_client, SearchResponse, SearchResult
from app.services.reasoning import competition_module, traction_module


def test_competition_landscape_confidence_is_capped_by_single_source(db_session, sample_company, sample_deck, monkeypatch):
    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(
        mode="live", query="stub",
        results=[SearchResult(title="One thin blog post", url="https://example.com/blog", content="vague content")],
    ))
    llm = get_llm_client()
    # The model itself claims "high" confidence off that single source - the platform
    # must not take that at face value.
    monkeypatch.setattr(llm, "synthesize_research", lambda *a, **k: LlmResult(
        mode="live", text="stub", parsed={"answer": "Réponse synthétisée.", "confidence": "high"},
    ))

    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    landscape_ev = (
        db_session.query(Evidence)
        .filter_by(company_id=sample_company.id, module="competition", claim="Independently researched competitive landscape")
        .one()
    )
    assert landscape_ev.confidence != Confidence.high
    assert landscape_ev.confidence == Confidence.low  # exactly one source -> capped to low, not unverified either


def test_traction_external_corroboration_confidence_is_capped_by_zero_sources(db_session, sample_company, sample_deck, monkeypatch):
    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(mode="live", query="stub", results=[]))
    llm = get_llm_client()
    monkeypatch.setattr(llm, "synthesize_research", lambda *a, **k: LlmResult(
        mode="live", text="stub", parsed={"answer": "Réponse synthétisée sans aucune source réelle.", "confidence": "medium"},
    ))

    traction_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    ev = (
        db_session.query(Evidence)
        .filter_by(company_id=sample_company.id, module="traction", claim="External corroboration of customer traction")
        .one()
    )
    # Zero sources found -> capped all the way to unverified, regardless of the "medium" the model claimed.
    assert ev.confidence == Confidence.unverified
