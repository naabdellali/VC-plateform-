"""
Competition module: reads the precise target segment Market already
identified from the deck (same cross-module dependency pattern used for
Technology's read into Moat - see test_moat_evaluation.py), and uses it
to anchor the competitor-mapping query instead of only the broad sector.
Same underlying fix as market's segment narrowing: "who competes in
insurance software" surfaces every insurtech vendor; "who competes in
parametric underwriting for agricultural insurers" surfaces the actual
comparable set.
"""
import json

from app.models import ModuleResult, ModuleStatus
from app.services.llm_client import get_llm_client, LlmResult
from app.services.search_client import get_search_client, SearchResponse, SearchResult
from app.services.reasoning import competition_module


def _seed_market_result(db_session, company, segment_description):
    db_session.add(ModuleResult(
        company_id=company.id, module="market", status=ModuleStatus.complete,
        headline="stub", platform_value=json.dumps({"segment_description": segment_description, "buyer_persona": None}),
        reasoning_json={"steps": []}, evidence_ids_json=[], llm_mode="live",
    ))
    db_session.flush()


def test_landscape_query_uses_markets_segment_when_available(db_session, sample_company, sample_deck, monkeypatch):
    _seed_market_result(db_session, sample_company, "logiciels de notes de frais pour cabinets de conseil")

    seen_queries = {}
    search = get_search_client()

    def fake_search(query, max_results=4):
        seen_queries.setdefault("queries", []).append(query)
        return SearchResponse(mode="live", query=query, results=[])

    monkeypatch.setattr(search, "search", fake_search)

    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    assert any("notes de frais" in q for q in seen_queries["queries"])
    # The broad sector is still referenced somewhere (as the explicit fallback), not dropped.
    assert any(sample_company.sector in q for q in seen_queries["queries"])


def test_falls_back_to_sector_only_when_market_has_not_run_yet(db_session, sample_company, sample_deck, monkeypatch):
    # No Market ModuleResult seeded at all - Competition must not crash or invent a segment.
    seen_queries = {}
    search = get_search_client()

    def fake_search(query, max_results=4):
        seen_queries.setdefault("queries", []).append(query)
        return SearchResponse(mode="live", query=query, results=[])

    monkeypatch.setattr(search, "search", fake_search)

    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    assert any(sample_company.sector in q for q in seen_queries["queries"])

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="competition").one()
    assert result.status in (ModuleStatus.insufficient_evidence, ModuleStatus.needs_review)


def test_falls_back_to_sector_when_markets_platform_value_is_malformed(db_session, sample_company, sample_deck, monkeypatch):
    # A market ModuleResult exists but with unparsable platform_value (defensive path) -
    # must degrade to sector-only, not raise.
    db_session.add(ModuleResult(
        company_id=sample_company.id, module="market", status=ModuleStatus.complete,
        headline="stub", platform_value="not valid json",
        reasoning_json={"steps": []}, evidence_ids_json=[], llm_mode="live",
    ))
    db_session.flush()

    search = get_search_client()
    monkeypatch.setattr(search, "search", lambda *a, **k: SearchResponse(mode="live", query="stub", results=[]))

    # Must not raise.
    competition_module.run_auto(db_session, sample_company, sample_deck)
    db_session.commit()

    result = db_session.query(ModuleResult).filter_by(company_id=sample_company.id, module="competition").one()
    assert result is not None
